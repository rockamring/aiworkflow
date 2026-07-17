"""Context Pack 状态数据结构。

这些 dataclass 是 prepare 流程和运行产物之间的公共数据契约。它们保持
可序列化，方便后续审计、复现、Dashboard 分析，以及 Agent Adapter 复用。
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeChunk":
        return cls(
            source=str(data.get("source", "")),
            kind=str(data.get("kind", "")),
            text=str(data.get("text", "")),
            score=float(data.get("score", 1.0) or 1.0),
            tags=[str(item) for item in data.get("tags", []) or []],
        )


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
class ContextPack:
    """交给 Agent 的稳定上下文包契约。"""

    run_id: str
    repo_id: str
    repo_path: str
    query: str
    task_type: str = "unknown"
    agent: str = "generic"
    knowledge_tags: list[str] = field(default_factory=list)
    context_chunks: list[KnowledgeChunk] = field(default_factory=list)
    verification_commands: list[dict[str, str]] = field(default_factory=list)
    prompt_text: str = ""
    search_stats: dict[str, Any] = field(default_factory=dict)
    budget_summary: dict[str, Any] = field(default_factory=dict)
    generated_files: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextPack":
        chunks = [
            KnowledgeChunk.from_dict(item)
            for item in data.get("context_chunks", []) or []
            if isinstance(item, dict)
        ]
        verification_commands = [
            {str(key): str(value) for key, value in item.items()}
            for item in data.get("verification_commands", []) or []
            if isinstance(item, dict)
        ]
        return cls(
            run_id=str(data.get("run_id", "")),
            repo_id=str(data.get("repo_id", "")),
            repo_path=str(data.get("repo_path", "")),
            query=str(data.get("query", "")),
            task_type=str(data.get("task_type", "unknown") or "unknown"),
            agent=str(data.get("agent", "generic") or "generic"),
            knowledge_tags=[str(item) for item in data.get("knowledge_tags", []) or []],
            context_chunks=chunks,
            verification_commands=verification_commands,
            prompt_text=str(data.get("prompt_text", "")),
            search_stats=dict(data.get("search_stats", {}) or {}),
            budget_summary=dict(data.get("budget_summary", {}) or {}),
            generated_files={str(key): str(value) for key, value in (data.get("generated_files", {}) or {}).items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ContextPackState:
    """一次 prepare 流程的过程状态和审计轨迹。"""

    user_query: str
    repo_meta: dict[str, Any]
    agent: str
    task_type: str = "unknown"
    required_knowledge_tags: list[str] = field(default_factory=list)
    knowledge_chunks: list[KnowledgeChunk] = field(default_factory=list)
    verification_commands: list[dict[str, str]] = field(default_factory=list)
    search_stats: dict[str, Any] = field(default_factory=dict)
    budget_summary: dict[str, Any] = field(default_factory=dict)
    context_block: str = ""
    agent_prompt: str = ""
    context_pack: ContextPack | None = None
    workflow_steps: list[dict[str, Any]] = field(default_factory=list)
    human_approval: bool = False
    generated_files: dict[str, str] = field(default_factory=dict)
    final_report: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
