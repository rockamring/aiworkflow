"""上下文服务。

ContextService 是 Agent OS 里最核心的服务边界之一：它决定任务类型、
检索哪些知识，以及如何控制上下文预算。它不依赖具体工作流状态对象，
因此可以被 CLI、Agent Adapter、API 或测试直接复用。
"""

from __future__ import annotations

from dataclasses import dataclass

from .search import SearchRequest, SearchResponse, SearchService
from .state import KnowledgeChunk


DEFAULT_CONTEXT_BUDGET = 18000


@dataclass(slots=True)
class TaskClassification:
    """一次用户请求的轻量分类结果。"""

    task_type: str
    tags: list[str]
    human_approval: bool


@dataclass(slots=True)
class ContextBuildResult:
    """格式化后的上下文正文和预算统计。"""

    text: str
    summary: dict[str, object]


class ContextService:
    """负责把用户请求转成 Agent 可消费上下文的应用服务。

    它依赖 SearchService 召回知识片段；自身不直接读取文件或访问 Neo4j，
    从而保持上下文编排和存储实现解耦。
    """

    def __init__(
        self,
        search: SearchService,
        char_budget: int = DEFAULT_CONTEXT_BUDGET,
    ):
        self.search = search
        self.char_budget = char_budget

    def classify(self, query: str) -> TaskClassification:
        """根据用户请求返回任务类型、知识标签和人工审批标记。"""

        return classify_task(query)

    def retrieve(self, repo_id: str, query: str, tags: list[str], limit: int = 8) -> SearchResponse:
        """按任务分类结果检索知识片段，并返回检索统计。"""

        return self.search.search(
            SearchRequest(
                repo_id=repo_id,
                query=query,
                tags=tags,
                limit=limit,
            )
        )

    def build_context(self, chunks: list[KnowledgeChunk]) -> ContextBuildResult:
        """按预算格式化检索片段。"""

        text, summary = build_context_block(chunks, self.char_budget)
        return ContextBuildResult(text=text, summary=summary)


def classify_task(query: str) -> TaskClassification:
    """基于关键词做 MVP 级任务分类。

    这是可替换实现：后续可以升级为模型分类、规则配置或项目级分类器。
    """

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
    """把检索片段格式化为上下文块，并返回预算统计。

    当前使用字符预算近似 token 预算，保证 prompt 不会无界膨胀。
    后续接入 tokenizer 后，可以把这里替换为真实 token budget。
    """

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
