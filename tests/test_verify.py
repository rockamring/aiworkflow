from aiworkflow.verify import is_safe_verification_command


def test_rejects_dangerous_verification_commands():
    assert not is_safe_verification_command("git reset --hard")
    assert not is_safe_verification_command("rm -rf build")
    assert is_safe_verification_command("python -m pytest")
