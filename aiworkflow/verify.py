"""验证命令执行层。

Verification 是 Tool/Execution 能力的最小闭环：命令从配置读取，执行前
必须经过 CommandPolicy，结果会被写入 verify_report.json 和 state.json。
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from .config import VerificationConfig
from .policy import CommandPolicy
from .state import VerificationResult


def run_verification(repo: Path, config: VerificationConfig, policy: CommandPolicy | None = None) -> list[VerificationResult]:
    """在目标仓库目录执行配置中的验证命令。

    每条命令都会先经过 CommandPolicy；被拒绝的命令不会执行，但会以
    VerificationResult 形式记录拒绝原因，保证审计链路完整。
    """

    repo = repo.resolve()
    policy = policy or CommandPolicy()
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
                policy_allowed=True,
                policy_reason="未配置校验命令",
            )
        ]

    results = []
    for command in config.commands:
        decision = policy.evaluate(command.command, repo)
        if not decision.allowed:
            results.append(
                VerificationResult(
                    name=command.name,
                    command=command.command,
                    passed=False,
                    exit_code=126,
                    stdout="",
                    stderr="命令被安全策略拒绝。",
                    duration_seconds=0.0,
                    policy_allowed=False,
                    policy_reason=decision.reason,
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
                policy_allowed=True,
                policy_reason=decision.reason,
            )
        )
    return results


def is_safe_verification_command(command: str) -> bool:
    return CommandPolicy().evaluate(command, Path.cwd()).allowed


def verification_summary(results: list[VerificationResult]) -> dict[str, object]:
    """把多条验证结果聚合成报告摘要。"""

    return {
        "passed": all(item.passed for item in results),
        "results": [asdict(item) for item in results],
        "duration_seconds": round(sum(item.duration_seconds for item in results), 3),
        "commands_total": len(results),
        "commands_rejected": sum(1 for item in results if not item.policy_allowed),
    }


def format_verify_log(results: list[VerificationResult]) -> str:
    parts = []
    for item in results:
        status = "PASS" if item.passed else "FAIL"
        parts.append(
            f"[{status}] {item.name}\n"
            f"command: {item.command}\n"
            f"exit_code: {item.exit_code}\n"
            f"policy_allowed: {item.policy_allowed}\n"
            f"policy_reason: {item.policy_reason}\n"
            f"stdout:\n{item.stdout}\n"
            f"stderr:\n{item.stderr}\n"
        )
    return "\n".join(parts)


def _tail(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]
