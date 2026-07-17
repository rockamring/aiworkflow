from pathlib import Path

from aiworkflow.config import AppConfig, load_config, resolve_agent_profile


def test_default_codex_profile_describes_runtime_entrypoint():
    profile = resolve_agent_profile(AppConfig(), "codex")

    assert profile.prompt_style == "codex"
    assert profile.adapter == "codex_cli"
    assert profile.command == "codex"
    assert profile.input_mode == "stdin"
    assert profile.output_mode == "stream"


def test_legacy_string_profile_keeps_runtime_defaults(tmp_path: Path):
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        """
agent:
  profiles:
    codex: "codex"
""",
        encoding="utf-8",
    )

    profile = resolve_agent_profile(load_config(config_path), "codex")

    assert profile.prompt_style == "codex"
    assert profile.adapter == "codex_cli"
    assert profile.command == "codex"


def test_object_profile_loads_runtime_fields(tmp_path: Path):
    config_path = tmp_path / "workflow.yaml"
    config_path.write_text(
        """
agent:
  profiles:
    codex:
      prompt_style: "codex"
      adapter: "codex_cli"
      command: "codex"
      args:
        - "--model"
        - 5
      input_mode: "stdin"
      output_mode: "stream"
      extra_instructions:
        - "Prefer the provided Context Pack."
      default_permissions:
        - "read_repo"
        - "write_artifacts"
      timeout_seconds: "123"
      env:
        AIWORKFLOW_MODE: "test"
        RETRY_COUNT: 2
""",
        encoding="utf-8",
    )

    profile = resolve_agent_profile(load_config(config_path), "codex")

    assert profile.args == ["--model", "5"]
    assert profile.extra_instructions == ["Prefer the provided Context Pack."]
    assert profile.default_permissions == ["read_repo", "write_artifacts"]
    assert profile.timeout_seconds == 123
    assert profile.env == {"AIWORKFLOW_MODE": "test", "RETRY_COUNT": "2"}
