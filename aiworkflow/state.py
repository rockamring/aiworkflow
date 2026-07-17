"""工作流状态数据结构。

这些 dataclass 是 workflow 节点之间传递和最终写入 state.json 的公共
状态形状。它们应保持可序列化，方便后续审计、复现和 Dashboard 分析。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class KnowledgeChunk:
    """一次检索返回的上下文片段。"""

    source: str
    kind: str
    text: str
    score: float = 1.0
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerificationResult:
    """单条验证命令的执行结果和安全策略决策。"""

    name: str
    command: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    policy_allowed: bool = True
    policy_reason: str = ""


@dataclass(slots=True)
class DevWorkflowState:
    """一次 AI workflow 的完整状态快照。

    workflow 中的每个节点都只修改这个状态对象的一部分，最终整体写入
    state.json，作为可审计、可复现的运行记录。
    """

    user_query: str
    repo_meta: dict[str, Any]
    file_context: str = ""
    error_log: str = ""
    task_type: str = "unknown"
    target_model: str = "mock"
    required_knowledge_tags: list[str] = field(default_factory=list)
    knowledge_chunks: list[KnowledgeChunk] = field(default_factory=list)
    search_stats: dict[str, Any] = field(default_factory=dict)
    context_summary: dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    ai_diff: str = ""
    review_report: str = ""
    verify_report: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    workflow_steps: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    human_approval: bool = False
    final_report: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
