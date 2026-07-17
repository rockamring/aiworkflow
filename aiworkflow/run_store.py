"""文件版 Run Store。

Run Store 是 Agent OS 的运行账本：它不替代每次运行目录中的详细产物，
只维护可查询、可审计、可追加的摘要索引。第一版使用 JSONL 文件，避免
在 CLI-first MVP 阶段引入数据库依赖。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from .agent_adapter import artifacts_from_context_pack
from .contracts import AgentEvent, Artifact, PermissionDecision, ToolRequest, ToolResult, utc_now_iso
from .state import ContextPack


@dataclass(slots=True)
class RunRecord:
    """一次 prepare / agent run / tool run 的摘要记录。"""

    run_id: str
    run_type: str
    status: str
    project: str
    repo_id: str
    repo_path: str
    query: str
    task_type: str
    agent: str
    output_dir: str
    artifacts: list[Artifact] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_context_pack(
        cls,
        pack: ContextPack,
        project: str,
        output_dir: str,
        artifacts: list[Artifact] | None = None,
        started_at: str = "",
        finished_at: str = "",
        status: str = "prepared",
    ) -> "RunRecord":
        """从 ContextPack 生成 prepare 运行记录。"""

        return cls(
            run_id=pack.run_id,
            run_type="prepare",
            status=status,
            project=project,
            repo_id=pack.repo_id,
            repo_path=pack.repo_path,
            query=pack.query,
            task_type=pack.task_type,
            agent=pack.agent,
            output_dir=output_dir,
            artifacts=list(artifacts or artifacts_from_context_pack(pack)),
            started_at=started_at or utc_now_iso(),
            finished_at=finished_at or utc_now_iso(),
            metadata={
                "search_stats": pack.search_stats,
                "budget_summary": pack.budget_summary,
            },
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunRecord":
        artifacts = [
            Artifact(
                name=str(item.get("name", "")),
                kind=str(item.get("kind", "")),
                path=str(item.get("path", "")),
                media_type=str(item.get("media_type", "text/plain")),
                produced_by=str(item.get("produced_by", "platform")),
                metadata=dict(item.get("metadata", {}) or {}),
            )
            for item in data.get("artifacts", []) or []
            if isinstance(item, dict)
        ]
        return cls(
            run_id=str(data.get("run_id", "")),
            run_type=str(data.get("run_type", "")),
            status=str(data.get("status", "")),
            project=str(data.get("project", "")),
            repo_id=str(data.get("repo_id", "")),
            repo_path=str(data.get("repo_path", "")),
            query=str(data.get("query", "")),
            task_type=str(data.get("task_type", "")),
            agent=str(data.get("agent", "")),
            output_dir=str(data.get("output_dir", "")),
            artifacts=artifacts,
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at", "")),
            metadata=dict(data.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunEventRecord:
    """一次运行中的可追加事件记录。"""

    run_id: str
    sequence: int
    event_type: str
    source: str
    kind: str
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunEventRecord":
        return cls(
            run_id=str(data.get("run_id", "")),
            sequence=int(data.get("sequence", 0) or 0),
            event_type=str(data.get("event_type", "")),
            source=str(data.get("source", "")),
            kind=str(data.get("kind", "")),
            message=str(data.get("message", "")),
            payload=dict(data.get("payload", {}) or {}),
            created_at=str(data.get("created_at", "") or utc_now_iso()),
        )

    @classmethod
    def from_agent_event(cls, event: AgentEvent, source: str = "agent") -> "RunEventRecord":
        return cls(
            run_id=event.run_id,
            sequence=event.sequence,
            event_type="agent",
            source=source,
            kind=event.kind,
            message=event.message,
            payload=dict(event.payload),
            created_at=event.created_at,
        )

    @classmethod
    def from_tool_request(cls, request: ToolRequest) -> "RunEventRecord":
        return cls(
            run_id=request.run_id,
            sequence=0,
            event_type="tool_request",
            source=request.requested_by,
            kind="tool.requested",
            message=f"{request.tool} requested",
            payload=request.to_dict(),
            created_at=request.created_at,
        )

    @classmethod
    def from_tool_result(cls, result: ToolResult) -> "RunEventRecord":
        if not result.allowed:
            kind = "tool.denied"
        elif result.success:
            kind = "tool.succeeded"
        else:
            kind = "tool.failed"
        return cls(
            run_id=result.run_id,
            sequence=0,
            event_type="tool_result",
            source="tool",
            kind=kind,
            message=result.error or result.output,
            payload=result.to_dict(),
            created_at=result.finished_at,
        )

    @classmethod
    def from_permission_decision(
        cls,
        run_id: str,
        decision: PermissionDecision,
        sequence: int = 0,
    ) -> "RunEventRecord":
        return cls(
            run_id=run_id,
            sequence=sequence,
            event_type="permission",
            source="permission",
            kind="permission.allowed" if decision.allowed else "permission.denied",
            message=decision.reason,
            payload=decision.to_dict(),
            created_at=decision.decided_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunStore:
    """基于 `index.jsonl` 的运行索引。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.index_path = self.root / "index.jsonl"
        self.events_path = self.root / "events.jsonl"

    def append(self, record: RunRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def list(self, project: str = "", limit: int | None = None) -> list[RunRecord]:
        records = [record for record in self._read_records() if not project or record.project == project]
        if limit is not None:
            return records[-limit:]
        return records

    def find(self, run_id: str) -> RunRecord | None:
        for record in reversed(self._read_records()):
            if record.run_id == run_id:
                return record
        return None

    def append_event(self, event: RunEventRecord) -> RunEventRecord:
        self.root.mkdir(parents=True, exist_ok=True)
        if event.sequence <= 0:
            event = replace(event, sequence=self._next_event_sequence(event.run_id))
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def list_events(
        self,
        run_id: str = "",
        event_type: str = "",
        source: str = "",
        limit: int | None = None,
    ) -> list[RunEventRecord]:
        events = [
            event
            for event in self._read_events()
            if (not run_id or event.run_id == run_id)
            and (not event_type or event.event_type == event_type)
            and (not source or event.source == source)
        ]
        if limit is not None:
            return events[-limit:]
        return events

    def _read_records(self) -> list[RunRecord]:
        if not self.index_path.exists():
            return []
        records = []
        for raw_line in self.index_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            records.append(RunRecord.from_dict(json.loads(line)))
        return records

    def _read_events(self) -> list[RunEventRecord]:
        if not self.events_path.exists():
            return []
        events = []
        for raw_line in self.events_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            events.append(RunEventRecord.from_dict(json.loads(line)))
        return events

    def _next_event_sequence(self, run_id: str) -> int:
        existing = [event.sequence for event in self._read_events() if event.run_id == run_id]
        return (max(existing) if existing else 0) + 1


def run_store_root_for_output_dir(output_dir: str | Path, project: str = "") -> Path:
    """根据运行输出目录推导共享 Run Store 根目录。"""

    path = Path(output_dir)
    if project and path.name == project:
        return path.parent
    return path
