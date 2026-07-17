from aiworkflow.contracts import (
    AgentEvent,
    AgentRunRequest,
    AgentRunResult,
    Artifact,
    Capability,
    PermissionDecision,
    ToolRequest,
    ToolResult,
)
from aiworkflow.state import ContextPack, KnowledgeChunk


def test_agent_run_contracts_are_serializable():
    pack = ContextPack(
        run_id="run-1",
        repo_id="repo-1",
        repo_path="G:/repo",
        query="修复 Renderer crash",
        task_type="crash_fix",
        agent="codex",
        prompt_text="Agent prompt",
    )
    artifact = Artifact(
        name="agent_prompt",
        kind="prompt",
        path="runs/run-1/agent_prompt.md",
        media_type="text/markdown",
        produced_by="prepare",
    )
    request = AgentRunRequest(
        run_id="run-1",
        agent="codex",
        adapter="codex_cli",
        repo_path="G:/repo",
        context_pack=pack,
        limits={"timeout_seconds": 600},
        artifacts=[artifact],
    )
    event = AgentEvent(run_id="run-1", sequence=1, kind="stdout", message="started")
    result = AgentRunResult(
        run_id="run-1",
        agent="codex",
        adapter="codex_cli",
        status="succeeded",
        started_at="2026-07-17T00:00:00+00:00",
        finished_at="2026-07-17T00:00:01+00:00",
        events=[event],
        artifacts=[artifact],
    )

    assert request.to_dict()["context_pack"]["query"] == "修复 Renderer crash"
    assert request.to_dict()["artifacts"][0]["kind"] == "prompt"
    assert result.to_dict()["events"][0]["kind"] == "stdout"
    assert result.to_dict()["status"] == "succeeded"


def test_tool_permission_contracts_are_serializable():
    capability = Capability(name="RunVerification", risk_level="medium", required_permission="verify")
    decision = PermissionDecision(
        subject="agent:codex",
        capability=capability.name,
        resource="repo:repo-1",
        allowed=True,
        reason="policy allowed",
    )
    request = ToolRequest(
        run_id="run-1",
        request_id="tool-1",
        requested_by="agent:codex",
        capability=capability.name,
        tool="verification",
        arguments={"command": "python -m pytest"},
        cwd="G:/repo",
    )
    result = ToolResult(
        run_id="run-1",
        request_id="tool-1",
        tool=request.tool,
        capability=request.capability,
        allowed=decision.allowed,
        success=True,
        output="passed",
        permission=decision,
    )

    assert capability.to_dict()["required_permission"] == "verify"
    assert request.to_dict()["arguments"]["command"] == "python -m pytest"
    assert result.to_dict()["permission"]["allowed"] is True
    assert result.to_dict()["success"] is True


def test_context_pack_round_trips_from_dict():
    pack = ContextPack(
        run_id="run-1",
        repo_id="repo-1",
        repo_path="G:/repo",
        query="修复 Renderer crash",
        task_type="crash_fix",
        agent="codex",
        knowledge_tags=["render"],
        context_chunks=[KnowledgeChunk(source="Renderer.cpp", kind="File", text="class Renderer {};", score=0.8, tags=["cpp"])],
        verification_commands=[{"name": "tests", "command": "python -m pytest"}],
        prompt_text="Agent prompt",
        search_stats={"total": 1},
        budget_summary={"used_chars": 12},
        generated_files={"manifest": "runs/run-1/manifest.json"},
    )

    restored = ContextPack.from_dict(pack.to_dict())

    assert restored.run_id == "run-1"
    assert restored.context_chunks[0].source == "Renderer.cpp"
    assert restored.context_chunks[0].score == 0.8
    assert restored.verification_commands == [{"name": "tests", "command": "python -m pytest"}]
    assert restored.generated_files["manifest"] == "runs/run-1/manifest.json"
