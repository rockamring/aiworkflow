"""Prompt 模板服务。

任务指导不写死在 prepare 流程里，而是通过 prompts/ 目录管理，便于
版本化、Code Review 和项目级扩展。当前模板渲染只做最小变量替换，
后续可以替换为 Jinja2 等更完整的模板引擎。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PromptBundle:
    """一次任务需要的 Prompt 模板集合。"""

    task: str


class PromptService:
    """从 prompts/ 加载并渲染任务指导模板。"""

    def __init__(self, prompts_dir: Path | None = None):
        self.prompts_dir = prompts_dir or Path(__file__).resolve().parent.parent / "prompts"

    def load_bundle(self, task_type: str) -> PromptBundle:
        """按任务类型加载任务指导模板。"""

        return PromptBundle(
            task=self._read(f"tasks/{task_type}.md", fallback=self._read("tasks/general.md")),
        )

    def render(self, template: str, values: dict[str, object]) -> str:
        """执行最小模板渲染，支持 {{ key }} 与 {{key}} 两种占位格式。"""

        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{{ " + key + " }}", str(value))
            rendered = rendered.replace("{{" + key + "}}", str(value))
        return rendered

    def _read(self, relative_path: str, fallback: str = "") -> str:
        path = self.prompts_dir / relative_path
        if not path.exists():
            return fallback
        return path.read_text(encoding="utf-8")
