"""Agent Adapter 抽象层。

Adapter 把 Agent OS 的统一运行时契约翻译成具体 Agent 的执行方式。
本模块只提供接口、注册表和 dry-run 实现，不启动 Codex / Claude Code
等外部进程。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Protocol

from .config import AgentProfileConfig
from .contracts import AgentEvent, AgentRunRequest, AgentRunResult, Artifact, utc_now_iso
from .state import ContextPack


class AgentAdapter(Protocol):
    """所有 Agent 运行时适配器必须实现的最小接口。"""

    name: str

    def supports(self, agent: str) -> bool:
        """返回该 adapter 是否支持指定 Agent 名称。"""
        ...

    def run_task(self, request: AgentRunRequest) -> AgentRunResult:
        """执行一次 Agent 任务并返回统一结果。"""
        ...


class AgentAdapterRegistry:
    """进程内 Agent Adapter 注册表。"""

    def __init__(self):
        self._adapters: dict[str, AgentAdapter] = {}

    def register(self, adapter: AgentAdapter) -> None:
        """注册一个 adapter，名称重复时以后注册者覆盖。"""

        self._adapters[adapter.name] = adapter

    def resolve(self, agent: str, adapter: str | None = None) -> AgentAdapter:
        """按明确 adapter 名称或 Agent 名称解析 adapter。"""

        if adapter:
            try:
                return self._adapters[adapter]
            except KeyError as exc:
                raise LookupError(f"agent adapter is not registered: {adapter}") from exc

        for candidate in self._adapters.values():
            if candidate.supports(agent):
                return candidate
        raise LookupError(f"no agent adapter supports agent: {agent}")

    def names(self) -> list[str]:
        """返回已注册 adapter 名称。"""

        return sorted(self._adapters)


class DryRunAgentAdapter:
    """不启动外部进程的 Agent Adapter，用于测试平台运行时边界。"""

    name = "dry_run"

    def __init__(self, supported_agents: set[str] | None = None):
        self.supported_agents = supported_agents or {"generic", "codex", "claude-code"}

    def supports(self, agent: str) -> bool:
        return agent in self.supported_agents

    def run_task(self, request: AgentRunRequest) -> AgentRunResult:
        started_at = utc_now_iso()
        events = [
            AgentEvent(
                run_id=request.run_id,
                sequence=1,
                kind="started",
                message=f"Dry-run adapter accepted task for {request.agent}.",
                payload={"adapter": self.name, "mode": request.mode},
            ),
            AgentEvent(
                run_id=request.run_id,
                sequence=2,
                kind="finished",
                message="Dry-run completed without launching an external Agent.",
                payload={"artifacts": [artifact.name for artifact in request.artifacts]},
            ),
        ]
        return AgentRunResult(
            run_id=request.run_id,
            agent=request.agent,
            adapter=self.name,
            status="dry_run",
            started_at=started_at,
            finished_at=utc_now_iso(),
            events=events,
            artifacts=request.artifacts,
            summary="Dry-run adapter validated the AgentRunRequest.",
            metadata={"requested_adapter": request.adapter, "repo_path": request.repo_path},
        )


class CodexCliAdapter:
    """通过本地 CLI 进程运行 Codex 类 Agent 的最小 adapter。"""

    name = "codex_cli"

    def __init__(self, supported_agents: set[str] | None = None):
        self.supported_agents = supported_agents or {"codex"}

    def supports(self, agent: str) -> bool:
        return agent in self.supported_agents

    def run_task(self, request: AgentRunRequest) -> AgentRunResult:
        started_at = utc_now_iso()
        profile = _request_agent_profile(request)
        command = str(profile.get("command", "") or "")
        args = _string_list(profile.get("args", []))
        input_mode = str(profile.get("input_mode", "stdin") or "stdin")
        output_mode = str(profile.get("output_mode", "stream") or "stream")
        timeout_seconds = _timeout_seconds(request, profile)
        events = [
            AgentEvent(
                run_id=request.run_id,
                sequence=1,
                kind="started",
                message=f"Starting {self.name} for {request.agent}.",
                payload={
                    "adapter": self.name,
                    "command": command,
                    "args": args,
                    "cwd": request.repo_path,
                    "input_mode": input_mode,
                    "output_mode": output_mode,
                    "timeout_seconds": timeout_seconds,
                },
            )
        ]

        if input_mode != "stdin":
            return _agent_run_result(
                request=request,
                adapter=self.name,
                status="failed",
                started_at=started_at,
                events=events
                + [
                    AgentEvent(
                        run_id=request.run_id,
                        sequence=len(events) + 1,
                        kind="failed",
                        message=f"Unsupported input_mode: {input_mode}",
                    )
                ],
                error=f"Unsupported input_mode: {input_mode}",
            )
        if not command:
            return _agent_run_result(
                request=request,
                adapter=self.name,
                status="failed",
                started_at=started_at,
                events=events
                + [
                    AgentEvent(
                        run_id=request.run_id,
                        sequence=len(events) + 1,
                        kind="failed",
                        message="Agent profile command is empty.",
                    )
                ],
                error="Agent profile command is empty.",
            )

        try:
            completed = subprocess.run(
                [command, *args],
                input=_prompt_text(request),
                cwd=request.repo_path,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=_subprocess_env(profile),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            _append_output_events(events, request.run_id, _coerce_process_output(exc.stdout), _coerce_process_output(exc.stderr))
            events.append(
                AgentEvent(
                    run_id=request.run_id,
                    sequence=len(events) + 1,
                    kind="timeout",
                    message=f"Agent command timed out after {timeout_seconds} seconds.",
                    payload={"timeout_seconds": timeout_seconds},
                )
            )
            return _agent_run_result(
                request=request,
                adapter=self.name,
                status="timeout",
                started_at=started_at,
                events=events,
                error=events[-1].message,
            )
        except OSError as exc:
            events.append(
                AgentEvent(
                    run_id=request.run_id,
                    sequence=len(events) + 1,
                    kind="failed",
                    message=str(exc),
                    payload={"command": command},
                )
            )
            return _agent_run_result(
                request=request,
                adapter=self.name,
                status="failed",
                started_at=started_at,
                events=events,
                error=str(exc),
            )

        _append_output_events(events, request.run_id, completed.stdout, completed.stderr)
        if completed.returncode == 0:
            status = "succeeded"
            kind = "finished"
            message = "Agent command completed successfully."
            error = ""
        else:
            status = "failed"
            kind = "failed"
            message = f"Agent command exited with code {completed.returncode}."
            error = completed.stderr or message
        events.append(
            AgentEvent(
                run_id=request.run_id,
                sequence=len(events) + 1,
                kind=kind,
                message=message,
                payload={"exit_code": completed.returncode},
            )
        )
        return _agent_run_result(
            request=request,
            adapter=self.name,
            status=status,
            started_at=started_at,
            events=events,
            error=error,
        )


def build_agent_run_request(
    context_pack: ContextPack,
    adapter: str | None = None,
    profile: AgentProfileConfig | None = None,
    artifacts: list[Artifact] | None = None,
    limits: dict[str, object] | None = None,
    mode: str = "task",
    metadata: dict[str, object] | None = None,
) -> AgentRunRequest:
    """从 ContextPack 构建统一 AgentRunRequest。"""

    resolved_adapter = adapter or (profile.adapter if profile else "") or "dry_run"
    resolved_limits = dict(limits or {})
    resolved_metadata = dict(metadata or {})
    if profile:
        resolved_limits.setdefault("timeout_seconds", profile.timeout_seconds)
        profile_metadata = {
            "prompt_style": profile.prompt_style,
            "adapter": profile.adapter,
            "command": profile.command,
            "args": list(profile.args),
            "input_mode": profile.input_mode,
            "output_mode": profile.output_mode,
            "default_permissions": list(profile.default_permissions),
            "timeout_seconds": profile.timeout_seconds,
            "env": dict(profile.env),
        }
        existing_profile_metadata = resolved_metadata.get("agent_profile")
        if isinstance(existing_profile_metadata, dict):
            profile_metadata.update(existing_profile_metadata)
        resolved_metadata["agent_profile"] = profile_metadata

    return AgentRunRequest(
        run_id=context_pack.run_id,
        agent=context_pack.agent,
        adapter=resolved_adapter,
        repo_path=context_pack.repo_path,
        context_pack=context_pack,
        mode=mode,
        limits=resolved_limits,
        artifacts=list(artifacts or artifacts_from_context_pack(context_pack)),
        metadata=resolved_metadata,
    )


def artifacts_from_context_pack(context_pack: ContextPack) -> list[Artifact]:
    """把 ContextPack.generated_files 转成统一 Artifact 列表。"""

    return [
        Artifact(
            name=name,
            kind=_artifact_kind(name),
            path=path,
            media_type=_artifact_media_type(path),
            produced_by="prepare",
        )
        for name, path in sorted(context_pack.generated_files.items())
    ]


def default_agent_adapter_registry() -> AgentAdapterRegistry:
    """构建当前默认 adapter registry。"""

    registry = AgentAdapterRegistry()
    registry.register(DryRunAgentAdapter())
    registry.register(CodexCliAdapter())
    return registry


def _agent_run_result(
    *,
    request: AgentRunRequest,
    adapter: str,
    status: str,
    started_at: str,
    events: list[AgentEvent],
    error: str = "",
) -> AgentRunResult:
    return AgentRunResult(
        run_id=request.run_id,
        agent=request.agent,
        adapter=adapter,
        status=status,
        started_at=started_at,
        finished_at=utc_now_iso(),
        events=events,
        artifacts=request.artifacts,
        summary=_agent_result_summary(status, events),
        error=error,
        metadata={"requested_adapter": request.adapter, "repo_path": request.repo_path},
    )


def _agent_result_summary(status: str, events: list[AgentEvent]) -> str:
    terminal = events[-1].message if events else ""
    return terminal or f"Agent run finished with status: {status}"


def _request_agent_profile(request: AgentRunRequest) -> dict[str, object]:
    profile = request.metadata.get("agent_profile", {})
    if isinstance(profile, dict):
        return dict(profile)
    return {}


def _timeout_seconds(request: AgentRunRequest, profile: dict[str, object]) -> float | None:
    value = request.limits.get("timeout_seconds", profile.get("timeout_seconds"))
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []


def _subprocess_env(profile: dict[str, object]) -> dict[str, str]:
    env = os.environ.copy()
    profile_env = profile.get("env", {})
    if isinstance(profile_env, dict):
        env.update({str(key): str(value) for key, value in profile_env.items()})
    return env


def _prompt_text(request: AgentRunRequest) -> str:
    if request.context_pack.prompt_text:
        return request.context_pack.prompt_text
    for artifact in request.artifacts:
        if artifact.name == "agent_prompt" or artifact.kind == "prompt":
            path = Path(artifact.path)
            if path.exists():
                return path.read_text(encoding="utf-8")
    return ""


def _append_output_events(events: list[AgentEvent], run_id: str, stdout: str, stderr: str) -> None:
    if stdout:
        events.append(
            AgentEvent(
                run_id=run_id,
                sequence=len(events) + 1,
                kind="stdout",
                message=stdout,
            )
        )
    if stderr:
        events.append(
            AgentEvent(
                run_id=run_id,
                sequence=len(events) + 1,
                kind="stderr",
                message=stderr,
            )
        )


def _coerce_process_output(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def _artifact_kind(name: str) -> str:
    mapping = {
        "agent_prompt": "prompt",
        "context": "context",
        "manifest": "manifest",
        "state": "state",
        "final_report": "report",
    }
    return mapping.get(name, "artifact")


def _artifact_media_type(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".json"):
        return "application/json"
    if lowered.endswith(".md"):
        return "text/markdown"
    return "text/plain"
