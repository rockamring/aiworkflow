from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigError


ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


@dataclass(slots=True)
class RepoConfig:
    include: list[str] = field(default_factory=lambda: ["**/*"])
    exclude: list[str] = field(default_factory=lambda: [".git/**", "node_modules/**", ".venv/**", "venv/**", "runs/**"])


@dataclass(slots=True)
class KnowledgeConfig:
    docs_paths: list[str] = field(default_factory=lambda: ["docs", "knowledge", "skills", "AGENTS.md", "README.md"])


@dataclass(slots=True)
class Neo4jConfig:
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "aiworkflow-local"


@dataclass(slots=True)
class ModelConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = "mock"
    timeout_seconds: int = 90


@dataclass(slots=True)
class VerificationCommand:
    name: str
    command: str


@dataclass(slots=True)
class VerificationConfig:
    commands: list[VerificationCommand] = field(default_factory=list)


@dataclass(slots=True)
class WorkflowConfig:
    max_retries: int = 3
    output_dir: str = "runs"


@dataclass(slots=True)
class AppConfig:
    repo: RepoConfig = field(default_factory=RepoConfig)
    knowledge: KnowledgeConfig = field(default_factory=KnowledgeConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: Path | None = None) -> AppConfig:
    load_env_file(Path(".env"))
    config_path = resolve_config_path(path)
    data: dict[str, Any] = {}
    if config_path and config_path.exists():
        data = _load_mapping_file(config_path)
    elif config_path and not config_path.exists():
        raise ConfigError(f"配置文件不存在: {config_path}")

    data = _expand_env(data)
    return _build_config(data)


def resolve_config_path(path: Path | None) -> Path | None:
    if path is not None:
        return path
    env_path = os.getenv("AIWORKFLOW_CONFIG")
    if env_path:
        return Path(env_path)
    preferred = Path("config/workflow.yaml")
    if preferred.exists():
        return preferred
    example = Path("config/workflow.example.yaml")
    if example.exists():
        return example
    return None


def _load_mapping_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        value = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ConfigError("读取 YAML 配置需要安装 PyYAML，或改用 JSON 配置文件。") from exc
        value = yaml.safe_load(text) or {}
    if not isinstance(value, dict):
        raise ConfigError(f"配置文件根节点必须是对象: {path}")
    return value


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, str):
        match = ENV_PATTERN.match(value)
        if match:
            return os.getenv(match.group(1), "")
    return value


def _build_config(data: dict[str, Any]) -> AppConfig:
    repo_data = data.get("repo", {}) or {}
    knowledge_data = data.get("knowledge", {}) or {}
    neo4j_data = data.get("neo4j", {}) or {}
    model_data = data.get("model", {}) or {}
    verification_data = data.get("verification", {}) or {}
    workflow_data = data.get("workflow", {}) or {}

    commands = []
    for item in verification_data.get("commands", []) or []:
        if not isinstance(item, dict) or not item.get("name") or not item.get("command"):
            raise ConfigError("verification.commands 中每项都必须包含 name 和 command。")
        commands.append(VerificationCommand(name=str(item["name"]), command=str(item["command"])))

    return AppConfig(
        repo=RepoConfig(
            include=list(repo_data.get("include", RepoConfig().include)),
            exclude=list(repo_data.get("exclude", RepoConfig().exclude)),
        ),
        knowledge=KnowledgeConfig(docs_paths=list(knowledge_data.get("docs_paths", KnowledgeConfig().docs_paths))),
        neo4j=Neo4jConfig(
            uri=str(neo4j_data.get("uri") or os.getenv("NEO4J_URI") or Neo4jConfig().uri),
            user=str(neo4j_data.get("user") or os.getenv("NEO4J_USER") or Neo4jConfig().user),
            password=str(neo4j_data.get("password") or os.getenv("NEO4J_PASSWORD") or Neo4jConfig().password),
        ),
        model=ModelConfig(
            base_url=str(model_data.get("base_url") or os.getenv("MODEL_BASE_URL") or ""),
            api_key=str(model_data.get("api_key") or os.getenv("MODEL_API_KEY") or ""),
            model=str(model_data.get("model") or os.getenv("MODEL_NAME") or "mock"),
            timeout_seconds=int(model_data.get("timeout_seconds") or 90),
        ),
        verification=VerificationConfig(commands=commands),
        workflow=WorkflowConfig(
            max_retries=int(workflow_data.get("max_retries", 3)),
            output_dir=str(workflow_data.get("output_dir", "runs")),
        ),
    )
