import json
import sys
from pathlib import Path

from aiworkflow.cli import main
from aiworkflow.run_store import RunEventRecord, RunRecord, RunStore
from aiworkflow.state import ContextPack


def test_runs_events_cli_outputs_filtered_json(tmp_path: Path, capsys):
    output_dir = tmp_path / "runs"
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
workflow:
  output_dir: "{output_dir.as_posix()}"
""",
        encoding="utf-8",
    )
    store = RunStore(output_dir)
    store.append_event(RunEventRecord(run_id="run-1", sequence=0, event_type="platform", source="prepare", kind="prepare.finished"))
    store.append_event(RunEventRecord(run_id="run-1", sequence=0, event_type="agent", source="dry_run", kind="started"))
    store.append_event(RunEventRecord(run_id="run-1", sequence=0, event_type="agent", source="dry_run", kind="finished"))
    store.append_event(RunEventRecord(run_id="run-2", sequence=0, event_type="agent", source="dry_run", kind="started"))

    exit_code = main(
        [
            "--config",
            str(config_path),
            "runs",
            "events",
            "run-1",
            "--type",
            "agent",
            "--source",
            "dry_run",
            "--limit",
            "1",
        ]
    )

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 1
    assert data[0]["run_id"] == "run-1"
    assert data[0]["event_type"] == "agent"
    assert data[0]["source"] == "dry_run"
    assert data[0]["kind"] == "finished"


def test_agent_run_cli_executes_configured_adapter_and_records_events(tmp_path: Path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    output_dir = tmp_path / "runs"
    run_dir = output_dir / "run-1"
    run_dir.mkdir(parents=True)
    manifest_path = run_dir / "manifest.json"
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "workflow": {"output_dir": output_dir.as_posix()},
                "agent": {
                    "profiles": {
                        "codex": {
                            "adapter": "codex_cli",
                            "command": Path(sys.executable).as_posix(),
                            "args": ["-c", "import sys; print('ECHO:' + sys.stdin.read())"],
                            "input_mode": "stdin",
                            "output_mode": "stream",
                            "timeout_seconds": 5,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    pack = ContextPack(
        run_id="run-1",
        repo_id="repo-1",
        repo_path=str(repo),
        query="修复 Renderer crash",
        task_type="crash_fix",
        agent="codex",
        prompt_text="Agent prompt",
        generated_files={"manifest": str(manifest_path)},
    )
    manifest_path.write_text(json.dumps(pack.to_dict(), ensure_ascii=False), encoding="utf-8")
    store = RunStore(output_dir)
    store.append(RunRecord.from_context_pack(pack, project="", output_dir=str(run_dir)))

    exit_code = main(["--config", str(config_path), "agent", "run", "run-1"])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "succeeded"
    events = store.list_events(run_id="run-1", event_type="agent", source="codex_cli")
    assert [event.kind for event in events] == ["started", "stdout", "finished"]
    assert "ECHO:Agent prompt" in events[1].message
    agent_records = [record for record in store.list() if record.run_type == "agent"]
    assert agent_records[-1].status == "succeeded"
    assert agent_records[-1].metadata["adapter"] == "codex_cli"


def test_agent_run_cli_can_force_dry_run_adapter(tmp_path: Path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    output_dir = tmp_path / "runs"
    run_dir = output_dir / "run-1"
    run_dir.mkdir(parents=True)
    manifest_path = run_dir / "manifest.json"
    config_path = tmp_path / "workflow.json"
    config_path.write_text(json.dumps({"workflow": {"output_dir": output_dir.as_posix()}}), encoding="utf-8")
    pack = ContextPack(
        run_id="run-1",
        repo_id="repo-1",
        repo_path=str(repo),
        query="修复 Renderer crash",
        task_type="crash_fix",
        agent="codex",
        prompt_text="Agent prompt",
        generated_files={"manifest": str(manifest_path)},
    )
    manifest_path.write_text(json.dumps(pack.to_dict(), ensure_ascii=False), encoding="utf-8")
    store = RunStore(output_dir)
    store.append(RunRecord.from_context_pack(pack, project="", output_dir=str(run_dir)))

    exit_code = main(["--config", str(config_path), "agent", "run", "run-1", "--adapter", "dry_run"])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "dry_run"
    assert [event.kind for event in store.list_events(run_id="run-1", event_type="agent", source="dry_run")] == [
        "started",
        "finished",
    ]


def test_agent_run_cli_reports_missing_run_record(tmp_path: Path, capsys):
    config_path = tmp_path / "workflow.json"
    config_path.write_text(json.dumps({"workflow": {"output_dir": (tmp_path / "runs").as_posix()}}), encoding="utf-8")

    exit_code = main(["--config", str(config_path), "agent", "run", "missing"])

    assert exit_code == 2
    assert "未找到运行记录" in capsys.readouterr().err
