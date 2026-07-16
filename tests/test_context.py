from aiworkflow.context import ContextService, build_context_block, classify_task
from aiworkflow.graph import InMemoryGraphStore
from aiworkflow.search import SearchService
from aiworkflow.state import KnowledgeChunk


def test_classify_task_selects_game_relevant_tags():
    crash = classify_task("修复 Renderer crash")
    perf = classify_task("优化 Lua UI performance")

    assert crash.task_type == "crash_fix"
    assert crash.tags == ["crash", "debugging"]
    assert perf.task_type == "performance"
    assert perf.tags == ["performance"]


def test_context_block_records_budget_and_sources():
    block, summary = build_context_block(
        [
            KnowledgeChunk(source="Renderer.cpp", kind="file", text="Renderer crash path", score=3.0, tags=["crash"]),
            KnowledgeChunk(source="AGENTS.md", kind="rule", text="Run tests", score=2.0, tags=["test"]),
        ],
        char_budget=500,
    )

    assert "Renderer.cpp" in block
    assert "score: 3.0" in block
    assert summary["chunks_included"] == 2
    assert summary["used_chars"] > 0


def test_context_service_builds_prompt_from_search_results():
    store = InMemoryGraphStore()
    service = ContextService(SearchService(store))

    assert service.char_budget > 0
