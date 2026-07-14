from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import AppConfig
from .graph import GraphStore
from .ingest import repo_id_for
from .model_gateway import ModelClient
from .state import DevWorkflowState, KnowledgeChunk
from .verify import format_verify_log, run_verification, verification_summary


def run_workflow(repo: Path, query: str, config: AppConfig, store: GraphStore, model: ModelClient) -> DevWorkflowState:
    repo = repo.resolve()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    output_dir = Path(config.workflow.output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    state = DevWorkflowState(
        user_query=query,
        repo_meta={
            "repo_path": str(repo),
            "repo_id": repo_id_for(repo),
            "run_id": run_id,
            "output_dir": str(output_dir),
        },
    )
    _classify(state)
    _retrieve_graph(state, store)
    _build_context(state)

    for attempt in range(config.workflow.max_retries + 1):
        state.retry_count = attempt
        state.ai_diff = _generate_diff(state, model)
        _write_text(output_dir / "change.patch", state.ai_diff)
        verify_results = run_verification(repo, config.verification)
        state.verify_report = verification_summary(verify_results)
        _write_json(output_dir / "verify_report.json", state.verify_report)
        if state.verify_report["passed"]:
            break
        if attempt >= config.workflow.max_retries:
            break
        state.error_log = format_verify_log(verify_results)
        _build_context(state)

    state.final_report = _build_final_report(state)
    _write_text(output_dir / "context.md", state.system_prompt)
    _write_json(output_dir / "state.json", state.to_dict())
    _write_text(output_dir / "final_report.md", state.final_report)
    return state


def _classify(state: DevWorkflowState) -> None:
    text = state.user_query.lower()
    rules = [
        ("crash_fix", ["crash", "崩溃", "exception", "traceback"], ["crash", "debugging"]),
        ("performance", ["performance", "性能", "slow", "优化"], ["performance"]),
        ("feature", ["feature", "新增", "实现", "add"], ["architecture"]),
        ("review", ["review", "评审", "pr", "diff"], ["style", "test"]),
        ("refactor", ["refactor", "重构", "架构"], ["architecture", "test"]),
    ]
    for task_type, needles, tags in rules:
        if any(needle in text for needle in needles):
            state.task_type = task_type
            state.required_knowledge_tags = tags
            break
    else:
        state.task_type = "general"
        state.required_knowledge_tags = ["architecture", "test"]
    state.human_approval = any(needle in text for needle in ["底层", "core", "security", "权限", "delete", "删除"])


def _retrieve_graph(state: DevWorkflowState, store: GraphStore) -> None:
    state.knowledge_chunks = store.search(
        repo_id=str(state.repo_meta["repo_id"]),
        query=state.user_query,
        tags=state.required_knowledge_tags,
        limit=8,
    )


def _build_context(state: DevWorkflowState) -> None:
    chunks = "\n\n".join(_format_chunk(item) for item in state.knowledge_chunks) or "未检索到相关知识片段。"
    error_block = f"\n\n## 上轮校验失败日志\n{state.error_log}" if state.error_log else ""
    state.system_prompt = (
        "# AI 编程工作流上下文\n\n"
        "你是一个谨慎的编码 Agent。默认只输出可审阅的 diff 和说明，不直接修改用户仓库。\n"
        "必须遵守项目 AGENTS.md、README、文档规范和校验结果。避免破坏性命令和无关重构。\n\n"
        f"## 任务类型\n{state.task_type}\n\n"
        f"## 知识标签\n{', '.join(state.required_knowledge_tags)}\n\n"
        f"## 检索知识\n{chunks}\n"
        f"{error_block}\n"
    )


def _generate_diff(state: DevWorkflowState, model: ModelClient) -> str:
    user_prompt = (
        f"开发者需求:\n{state.user_query}\n\n"
        "请输出统一 diff、修改说明、风险说明和建议校验命令。"
    )
    response = model.complete(state.system_prompt, user_prompt)
    state.target_model = response.model
    return response.content


def _build_final_report(state: DevWorkflowState) -> str:
    passed = bool(state.verify_report.get("passed"))
    status = "通过" if passed else "未通过"
    chunks = "\n".join(f"- {item.source} ({item.kind}, score={item.score})" for item in state.knowledge_chunks) or "- 无"
    return (
        f"# AI Workflow Run Report\n\n"
        f"- 状态: {status}\n"
        f"- 任务类型: {state.task_type}\n"
        f"- 模型: {state.target_model}\n"
        f"- 重试次数: {state.retry_count}\n"
        f"- 高危审批: {'需要' if state.human_approval else '不需要'}\n\n"
        f"## 检索片段\n{chunks}\n\n"
        "## 产物\n"
        "- `context.md`: 组装后的模型上下文\n"
        "- `change.patch`: 模型生成的可审阅 patch\n"
        "- `verify_report.json`: 校验流水线结果\n"
        "- `state.json`: 完整状态快照\n"
    )


def _format_chunk(chunk: KnowledgeChunk) -> str:
    return f"### {chunk.source} [{chunk.kind}] score={chunk.score}\n{chunk.text}"


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _json_default(value: object) -> object:
    if hasattr(value, "__dict__"):
        return asdict(value)  # type: ignore[arg-type]
    return str(value)
