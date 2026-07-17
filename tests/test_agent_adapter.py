import sys

import pytest

from aiworkflow.agent_adapter import (
    AgentAdapterRegistry,
    CodexCliAdapter,
    DryRunAgentAdapter,
    artifacts_from_context_pack,
    build_agent_run_request,
    default_agent_adapter_registry,
)
from aiworkflow.config import AgentProfileConfig
from aiworkflow.contracts import Artifact
from aiworkflow.state import ContextPack


def _pack(repo_path: str = "G:/repo") -> ContextPack:
    return ContextPack(
        run_id="run-1",
        repo_id="repo-1",
        repo_path=repo_path,
        query="修复 Renderer crash",
        task_type="crash_fix",
        agent="codex",
        prompt_text="Agent prompt",
        generated_files={
            "agent_prompt": "G:/repo/runs/run-1/agent_prompt.md",
            "manifest": "G:/repo/runs/run-1/manifest.json",
        },
    )


def test_registry_resolves_dry_run_adapter_by_name_and_agent():
    registry = AgentAdapterRegistry()
    adapter = DryRunAgentAdapter()
    registry.register(adapter)

    assert registry.names() == ["dry_run"]
    assert registry.resolve(agent="codex") is adapter
    assert registry.resolve(agent="codex", adapter="dry_run") is adapter


def test_registry_reports_missing_adapter_or_agent():
    registry = AgentAdapterRegistry()
    registry.register(DryRunAgentAdapter())

    with pytest.raises(LookupError):
        registry.resolve(agent="codex", adapter="missing")
    with pytest.raises(LookupError):
        registry.resolve(agent="unknown")


def test_build_agent_run_request_uses_context_pack_artifacts():
    request = build_agent_run_request(
        _pack(),
        adapter="dry_run",
        limits={"timeout_seconds": 600},
        metadata={"source": "test"},
    )

    assert request.run_id == "run-1"
    assert request.agent == "codex"
    assert request.adapter == "dry_run"
    assert request.limits["timeout_seconds"] == 600
    assert request.metadata["source"] == "test"
    assert {artifact.kind for artifact in request.artifacts} == {"prompt", "manifest"}


def test_build_agent_run_request_accepts_explicit_artifacts():
    artifact = Artifact(name="custom", kind="log", path="G:/repo/run.log")
    request = build_agent_run_request(_pack(), adapter="dry_run", artifacts=[artifact])

    assert request.artifacts == [artifact]


def test_build_agent_run_request_uses_profile_runtime_defaults():
    profile = AgentProfileConfig(
        prompt_style="codex",
        adapter="codex_cli",
        command="codex",
        args=["--approval-mode", "suggest"],
        input_mode="stdin",
        output_mode="stream",
        default_permissions=["read_repo"],
        timeout_seconds=123,
        env={"CODEX_ENV": "test"},
    )

    request = build_agent_run_request(_pack(), profile=profile)

    assert request.adapter == "codex_cli"
    assert request.limits["timeout_seconds"] == 123
    assert request.metadata["agent_profile"]["input_mode"] == "stdin"
    assert request.metadata["agent_profile"]["output_mode"] == "stream"
    assert request.metadata["agent_profile"]["default_permissions"] == ["read_repo"]
    assert request.metadata["agent_profile"]["command"] == "codex"
    assert request.metadata["agent_profile"]["env"] == {"CODEX_ENV": "test"}


def test_artifacts_from_context_pack_sets_media_types():
    artifacts = artifacts_from_context_pack(_pack())
    by_name = {artifact.name: artifact for artifact in artifacts}

    assert by_name["agent_prompt"].media_type == "text/markdown"
    assert by_name["manifest"].media_type == "application/json"


def test_dry_run_adapter_returns_serializable_result_without_external_agent():
    request = build_agent_run_request(_pack(), adapter="dry_run")
    adapter = DryRunAgentAdapter()

    result = adapter.run_task(request)
    data = result.to_dict()

    assert result.status == "dry_run"
    assert [event.kind for event in result.events] == ["started", "finished"]
    assert data["events"][0]["payload"]["adapter"] == "dry_run"
    assert data["artifacts"][0]["produced_by"] == "prepare"


def test_default_registry_contains_dry_run_adapter():
    registry = default_agent_adapter_registry()

    assert registry.resolve(agent="claude-code").name == "dry_run"
    assert registry.resolve(agent="codex", adapter="codex_cli").name == "codex_cli"


def test_codex_cli_adapter_sends_prompt_to_stdin_and_captures_stdout(tmp_path):
    profile = AgentProfileConfig(
        adapter="codex_cli",
        command=sys.executable,
        args=["-c", "import sys; data=sys.stdin.read(); print('PROMPT:' + data)"],
        input_mode="stdin",
        output_mode="stream",
        timeout_seconds=5,
    )
    request = build_agent_run_request(_pack(str(tmp_path)), profile=profile)

    result = CodexCliAdapter().run_task(request)

    assert result.status == "succeeded"
    assert [event.kind for event in result.events] == ["started", "stdout", "finished"]
    assert "PROMPT:Agent prompt" in result.events[1].message


def test_codex_cli_adapter_reports_failed_exit_with_stderr(tmp_path):
    profile = AgentProfileConfig(
        adapter="codex_cli",
        command=sys.executable,
        args=["-c", "import sys; sys.stderr.write('bad run'); sys.exit(3)"],
        input_mode="stdin",
        output_mode="stream",
        timeout_seconds=5,
    )
    request = build_agent_run_request(_pack(str(tmp_path)), profile=profile)

    result = CodexCliAdapter().run_task(request)

    assert result.status == "failed"
    assert [event.kind for event in result.events] == ["started", "stderr", "failed"]
    assert "bad run" in result.events[1].message
    assert result.events[-1].payload["exit_code"] == 3


def test_codex_cli_adapter_reports_timeout(tmp_path):
    profile = AgentProfileConfig(
        adapter="codex_cli",
        command=sys.executable,
        args=["-c", "import time; time.sleep(1)"],
        input_mode="stdin",
        output_mode="stream",
        timeout_seconds=0.05,
    )
    request = build_agent_run_request(_pack(str(tmp_path)), profile=profile)

    result = CodexCliAdapter().run_task(request)

    assert result.status == "timeout"
    assert result.events[-1].kind == "timeout"
