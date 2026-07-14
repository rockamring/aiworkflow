from __future__ import annotations

import re
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from .config import VerificationConfig
from .state import VerificationResult


DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b",
    r"\bformat\b",
]


def run_verification(repo: Path, config: VerificationConfig) -> list[VerificationResult]:
    repo = repo.resolve()
    if not config.commands:
        return [
            VerificationResult(
                name="no-op",
                command="",
                passed=True,
                exit_code=0,
                stdout="未配置 verification.commands，跳过校验。",
                stderr="",
                duration_seconds=0.0,
            )
        ]
    results = []
    for command in config.commands:
        if not is_safe_verification_command(command.command):
            results.append(
                VerificationResult(
                    name=command.name,
                    command=command.command,
                    passed=False,
                    exit_code=126,
                    stdout="",
                    stderr="命令被安全策略拒绝：校验流水线不执行明显破坏性命令。",
                    duration_seconds=0.0,
                )
            )
            continue
        started = time.perf_counter()
        completed = subprocess.run(
            command.command,
            cwd=repo,
            shell=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        results.append(
            VerificationResult(
                name=command.name,
                command=command.command,
                passed=completed.returncode == 0,
                exit_code=completed.returncode,
                stdout=_tail(completed.stdout),
                stderr=_tail(completed.stderr),
                duration_seconds=round(time.perf_counter() - started, 3),
            )
        )
    return results


def is_safe_verification_command(command: str) -> bool:
    lowered = command.lower()
    return not any(re.search(pattern, lowered) for pattern in DANGEROUS_PATTERNS)


def verification_summary(results: list[VerificationResult]) -> dict[str, object]:
    return {
        "passed": all(item.passed for item in results),
        "results": [asdict(item) for item in results],
    }


def format_verify_log(results: list[VerificationResult]) -> str:
    parts = []
    for item in results:
        status = "PASS" if item.passed else "FAIL"
        parts.append(
            f"[{status}] {item.name}\n"
            f"command: {item.command}\n"
            f"exit_code: {item.exit_code}\n"
            f"stdout:\n{item.stdout}\n"
            f"stderr:\n{item.stderr}\n"
        )
    return "\n".join(parts)


def _tail(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]
