"""Project Registry 解析。

Project Registry 把项目别名、仓库路径、默认 Agent 和运行产物目录绑定起来。
这样 CLI 和后续 Agent Runtime 不必反复传裸 repo 路径，也为项目级权限、
Run Store 和团队策略预留稳定入口。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .config import AppConfig, ProjectConfig
from .errors import ConfigError


@dataclass(slots=True)
class ProjectSelection:
    """一次命令解析出的项目上下文。"""

    name: str
    repo: Path
    agent: str
    output_dir: str
    config: str = ""
    prompts: str = ""


def resolve_project(config: AppConfig, name: str) -> ProjectSelection:
    """按项目别名解析仓库、Agent 和输出目录。"""

    try:
        project = config.projects[name]
    except KeyError as exc:
        known = ", ".join(sorted(config.projects)) or "none"
        raise ConfigError(f"未知项目: {name}。已配置项目: {known}") from exc
    return selection_from_project_config(name, project, config)


def selection_from_project_config(name: str, project: ProjectConfig, config: AppConfig) -> ProjectSelection:
    output_dir = project.output_dir or str(Path(config.workflow.output_dir) / name)
    return ProjectSelection(
        name=name,
        repo=Path(project.repo),
        agent=project.agent or config.agent.default,
        output_dir=output_dir,
        config=project.config,
        prompts=project.prompts,
    )


def config_for_project(config: AppConfig, selection: ProjectSelection) -> AppConfig:
    """返回应用项目级 output_dir 后的配置快照。"""

    return replace(config, workflow=replace(config.workflow, output_dir=selection.output_dir))
