import argparse
from pathlib import Path

import pytest

from aiworkflow.cli import _resolve_command_project
from aiworkflow.config import AgentConfig, AppConfig, ProjectConfig, WorkflowConfig, load_config
from aiworkflow.errors import AIWorkflowError, ConfigError
from aiworkflow.projects import config_for_project, resolve_project


def test_load_config_reads_project_registry(tmp_path: Path):
    repo = tmp_path / "game"
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        f"""
projects:
  my_game:
    repo: "{repo.as_posix()}"
    agent: "claude-code"
    output_dir: "runs/my_game"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.projects["my_game"].repo == repo.as_posix()
    assert config.projects["my_game"].agent == "claude-code"
    assert config.projects["my_game"].output_dir == "runs/my_game"


def test_resolve_project_uses_default_agent_and_output_dir():
    config = AppConfig(
        agent=AgentConfig(default="codex"),
        workflow=WorkflowConfig(output_dir="runs"),
        projects={"demo": ProjectConfig(repo="G:/demo")},
    )

    selection = resolve_project(config, "demo")

    assert selection.repo == Path("G:/demo")
    assert selection.agent == "codex"
    assert selection.output_dir == str(Path("runs") / "demo")


def test_config_for_project_overrides_output_dir():
    config = AppConfig(
        workflow=WorkflowConfig(output_dir="runs"),
        projects={"demo": ProjectConfig(repo="G:/demo", output_dir="custom/demo")},
    )
    selection = resolve_project(config, "demo")

    project_config = config_for_project(config, selection)

    assert config.workflow.output_dir == "runs"
    assert project_config.workflow.output_dir == "custom/demo"


def test_resolve_project_reports_known_projects():
    config = AppConfig(projects={"demo": ProjectConfig(repo="G:/demo")})

    with pytest.raises(ConfigError) as excinfo:
        resolve_project(config, "missing")

    assert "demo" in str(excinfo.value)


def test_cli_project_resolution_rejects_ambiguous_repo_and_project():
    config = AppConfig(projects={"demo": ProjectConfig(repo="G:/demo")})
    args = argparse.Namespace(repo=Path("G:/other"), project="demo")

    with pytest.raises(AIWorkflowError):
        _resolve_command_project(args, config)


def test_cli_project_resolution_returns_project_defaults():
    config = AppConfig(
        agent=AgentConfig(default="codex"),
        projects={"demo": ProjectConfig(repo="G:/demo", agent="claude-code")},
    )
    args = argparse.Namespace(repo=None, project="demo")

    repo, project_config, agent, project = _resolve_command_project(args, config)

    assert repo == Path("G:/demo")
    assert project_config.workflow.output_dir == str(Path("runs") / "demo")
    assert agent == "claude-code"
    assert project == "demo"
