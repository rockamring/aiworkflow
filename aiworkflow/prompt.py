from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PromptBundle:
    system: str
    task: str
    review: str


class PromptService:
    def __init__(self, prompts_dir: Path | None = None):
        self.prompts_dir = prompts_dir or Path(__file__).resolve().parent.parent / "prompts"

    def load_bundle(self, task_type: str) -> PromptBundle:
        return PromptBundle(
            system=self._read("system.md"),
            task=self._read(f"tasks/{task_type}.md", fallback=self._read("tasks/general.md")),
            review=self._read("review.md"),
        )

    def render(self, template: str, values: dict[str, object]) -> str:
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
