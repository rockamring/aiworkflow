from aiworkflow.graph import DocumentRecord, FileRecord, InMemoryGraphStore, SymbolRecord
from aiworkflow.search import SearchRequest, SearchService


def test_search_returns_documents_symbols_and_files_by_score():
    store = InMemoryGraphStore()
    store.upsert_document(DocumentRecord("repo", "docs/render.md", "document", "Renderer architecture crash notes", ["crash"]))
    store.upsert_symbol(SymbolRecord("repo", "Renderer.cpp", "RenderFrame", "function", 12, "Renderer"))
    store.upsert_file(FileRecord("repo", "Renderer.cpp", "cpp", "void RenderFrame() { /* crash guard */ }"))

    response = SearchService(store).search(SearchRequest(repo_id="repo", query="Renderer crash RenderFrame", tags=["crash"], limit=10))

    assert response.stats["returned"] == 3
    assert response.stats["by_kind"]["document"] == 1
    assert {item.kind for item in response.chunks} >= {"document", "symbol", "file"}
