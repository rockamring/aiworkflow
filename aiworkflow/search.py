"""搜索服务抽象。

当前 SearchService 只是对 GraphStore.search() 的薄封装，负责统一请求、
响应和统计形状。这个边界为后续 Hybrid Search 预留位置：BM25、Symbol、
Graph、Recent、Embedding 都可以在这里组合排序。
"""

from __future__ import annotations

from dataclasses import dataclass

from .graph import GraphStore
from .state import KnowledgeChunk


@dataclass(slots=True)
class SearchRequest:
    """一次上下文检索请求。"""

    repo_id: str
    query: str
    tags: list[str]
    limit: int = 8


@dataclass(slots=True)
class SearchResponse:
    """检索结果和本次搜索的统计信息。"""

    chunks: list[KnowledgeChunk]
    stats: dict[str, object]


class SearchService:
    """统一上下文检索入口。

    调用方不需要知道底层是 Neo4j、InMemory，还是未来的 Hybrid Search。
    """

    def __init__(self, store: GraphStore):
        self.store = store

    def search(self, request: SearchRequest) -> SearchResponse:
        """执行检索并按 chunk 类型汇总统计。"""

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
