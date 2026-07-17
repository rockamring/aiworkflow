"""Agent OS 运行时契约。

这些 dataclass 只定义平台和 Agent / Tool / Permission 层之间交换的数据
形状，不启动任何具体 Agent，也不执行真实工具。Codex CLI、Claude Code、
OpenHands 或内部 Agent 后续都应通过这些契约接入平台。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .state import ContextPack


def utc_now_iso() -> str:
    """返回便于 JSON 序列化和审计排序的 UTC 时间。"""

    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Artifact:
    """一次 prepare、Agent run 或 Tool call 产生的文件产物。"""

    name: str
    kind: str
    path: str
    media_type: str = "text/plain"
    produced_by: str = "platform"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentRunRequest:
    """平台请求某个 Agent 执行任务的输入契约。"""

    run_id: str
    agent: str
    adapter: str
    repo_path: str
    context_pack: ContextPack
    mode: str = "task"
    limits: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentEvent:
    """Agent 运行期间的流式事件。"""

    run_id: str
    sequence: int
    kind: str
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentRunResult:
    """某次 Agent 运行结束后的统一结果。"""

    run_id: str
    agent: str
    adapter: str
    status: str
    started_at: str
    finished_at: str
    events: list[AgentEvent] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    summary: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Capability:
    """平台暴露给 Agent 请求的受控能力。"""

    name: str
    description: str = ""
    risk_level: str = "low"
    required_permission: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PermissionDecision:
    """Permission Service 对某次能力请求的决策。"""

    subject: str
    capability: str
    resource: str
    allowed: bool
    reason: str
    approval_required: bool = False
    policy: str = "default"
    decided_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolRequest:
    """Agent 请求平台代执行某个工具能力。"""

    run_id: str
    request_id: str
    requested_by: str
    capability: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    cwd: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolResult:
    """平台完成或拒绝某次工具请求后的统一结果。"""

    run_id: str
    request_id: str
    tool: str
    capability: str
    allowed: bool
    success: bool
    output: str = ""
    error: str = ""
    artifacts: list[Artifact] = field(default_factory=list)
    permission: PermissionDecision | None = None
    finished_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
