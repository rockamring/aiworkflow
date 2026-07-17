"""Agent OS 的 Context Pack 生成流程。

prepare 是当前 Agent OS 的第一条核心能力：它不调用模型、不生成 patch、不执行验证命令，
而是把任务、检索上下文、项目规则和校验方式整理成可直接交给 Codex /
Claude Code 等 Agent 的任务包。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import AgentProfileConfig, AppConfig, VerificationCommand, resolve_agent_profile
from .context import ContextService, TaskClassification
from .graph import GraphStore
from .ingest import repo_id_for
from .prompt import PromptService
from .run_store import RunEventRecord, RunRecord, RunStore, run_store_root_for_output_dir
from .search import SearchService
from .state import ContextPack, ContextPackState, KnowledgeChunk


def prepare_context_pack(
    repo: Path,
    query: str,
    config: AppConfig,
    store: GraphStore,
    agent: str | None = None,
    project: str = "",
) -> ContextPackState:
    """生成一次可审阅、可复现的 Agent Context Pack。"""

    started_at = datetime.now().astimezone().isoformat()
    repo = repo.resolve()
    if not repo.exists() or not repo.is_dir():
        raise ValueError(f"目标仓库不存在或不是目录: {repo}")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    output_dir = Path(config.workflow.output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    repo_id = repo_id_for(repo)
    agent_name = agent or config.agent.default

    state = ContextPackState(
        user_query=query,
        repo_meta={
            "repo_path": str(repo),
            "repo_id": repo_id,
            "run_id": run_id,
            "output_dir": str(output_dir),
        },
        agent=agent_name,
    )

    context = ContextService(SearchService(store), char_budget=config.context.budget_chars)
    classification = context.classify(query)
    _record_classification(state, classification)

    response = context.retrieve(repo_id=repo_id, query=query, tags=classification.tags, limit=config.context.search_limit)
    state.knowledge_chunks = response.chunks
    state.search_stats = response.stats
    state.workflow_steps.append({"node": "retrieve", **response.stats})

    built_context = context.build_context(response.chunks)
    state.context_block = built_context.text
    state.budget_summary = built_context.summary
    state.workflow_steps.append({"node": "build_context", **built_context.summary})

    state.verification_commands = _verification_commands(config.verification.commands)
    profile = resolve_agent_profile(config, agent_name)
    task_guidance = PromptService().load_bundle(state.task_type).task
    state.agent_prompt = render_agent_prompt(
        query=query,
        classification=classification,
        agent=agent_name,
        profile=profile,
        task_guidance=task_guidance,
        context_block=state.context_block,
        verification_commands=state.verification_commands,
    )
    state.workflow_steps.append({"node": "render_agent_prompt", "agent": agent_name, "chars": len(state.agent_prompt)})

    generated_files = _generated_files(output_dir)
    state.generated_files = generated_files
    state.context_pack = ContextPack(
        run_id=run_id,
        repo_id=repo_id,
        repo_path=str(repo),
        query=query,
        task_type=state.task_type,
        agent=agent_name,
        knowledge_tags=state.required_knowledge_tags,
        context_chunks=state.knowledge_chunks,
        verification_commands=state.verification_commands,
        prompt_text=state.agent_prompt,
        search_stats=state.search_stats,
        budget_summary=state.budget_summary,
        generated_files=generated_files,
    )
    state.workflow_steps.append({"node": "build_context_pack", "chunks": len(state.knowledge_chunks)})

    state.final_report = _build_final_report(state)
    _write_outputs(output_dir, state)
    state.workflow_steps.append({"node": "write_outputs", "files": sorted(generated_files)})
    _write_json(output_dir / "state.json", state.to_dict())
    _append_run_record(config.workflow.output_dir, state, project, output_dir, started_at)
    return state


def render_agent_prompt(
    *,
    query: str,
    classification: TaskClassification,
    agent: str,
    profile: AgentProfileConfig,
    task_guidance: str,
    context_block: str,
    verification_commands: list[dict[str, str]],
) -> str:
    """渲染可直接交给目标 Agent 的任务 Prompt。"""

    verification_block = _format_verification_commands(verification_commands)
    extra = "\n".join(f"- {item}" for item in profile.extra_instructions) or "- 无额外项目指令。"
    tags = ", ".join(classification.tags) if classification.tags else "none"
    return (
        "# Agent Task Pack\n\n"
        f"- Agent: {agent}\n"
        f"- Prompt style: {profile.prompt_style}\n"
        f"- Task type: {classification.task_type}\n"
        f"- Knowledge tags: {tags}\n"
        f"- Human approval suggested: {'yes' if classification.human_approval else 'no'}\n\n"
        "## 任务\n"
        f"{query}\n\n"
        "## 工作方式\n"
        "- 优先使用本 Context Pack 中的上下文、规则和验证命令。\n"
        "- 不要盲目做全仓搜索；只有上下文不足时，再做小范围、有目的的检索。\n"
        "- 保持改动聚焦，避免无关重构。\n"
        "- 输出时说明关键依据、修改位置、风险和建议验证方式。\n\n"
        "## Agent Profile 指令\n"
        f"{extra}\n\n"
        "## 任务类型指导\n"
        f"{task_guidance.strip() or '按通用软件工程任务处理。'}\n\n"
        "## 建议验证命令\n"
        f"{verification_block}\n\n"
        "## 检索上下文\n"
        f"{context_block}\n"
    )


def _record_classification(state: ContextPackState, classification: TaskClassification) -> None:
    state.task_type = classification.task_type
    state.required_knowledge_tags = classification.tags
    state.human_approval = classification.human_approval
    state.workflow_steps.append(
        {
            "node": "classify",
            "task_type": classification.task_type,
            "tags": classification.tags,
            "human_approval": classification.human_approval,
        }
    )


def _verification_commands(commands: list[VerificationCommand]) -> list[dict[str, str]]:
    return [{"name": item.name, "command": item.command} for item in commands]


def _format_verification_commands(commands: list[dict[str, str]]) -> str:
    if not commands:
        return "未配置 verification.commands。"
    return "\n".join(f"- {item['name']}: `{item['command']}`" for item in commands)


def _generated_files(output_dir: Path) -> dict[str, str]:
    return {
        "agent_prompt": str((output_dir / "agent_prompt.md").resolve()),
        "context": str((output_dir / "context.md").resolve()),
        "manifest": str((output_dir / "manifest.json").resolve()),
        "state": str((output_dir / "state.json").resolve()),
        "final_report": str((output_dir / "final_report.md").resolve()),
    }


def _write_outputs(output_dir: Path, state: ContextPackState) -> None:
    _write_text(output_dir / "agent_prompt.md", state.agent_prompt)
    _write_text(output_dir / "context.md", state.context_block)
    _write_json(output_dir / "manifest.json", state.context_pack.to_dict() if state.context_pack else {})
    _write_text(output_dir / "final_report.md", state.final_report)


def _append_run_record(output_root: str, state: ContextPackState, project: str, output_dir: Path, started_at: str) -> None:
    if state.context_pack is None:
        return
    record = RunRecord.from_context_pack(
        state.context_pack,
        project=project,
        output_dir=str(output_dir),
        started_at=started_at,
        finished_at=datetime.now().astimezone().isoformat(),
    )
    run_store = RunStore(run_store_root_for_output_dir(output_root, project))
    run_store.append(record)
    run_store.append_event(
        RunEventRecord(
            run_id=state.context_pack.run_id,
            sequence=0,
            event_type="platform",
            source="prepare",
            kind="prepare.finished",
            message="Context Pack prepared successfully.",
            payload={
                "output_dir": str(output_dir),
                "generated_files": dict(state.generated_files),
                "search_stats": dict(state.search_stats),
                "budget_summary": dict(state.budget_summary),
            },
        )
    )


def _build_final_report(state: ContextPackState) -> str:
    chunks = "\n".join(_format_chunk_summary(item) for item in state.knowledge_chunks) or "- none"
    commands = _format_verification_commands(state.verification_commands)
    return (
        "# Agent Context Pack Report\n\n"
        f"- 状态: prepared\n"
        f"- Agent: {state.agent}\n"
        f"- 任务类型: {state.task_type}\n"
        f"- 知识标签: {', '.join(state.required_knowledge_tags) or 'none'}\n"
        f"- 人工审批建议: {'需要' if state.human_approval else '不需要'}\n"
        f"- 上下文片段: {len(state.knowledge_chunks)}\n"
        f"- 上下文预算: {state.budget_summary.get('used_chars', 0)} / {state.budget_summary.get('budget_chars', 0)} chars\n\n"
        f"## 检索片段\n{chunks}\n\n"
        f"## 建议验证命令\n{commands}\n\n"
        "## 产物\n"
        "- `agent_prompt.md`: 直接交给 Agent 的完整任务 Prompt\n"
        "- `context.md`: 被选中的上下文片段\n"
        "- `manifest.json`: 机器可读 Context Pack\n"
        "- `state.json`: 完整 prepare 过程状态\n"
        "- `final_report.md`: 本报告\n"
    )


def _format_chunk_summary(chunk: KnowledgeChunk) -> str:
    tags = ", ".join(chunk.tags) if chunk.tags else "none"
    return f"- {chunk.source} ({chunk.kind}, score={chunk.score}, tags={tags})"


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _json_default(value: object) -> object:
    if hasattr(value, "__dict__"):
        return asdict(value)  # type: ignore[arg-type]
    return str(value)
