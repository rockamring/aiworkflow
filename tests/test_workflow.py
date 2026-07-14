from pathlib import Path

from aiworkflow.config import AppConfig, KnowledgeConfig, RepoConfig, VerificationCommand, VerificationConfig, WorkflowConfig
from aiworkflow.graph import InMemoryGraphStore
from aiworkflow.ingest import ingest_repo
from aiworkflow.model_gateway import MockModelClient
from aiworkflow.workflow import run_workflow


def test_workflow_runs_with_mock_model_and_noop_verification(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("测试项目\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("所有变更都要可审阅。", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    config = AppConfig(
        repo=RepoConfig(include=["**/*.md"], exclude=[]),
        knowledge=KnowledgeConfig(docs_paths=["AGENTS.md", "README.md"]),
        verification=VerificationConfig(commands=[]),
        workflow=WorkflowConfig(max_retries=1, output_dir="runs"),
    )
    store = InMemoryGraphStore()
    report = ingest_repo(repo, config, store)

    state = run_workflow(repo, "实现一个新功能并补充测试", config, store, MockModelClient())

    assert state.repo_meta["repo_id"] == report.repo_id
    assert state.verify_report["passed"] is True
    assert "Mock AI Diff" in state.ai_diff
    assert (tmp_path / state.repo_meta["output_dir"] / "final_report.md").exists()


def test_workflow_retries_failed_verification(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("测试项目\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    config = AppConfig(
        repo=RepoConfig(include=["**/*.md"], exclude=[]),
        knowledge=KnowledgeConfig(docs_paths=["README.md"]),
        verification=VerificationConfig(commands=[VerificationCommand(name="fail", command="python -c \"import sys; sys.exit(1)\"")]),
        workflow=WorkflowConfig(max_retries=2, output_dir="runs"),
    )
    store = InMemoryGraphStore()
    ingest_repo(repo, config, store)

    state = run_workflow(repo, "修复 crash", config, store, MockModelClient())

    assert state.verify_report["passed"] is False
    assert state.retry_count == 2
