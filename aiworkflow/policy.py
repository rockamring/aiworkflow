from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


DANGEROUS_COMMAND_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b",
    r"\bformat\b",
]


@dataclass(slots=True)
class CommandDecision:
    command: str
    cwd: str
    allowed: bool
    reason: str


class CommandPolicy:
    def __init__(self, denied_patterns: list[str] | None = None):
        self.denied_patterns = denied_patterns or DANGEROUS_COMMAND_PATTERNS

    def evaluate(self, command: str, cwd: Path) -> CommandDecision:
        lowered = command.lower()
        for pattern in self.denied_patterns:
            if re.search(pattern, lowered):
                return CommandDecision(
                    command=command,
                    cwd=str(cwd),
                    allowed=False,
                    reason=f"command matches denied pattern: {pattern}",
                )
        return CommandDecision(command=command, cwd=str(cwd), allowed=True, reason="allowed")
