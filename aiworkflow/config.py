"""配置加载与合并。

配置来源优先级是显式路径、AIWORKFLOW_CONFIG、config/workflow.yaml、
config/workflow.example.yaml。这里把 YAML/JSON/环境变量统一转换成 AppConfig，
让 CLI 和 workflow 不直接处理原始配置字典。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .errors import ConfigError


ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


@dataclass(slots=True)
class RepoConfig:
    include: list[str] = field(default_factory=lambda: [
        "**/*.py",
        "**/*.ts",
        "**/*.tsx",
        "**/*.js",
        "**/*.jsx",
        "**/*.md",
        "**/*.json",
        "**/*.yaml",
        "**/*.yml",
        "**/*.cpp",
        "**/*.cc",
        "**/*.cxx",
        "**/*.h",
        "**/*.hpp",
        "**/*.cs",
        "**/*.lua",
        "**/*.uasset",
    ])
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
class ContextConfig:
    budget_chars: int = 18000
    search_limit: int = 8


@dataclass(slots=True)
class VerificationCommand:
    name: str
    command: str


@dataclass(slots=True)
class VerificationConfig:
    commands: list[VerificationCommand] = field(default_factory=list)


@dataclass(slots=True)
class WorkflowConfig:
    output_dir: str = "runs"


@dataclass(slots=True)
class ProjectConfig:
    repo: str
    agent: str = ""
    output_dir: str = ""
    config: str = ""
    prompts: str = ""


@dataclass(slots=True)
class AgentProfileConfig:
    prompt_style: str = "generic"
    extra_instructions: list[str] = field(default_factory=list)
    adapter: str = "dry_run"
    command: str = ""
    args: list[str] = field(default_factory=list)
    input_mode: str = "stdin"
    output_mode: str = "text"
    default_permissions: list[str] = field(default_factory=list)
    timeout_seconds: int = 600
    env: dict[str, str] = field(default_factory=dict)


def _default_agent_profiles() -> dict[str, AgentProfileConfig]:
    return {
        "generic": AgentProfileConfig(
            prompt_style="generic",
            adapter="dry_run",
            input_mode="none",
            output_mode="events",
            timeout_seconds=60,
        ),
        "codex": AgentProfileConfig(
            prompt_style="codex",
            adapter="codex_cli",
            command="codex",
            input_mode="stdin",
            output_mode="stream",
            default_permissions=["read_repo"],
            timeout_seconds=900,
        ),
        "claude-code": AgentProfileConfig(
            prompt_style="claude-code",
            adapter="claude_code_cli",
            command="claude",
            input_mode="stdin",
            output_mode="stream",
            default_permissions=["read_repo"],
            timeout_seconds=900,
        ),
    }


@dataclass(slots=True)
class AgentConfig:
    default: str = "codex"
    profiles: dict[str, AgentProfileConfig] = field(default_factory=_default_agent_profiles)


@dataclass(slots=True)
class AppConfig:
    """应用运行所需的完整配置快照。"""

    repo: RepoConfig = field(default_factory=RepoConfig)
    knowledge: KnowledgeConfig = field(default_factory=KnowledgeConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    projects: dict[str, ProjectConfig] = field(default_factory=dict)


def resolve_agent_profile(config: AppConfig, agent_name: str) -> AgentProfileConfig:
    """返回目标 Agent 的结构化 Profile，未知 Agent 回退到 generic。"""

    return (
        config.agent.profiles.get(agent_name)
        or config.agent.profiles.get("generic")
        or AgentProfileConfig(prompt_style=agent_name)
    )


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
    """加载配置文件并展开 ${ENV_NAME} 占位符。"""

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
    """按约定解析最终使用的配置文件路径。"""

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
    """把原始 mapping 转换为强类型 AppConfig。"""

    repo_data = data.get("repo", {}) or {}
    knowledge_data = data.get("knowledge", {}) or {}
    neo4j_data = data.get("neo4j", {}) or {}
    context_data = data.get("context", {}) or {}
    agent_data = data.get("agent", {}) or {}
    verification_data = data.get("verification", {}) or {}
    workflow_data = data.get("workflow", {}) or {}
    projects_data = data.get("projects", {}) or {}

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
        context=ContextConfig(
            budget_chars=int(context_data.get("budget_chars", ContextConfig().budget_chars)),
            search_limit=int(context_data.get("search_limit", ContextConfig().search_limit)),
        ),
        agent=AgentConfig(
            default=str(agent_data.get("default") or AgentConfig().default),
            profiles=_build_agent_profiles(agent_data.get("profiles", {}) or {}),
        ),
        verification=VerificationConfig(commands=commands),
        workflow=WorkflowConfig(
            output_dir=str(workflow_data.get("output_dir", "runs")),
        ),
        projects=_build_projects(projects_data),
    )


def _build_agent_profiles(raw_profiles: object) -> dict[str, AgentProfileConfig]:
    profiles = _default_agent_profiles()
    if not isinstance(raw_profiles, dict):
        return profiles
    for name, raw_profile in raw_profiles.items():
        profile_name = str(name)
        base = profiles.get(profile_name, AgentProfileConfig(prompt_style=profile_name))
        if isinstance(raw_profile, str):
            profiles[profile_name] = replace(base, prompt_style=raw_profile)
            continue
        if not isinstance(raw_profile, dict):
            continue
        profiles[profile_name] = replace(
            base,
            prompt_style=str(raw_profile.get("prompt_style") or base.prompt_style or profile_name),
            extra_instructions=_as_string_list(raw_profile.get("extra_instructions"), base.extra_instructions),
            adapter=str(raw_profile.get("adapter") or base.adapter),
            command=str(raw_profile.get("command") or base.command),
            args=_as_string_list(raw_profile.get("args"), base.args),
            input_mode=str(raw_profile.get("input_mode") or base.input_mode),
            output_mode=str(raw_profile.get("output_mode") or base.output_mode),
            default_permissions=_as_string_list(raw_profile.get("default_permissions"), base.default_permissions),
            timeout_seconds=_as_int(raw_profile.get("timeout_seconds"), base.timeout_seconds),
            env=_as_string_dict(raw_profile.get("env"), base.env),
        )
    return profiles


def _as_string_list(value: object, default: list[str] | None = None) -> list[str]:
    if value is None:
        return list(default or [])
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return list(default or [])


def _as_string_dict(value: object, default: dict[str, str] | None = None) -> dict[str, str]:
    if value is None:
        return dict(default or {})
    if not isinstance(value, dict):
        return dict(default or {})
    return {str(key): str(item) for key, item in value.items()}


def _as_int(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_projects(raw_projects: object) -> dict[str, ProjectConfig]:
    if not isinstance(raw_projects, dict):
        return {}
    projects: dict[str, ProjectConfig] = {}
    for name, raw_project in raw_projects.items():
        project_name = str(name)
        if isinstance(raw_project, str):
            projects[project_name] = ProjectConfig(repo=raw_project)
            continue
        if not isinstance(raw_project, dict):
            raise ConfigError(f"projects.{project_name} 必须是 repo 路径字符串或对象。")
        repo = raw_project.get("repo")
        if not repo:
            raise ConfigError(f"projects.{project_name}.repo 不能为空。")
        projects[project_name] = ProjectConfig(
            repo=str(repo),
            agent=str(raw_project.get("agent") or ""),
            output_dir=str(raw_project.get("output_dir") or ""),
            config=str(raw_project.get("config") or ""),
            prompts=str(raw_project.get("prompts") or ""),
        )
    return projects
