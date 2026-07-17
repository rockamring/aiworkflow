"""命令安全策略。

Permission Service 的 MVP 形态。当前只做危险命令模式拒绝，后续可以
扩展为项目级权限、用户角色、路径范围、审计记录和 Tool Service 策略。
"""

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
    """一次命令策略判断结果。"""

    command: str
    cwd: str
    allowed: bool
    reason: str


class CommandPolicy:
    """验证或工具命令执行前的安全策略。"""

    def __init__(self, denied_patterns: list[str] | None = None):
        self.denied_patterns = denied_patterns or DANGEROUS_COMMAND_PATTERNS

    def evaluate(self, command: str, cwd: Path) -> CommandDecision:
        """判断命令是否允许在指定目录执行。"""

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
