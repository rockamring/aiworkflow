from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class KnowledgeChunk:
    source: str
    kind: str
    text: str
    score: float = 1.0
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerificationResult:
    name: str
    command: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


@dataclass(slots=True)
class DevWorkflowState:
    user_query: str
    repo_meta: dict[str, Any]
    file_context: str = ""
    error_log: str = ""
    task_type: str = "unknown"
    target_model: str = "mock"
    required_knowledge_tags: list[str] = field(default_factory=list)
    knowledge_chunks: list[KnowledgeChunk] = field(default_factory=list)
    system_prompt: str = ""
    ai_diff: str = ""
    verify_report: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    human_approval: bool = False
    final_report: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
