from __future__ import annotations

from dataclasses import dataclass

from .graph import GraphStore
from .state import KnowledgeChunk


@dataclass(slots=True)
class SearchRequest:
    repo_id: str
    query: str
    tags: list[str]
    limit: int = 8


@dataclass(slots=True)
class SearchResponse:
    chunks: list[KnowledgeChunk]
    stats: dict[str, object]


class SearchService:
    def __init__(self, store: GraphStore):
        self.store = store

    def search(self, request: SearchRequest) -> SearchResponse:
        chunks = self.store.search(
            repo_id=request.repo_id,
            query=request.query,
            tags=request.tags,
            limit=request.limit,
        )
        by_kind: dict[str, int] = {}
        for chunk in chunks:
            by_kind[chunk.kind] = by_kind.get(chunk.kind, 0) + 1
        return SearchResponse(
            chunks=chunks,
            stats={
                "query": request.query,
                "tags": request.tags,
                "limit": request.limit,
                "returned": len(chunks),
                "by_kind": by_kind,
            },
        )
