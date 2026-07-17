import json
from pathlib import Path

from aiworkflow.agent_pack import prepare_context_pack
from aiworkflow.config import AppConfig, ContextConfig, KnowledgeConfig, RepoConfig, VerificationCommand, VerificationConfig, WorkflowConfig
from aiworkflow.graph import InMemoryGraphStore
from aiworkflow.ingest import ingest_repo
from aiworkflow.run_store import RunStore


def test_prepare_context_pack_writes_agent_outputs(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("Renderer 模块说明。\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("所有变更都要可审阅。", encoding="utf-8")
    (repo / "Renderer.cpp").write_text("class Renderer {};\nvoid Renderer::Init() {}\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    config = AppConfig(
        repo=RepoConfig(include=["**/*.md", "**/*.cpp"], exclude=[]),
        knowledge=KnowledgeConfig(docs_paths=["AGENTS.md", "README.md"]),
        context=ContextConfig(budget_chars=2000, search_limit=8),
        verification=VerificationConfig(commands=[VerificationCommand(name="tests", command="python -m pytest")]),
        workflow=WorkflowConfig(output_dir="runs"),
    )
    store = InMemoryGraphStore()
    ingest_repo(repo, config, store)

    state = prepare_context_pack(repo, "修复 Renderer crash", config, store, agent="codex")
    output_dir = tmp_path / state.repo_meta["output_dir"]

    assert state.context_pack is not None
    assert state.context_pack.agent == "codex"
    assert state.context_pack.task_type == "crash_fix"
    assert "python -m pytest" in state.agent_prompt
    assert "Renderer" in state.agent_prompt
    assert (output_dir / "agent_prompt.md").exists()
    assert (output_dir / "context.md").exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "state.json").exists()
    assert (output_dir / "final_report.md").exists()
    assert not (output_dir / "change.patch").exists()
    assert not (output_dir / "review_report.md").exists()
    assert not (output_dir / "verify_report.json").exists()

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == state.repo_meta["run_id"]
    assert manifest["repo_id"] == state.repo_meta["repo_id"]
    assert manifest["query"] == "修复 Renderer crash"
    assert manifest["verification_commands"] == [{"name": "tests", "command": "python -m pytest"}]
    assert set(manifest["generated_files"]) >= {"agent_prompt", "context", "manifest", "state", "final_report"}


def test_prepare_context_pack_registers_run_store_record(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("Renderer 模块说明。\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    config = AppConfig(
        repo=RepoConfig(include=["**/*.md"], exclude=[]),
        knowledge=KnowledgeConfig(docs_paths=["README.md"]),
        workflow=WorkflowConfig(output_dir="runs/my_game"),
    )
    store = InMemoryGraphStore()
    ingest_repo(repo, config, store)

    state = prepare_context_pack(repo, "修复 Renderer crash", config, store, agent="codex", project="my_game")

    run_store = RunStore(tmp_path / "runs")
    record = run_store.find(state.repo_meta["run_id"])
    events = run_store.list_events(run_id=state.repo_meta["run_id"])

    assert record is not None
    assert record.project == "my_game"
    assert record.run_id == state.repo_meta["run_id"]
    assert record.repo_id == state.repo_meta["repo_id"]
    assert record.agent == "codex"
    assert record.status == "prepared"
    assert record.output_dir == state.repo_meta["output_dir"]
    assert {artifact.name for artifact in record.artifacts} >= {"agent_prompt", "manifest", "state"}
    assert len(events) == 1
    assert events[0].event_type == "platform"
    assert events[0].source == "prepare"
    assert events[0].kind == "prepare.finished"
    assert events[0].payload["output_dir"] == state.repo_meta["output_dir"]
