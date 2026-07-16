from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import AppConfig
from .context import ContextService
from .graph import GraphStore
from .ingest import repo_id_for
from .model_gateway import ModelClient
from .prompt import PromptService
from .review import run_review
from .search import SearchService
from .state import DevWorkflowState
from .verify import format_verify_log, run_verification, verification_summary


@dataclass(slots=True)
class WorkflowRuntime:
    repo: Path
    config: AppConfig
    store: GraphStore
    model: ModelClient
    output_dir: Path
    context: ContextService


WorkflowNode = Callable[[DevWorkflowState, WorkflowRuntime], None]
NODE_REGISTRY: dict[str, WorkflowNode] = {}


def workflow_node(name: str) -> Callable[[WorkflowNode], WorkflowNode]:
    def decorator(func: WorkflowNode) -> WorkflowNode:
        NODE_REGISTRY[name] = func
        return func

    return decorator


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
    runtime = WorkflowRuntime(
        repo=repo,
        config=config,
        store=store,
        model=model,
        output_dir=output_dir,
        context=ContextService(SearchService(store), PromptService()),
    )

    _run_node("classify", state, runtime)
    _run_node("retrieve", state, runtime)
    _run_node("build_prompt", state, runtime)

    for attempt in range(config.workflow.max_retries + 1):
        state.retry_count = attempt
        _run_node("generate", state, runtime)
        _run_node("verify", state, runtime)
        _write_json(output_dir / "state.json", state.to_dict())
        if state.verify_report.get("passed"):
            break
        if attempt >= config.workflow.max_retries:
            break
        _run_node("prepare_retry", state, runtime)

    _run_node("review", state, runtime)
    _run_node("evaluate", state, runtime)
    _run_node("report", state, runtime)
    return state


@workflow_node("classify")
def _node_classify(state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    runtime.context.classify(state)


@workflow_node("retrieve")
def _node_retrieve(state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    runtime.context.retrieve(state)


@workflow_node("build_prompt")
def _node_build_prompt(state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    runtime.context.build_prompt(state)
    _write_text(runtime.output_dir / "context.md", state.system_prompt)


@workflow_node("generate")
def _node_generate(state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    user_prompt = (
        f"开发者需求:\n{state.user_query}\n\n"
        "请输出 unified diff、实现说明、风险说明和建议校验命令。"
    )
    response = runtime.model.complete(state.system_prompt, user_prompt)
    state.target_model = response.model
    state.ai_diff = response.content
    state.workflow_steps.append({"node": "generate", "attempt": state.retry_count, "model": response.model, "chars": len(response.content)})
    _write_text(runtime.output_dir / "change.patch", state.ai_diff)


@workflow_node("verify")
def _node_verify(state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    verify_results = run_verification(runtime.repo, runtime.config.verification)
    state.verify_report = verification_summary(verify_results)
    state.workflow_steps.append(
        {
            "node": "verify",
            "attempt": state.retry_count,
            "passed": state.verify_report.get("passed"),
            "duration_seconds": state.verify_report.get("duration_seconds"),
            "commands_rejected": state.verify_report.get("commands_rejected"),
        }
    )
    _write_json(runtime.output_dir / "verify_report.json", state.verify_report)


@workflow_node("prepare_retry")
def _node_prepare_retry(state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    results = state.verify_report.get("results", [])
    state.error_log = _format_verify_summary(results)
    runtime.context.build_prompt(state)
    state.workflow_steps.append({"node": "prepare_retry", "next_attempt": state.retry_count + 1})
    _write_text(runtime.output_dir / "context.md", state.system_prompt)


@workflow_node("review")
def _node_review(state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    state.review_report = run_review(state, runtime.context, runtime.model)
    _write_text(runtime.output_dir / "review_report.md", state.review_report)


@workflow_node("evaluate")
def _node_evaluate(state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    state.evaluation = {
        "model": state.target_model,
        "task_type": state.task_type,
        "retrieval_returned": state.search_stats.get("returned", 0),
        "context_used_chars": state.context_summary.get("used_chars", 0),
        "context_budget_chars": state.context_summary.get("budget_chars", 0),
        "verify_passed": bool(state.verify_report.get("passed")),
        "verify_duration_seconds": state.verify_report.get("duration_seconds", 0.0),
        "retry_count": state.retry_count,
        "review_chars": len(state.review_report),
    }
    state.workflow_steps.append({"node": "evaluate", **state.evaluation})


@workflow_node("report")
def _node_report(state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    state.final_report = _build_final_report(state)
    _write_json(runtime.output_dir / "state.json", state.to_dict())
    _write_text(runtime.output_dir / "final_report.md", state.final_report)


def _run_node(name: str, state: DevWorkflowState, runtime: WorkflowRuntime) -> None:
    try:
        node = NODE_REGISTRY[name]
    except KeyError as exc:
        raise RuntimeError(f"workflow node is not registered: {name}") from exc
    node(state, runtime)


def _build_final_report(state: DevWorkflowState) -> str:
    passed = bool(state.verify_report.get("passed"))
    status = "passed" if passed else "failed"
    chunks = "\n".join(f"- {item.source} ({item.kind}, score={item.score})" for item in state.knowledge_chunks) or "- none"
    evaluation = "\n".join(f"- {key}: {value}" for key, value in state.evaluation.items()) or "- none"
    return (
        "# AI Workflow Run Report\n\n"
        f"- 状态: {status}\n"
        f"- 任务类型: {state.task_type}\n"
        f"- 模型: {state.target_model}\n"
        f"- 重试次数: {state.retry_count}\n"
        f"- 人工审批: {'需要' if state.human_approval else '不需要'}\n\n"
        f"## 检索片段\n{chunks}\n\n"
        f"## Evaluation\n{evaluation}\n\n"
        "## 产物\n"
        "- `context.md`: 组装后的模型上下文\n"
        "- `change.patch`: 可审阅的模型输出\n"
        "- `review_report.md`: 独立评审结果\n"
        "- `verify_report.json`: 校验结果\n"
        "- `state.json`: 完整工作流状态\n"
    )


def _format_verify_summary(results: object) -> str:
    if not isinstance(results, list):
        return ""
    try:
        return format_verify_log([_result_from_dict(item) for item in results if isinstance(item, dict)])
    except TypeError:
        return json.dumps(results, ensure_ascii=False, indent=2)


def _result_from_dict(item: dict[str, object]):
    from .state import VerificationResult

    return VerificationResult(
        name=str(item.get("name", "")),
        command=str(item.get("command", "")),
        passed=bool(item.get("passed", False)),
        exit_code=int(item.get("exit_code", 0)),
        stdout=str(item.get("stdout", "")),
        stderr=str(item.get("stderr", "")),
        duration_seconds=float(item.get("duration_seconds", 0.0)),
        policy_allowed=bool(item.get("policy_allowed", True)),
        policy_reason=str(item.get("policy_reason", "")),
    )


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _json_default(value: object) -> object:
    if hasattr(value, "__dict__"):
        return asdict(value)  # type: ignore[arg-type]
    return str(value)
