from pathlib import Path

from aiworkflow.config import AppConfig, KnowledgeConfig, RepoConfig
from aiworkflow.graph import InMemoryGraphStore
from aiworkflow.ingest import ingest_repo


def test_ingest_repo_indexes_files_symbols_and_rules(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("必须运行 pytest。", encoding="utf-8")
    (repo / "app.py").write_text("class Service:\n    def run(self):\n        return 1\n", encoding="utf-8")

    config = AppConfig(
        repo=RepoConfig(include=["**/*.py", "**/*.md"], exclude=[]),
        knowledge=KnowledgeConfig(docs_paths=["AGENTS.md"]),
    )
    store = InMemoryGraphStore()

    report = ingest_repo(repo, config, store)

    assert report.files_indexed == 2
    assert report.symbols_indexed == 2
    assert report.documents_indexed == 1
    assert store.search(report.repo_id, "Service pytest", ["test"])
