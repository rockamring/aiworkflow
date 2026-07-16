from pathlib import Path

from aiworkflow.config import VerificationCommand, VerificationConfig
from aiworkflow.verify import is_safe_verification_command, run_verification, verification_summary


def test_rejects_dangerous_verification_commands():
    assert not is_safe_verification_command("git reset --hard")
    assert not is_safe_verification_command("rm -rf build")
    assert is_safe_verification_command("python -m pytest")


def test_verification_records_policy_decision(tmp_path: Path):
    results = run_verification(
        tmp_path,
        VerificationConfig(commands=[VerificationCommand(name="danger", command="git reset --hard")]),
    )
    summary = verification_summary(results)

    assert summary["passed"] is False
    assert summary["commands_rejected"] == 1
    assert results[0].policy_allowed is False
