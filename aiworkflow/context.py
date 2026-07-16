from __future__ import annotations

from dataclasses import dataclass

from .prompt import PromptService
from .search import SearchRequest, SearchService
from .state import DevWorkflowState, KnowledgeChunk


DEFAULT_CONTEXT_BUDGET = 18000


@dataclass(slots=True)
class TaskClassification:
    task_type: str
    tags: list[str]
    human_approval: bool


class ContextService:
    def __init__(
        self,
        search: SearchService,
        prompts: PromptService | None = None,
        char_budget: int = DEFAULT_CONTEXT_BUDGET,
    ):
        self.search = search
        self.prompts = prompts or PromptService()
        self.char_budget = char_budget

    def classify(self, state: DevWorkflowState) -> None:
        classification = classify_task(state.user_query)
        state.task_type = classification.task_type
        state.required_knowledge_tags = classification.tags
        state.human_approval = classification.human_approval
        state.workflow_steps.append(
            {
                "node": "classify",
                "task_type": state.task_type,
                "tags": state.required_knowledge_tags,
                "human_approval": state.human_approval,
            }
        )

    def retrieve(self, state: DevWorkflowState) -> None:
        response = self.search.search(
            SearchRequest(
                repo_id=str(state.repo_meta["repo_id"]),
                query=state.user_query,
                tags=state.required_knowledge_tags,
                limit=8,
            )
        )
        state.knowledge_chunks = response.chunks
        state.search_stats = response.stats
        state.workflow_steps.append({"node": "retrieve", **response.stats})

    def build_prompt(self, state: DevWorkflowState) -> None:
        bundle = self.prompts.load_bundle(state.task_type)
        context_block, summary = build_context_block(state.knowledge_chunks, self.char_budget)
        error_block = f"\n\n## 上轮校验失败\n{state.error_log}" if state.error_log else ""
        values = {
            "task_type": state.task_type,
            "knowledge_tags": ", ".join(state.required_knowledge_tags),
            "context_block": context_block,
            "error_block": error_block,
            "task_prompt": bundle.task,
        }
        state.system_prompt = self.prompts.render(bundle.system, values)
        state.context_summary = summary
        state.workflow_steps.append({"node": "build_prompt", **summary})

    def build_review_prompt(self, state: DevWorkflowState) -> str:
        bundle = self.prompts.load_bundle(state.task_type)
        return self.prompts.render(
            bundle.review,
            {
                "task_type": state.task_type,
                "knowledge_tags": ", ".join(state.required_knowledge_tags),
                "context_summary": state.context_summary,
                "change_patch": state.ai_diff,
            },
        )


def classify_task(query: str) -> TaskClassification:
    text = query.lower()
    rules = [
        ("crash_fix", ["crash", "崩溃", "exception", "traceback"], ["crash", "debugging"]),
        ("performance", ["performance", "性能", "slow", "优化"], ["performance"]),
        ("feature", ["feature", "新增", "实现", "add"], ["architecture"]),
        ("review", ["review", "评审", "pr", "diff"], ["style", "test"]),
        ("refactor", ["refactor", "重构", "架构"], ["architecture", "test"]),
    ]
    for task_type, needles, tags in rules:
        if any(needle in text for needle in needles):
            return TaskClassification(task_type, tags, _needs_human_approval(text))
    return TaskClassification("general", ["architecture", "test"], _needs_human_approval(text))


def build_context_block(chunks: list[KnowledgeChunk], char_budget: int = DEFAULT_CONTEXT_BUDGET) -> tuple[str, dict[str, object]]:
    if not chunks:
        return "未检索到相关知识片段。", {
            "budget_chars": char_budget,
            "used_chars": 0,
            "chunks_total": 0,
            "chunks_included": 0,
            "truncated": False,
        }

    used = 0
    included = []
    truncated = False
    for chunk in chunks:
        text = _format_chunk(chunk)
        if used + len(text) > char_budget:
            remaining = max(char_budget - used, 0)
            if remaining > 200:
                included.append(text[:remaining] + "\n...[上下文已截断]")
                used = char_budget
            truncated = True
            break
        included.append(text)
        used += len(text)
    return "\n\n".join(included), {
        "budget_chars": char_budget,
        "used_chars": used,
        "chunks_total": len(chunks),
        "chunks_included": len(included),
        "truncated": truncated,
    }


def _format_chunk(chunk: KnowledgeChunk) -> str:
    tags = ", ".join(chunk.tags) if chunk.tags else "none"
    return (
        f"### 来源: {chunk.source}\n"
        f"- kind: {chunk.kind}\n"
        f"- score: {chunk.score}\n"
        f"- tags: {tags}\n"
        f"- chars: {len(chunk.text)}\n\n"
        f"{chunk.text}"
    )


def _needs_human_approval(text: str) -> bool:
    return any(needle in text for needle in ["底层", "core", "security", "权限", "delete", "删除"])
