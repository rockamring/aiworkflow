from pathlib import Path

from aiworkflow.contracts import AgentEvent, Artifact, PermissionDecision, ToolRequest, ToolResult
from aiworkflow.run_store import RunEventRecord, RunRecord, RunStore, run_store_root_for_output_dir
from aiworkflow.state import ContextPack


def _pack(run_id: str = "run-1") -> ContextPack:
    return ContextPack(
        run_id=run_id,
        repo_id="repo-1",
        repo_path="G:/repo",
        query="修复 Renderer crash",
        task_type="crash_fix",
        agent="codex",
        generated_files={
            "agent_prompt": "runs/my_game/run-1/agent_prompt.md",
            "manifest": "runs/my_game/run-1/manifest.json",
        },
    )


def test_run_store_appends_jsonl_records(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    record = RunRecord.from_context_pack(_pack(), project="my_game", output_dir="runs/my_game/run-1")

    store.append(record)

    index = tmp_path / "runs" / "index.jsonl"
    assert index.exists()
    assert len(index.read_text(encoding="utf-8").splitlines()) == 1


def test_run_store_lists_by_project_and_limit(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    store.append(RunRecord.from_context_pack(_pack("run-1"), project="a", output_dir="runs/a/run-1"))
    store.append(RunRecord.from_context_pack(_pack("run-2"), project="b", output_dir="runs/b/run-2"))
    store.append(RunRecord.from_context_pack(_pack("run-3"), project="a", output_dir="runs/a/run-3"))

    assert [item.run_id for item in store.list(project="a")] == ["run-1", "run-3"]
    assert [item.run_id for item in store.list(limit=2)] == ["run-2", "run-3"]


def test_run_store_finds_latest_matching_run_id(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    store.append(RunRecord.from_context_pack(_pack("run-1"), project="a", output_dir="runs/a/run-1", status="old"))
    store.append(RunRecord.from_context_pack(_pack("run-1"), project="a", output_dir="runs/a/run-1", status="new"))

    record = store.find("run-1")

    assert record is not None
    assert record.status == "new"
    assert store.find("missing") is None


def test_run_store_appends_event_jsonl_records(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    event = RunEventRecord(
        run_id="run-1",
        sequence=1,
        event_type="platform",
        source="prepare",
        kind="prepare.finished",
        payload={"output_dir": "runs/run-1"},
    )

    stored = store.append_event(event)

    index = tmp_path / "runs" / "events.jsonl"
    assert index.exists()
    assert len(index.read_text(encoding="utf-8").splitlines()) == 1
    assert stored.sequence == 1


def test_run_store_assigns_event_sequence_per_run_id(tmp_path: Path):
    store = RunStore(tmp_path / "runs")

    first = store.append_event(RunEventRecord(run_id="run-1", sequence=0, event_type="platform", source="prepare", kind="a"))
    other = store.append_event(RunEventRecord(run_id="run-2", sequence=0, event_type="platform", source="prepare", kind="b"))
    second = store.append_event(RunEventRecord(run_id="run-1", sequence=0, event_type="agent", source="agent", kind="c"))

    assert first.sequence == 1
    assert other.sequence == 1
    assert second.sequence == 2


def test_run_store_lists_events_by_run_type_source_and_limit(tmp_path: Path):
    store = RunStore(tmp_path / "runs")
    store.append_event(RunEventRecord(run_id="run-1", sequence=0, event_type="platform", source="prepare", kind="prepare.finished"))
    store.append_event(RunEventRecord(run_id="run-1", sequence=0, event_type="agent", source="dry_run", kind="started"))
    store.append_event(RunEventRecord(run_id="run-2", sequence=0, event_type="agent", source="dry_run", kind="started"))
    store.append_event(RunEventRecord(run_id="run-1", sequence=0, event_type="agent", source="codex_cli", kind="finished"))

    assert [item.kind for item in store.list_events(run_id="run-1", event_type="agent")] == ["started", "finished"]
    assert [item.run_id for item in store.list_events(source="dry_run")] == ["run-1", "run-2"]
    assert [item.kind for item in store.list_events(run_id="run-1", limit=2)] == ["started", "finished"]


def test_run_event_record_converts_runtime_contracts():
    agent_event = AgentEvent(run_id="run-1", sequence=7, kind="started", message="hello", payload={"adapter": "dry_run"})
    tool_request = ToolRequest(
        run_id="run-1",
        request_id="tool-1",
        requested_by="codex",
        capability="verify",
        tool="pytest",
        arguments={"target": "tests"},
        cwd="G:/repo",
    )
    permission = PermissionDecision(
        subject="codex",
        capability="verify",
        resource="G:/repo",
        allowed=True,
        reason="allowed by profile",
    )
    tool_result = ToolResult(
        run_id="run-1",
        request_id="tool-1",
        tool="pytest",
        capability="verify",
        allowed=True,
        success=True,
        output="ok",
        permission=permission,
    )

    agent_record = RunEventRecord.from_agent_event(agent_event, source="dry_run")
    request_record = RunEventRecord.from_tool_request(tool_request)
    result_record = RunEventRecord.from_tool_result(tool_result)
    permission_record = RunEventRecord.from_permission_decision("run-1", permission)

    assert agent_record.sequence == 7
    assert agent_record.event_type == "agent"
    assert agent_record.source == "dry_run"
    assert request_record.event_type == "tool_request"
    assert request_record.payload["request_id"] == "tool-1"
    assert result_record.kind == "tool.succeeded"
    assert result_record.payload["permission"]["allowed"] is True
    assert permission_record.kind == "permission.allowed"


def test_run_event_record_round_trips_dict_payload():
    event = RunEventRecord(
        run_id="run-1",
        sequence=3,
        event_type="platform",
        source="prepare",
        kind="prepare.finished",
        message="done",
        payload={"nested": {"value": 1}},
        created_at="2026-07-17T00:00:00+00:00",
    )

    restored = RunEventRecord.from_dict(event.to_dict())

    assert restored.run_id == "run-1"
    assert restored.sequence == 3
    assert restored.payload == {"nested": {"value": 1}}
    assert restored.created_at == "2026-07-17T00:00:00+00:00"


def test_run_record_preserves_artifacts():
    artifact = Artifact(name="manifest", kind="manifest", path="runs/run-1/manifest.json", media_type="application/json")
    record = RunRecord.from_context_pack(_pack(), project="my_game", output_dir="runs/my_game/run-1", artifacts=[artifact])

    data = record.to_dict()
    restored = RunRecord.from_dict(data)

    assert restored.artifacts[0].name == "manifest"
    assert restored.artifacts[0].media_type == "application/json"


def test_run_store_root_for_project_output_dir():
    assert run_store_root_for_output_dir("runs/my_game", "my_game") == Path("runs")
    assert run_store_root_for_output_dir("runs", "") == Path("runs")
    assert run_store_root_for_output_dir("custom/my_game", "my_game") == Path("custom")
