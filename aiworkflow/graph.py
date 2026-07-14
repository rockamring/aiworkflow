from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Neo4jConfig
from .errors import DependencyError, GraphConnectionError
from .state import KnowledgeChunk


@dataclass(slots=True)
class FileRecord:
    repo_id: str
    path: str
    language: str
    content: str


@dataclass(slots=True)
class SymbolRecord:
    repo_id: str
    file_path: str
    name: str
    kind: str
    line: int


@dataclass(slots=True)
class DocumentRecord:
    repo_id: str
    path: str
    kind: str
    content: str
    tags: list[str]


class GraphStore(Protocol):
    def ping(self) -> None:
        ...

    def initialize(self) -> None:
        ...

    def clear_repo(self, repo_id: str) -> None:
        ...

    def upsert_file(self, record: FileRecord) -> None:
        ...

    def upsert_symbol(self, record: SymbolRecord) -> None:
        ...

    def upsert_document(self, record: DocumentRecord) -> None:
        ...

    def search(self, repo_id: str, query: str, tags: list[str], limit: int = 8) -> list[KnowledgeChunk]:
        ...

    def close(self) -> None:
        ...


class Neo4jGraphStore:
    def __init__(self, config: Neo4jConfig):
        try:
            from neo4j import GraphDatabase  # type: ignore
        except ImportError as exc:
            raise DependencyError("缺少 neo4j Python 驱动，请先安装项目依赖。") from exc
        self._driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password))

    def ping(self) -> None:
        try:
            self._driver.verify_connectivity()
        except Exception as exc:  # noqa: BLE001 - convert vendor errors to user-facing error
            raise GraphConnectionError(f"无法连接 Neo4j: {exc}") from exc

    def initialize(self) -> None:
        statements = [
            "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE (f.repo_id, f.path) IS UNIQUE",
            "CREATE CONSTRAINT symbol_id IF NOT EXISTS FOR (s:Symbol) REQUIRE (s.repo_id, s.file_path, s.name, s.line) IS UNIQUE",
            "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE (d.repo_id, d.path) IS UNIQUE",
            "CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:Rule) REQUIRE (r.repo_id, r.path) IS UNIQUE",
        ]
        with self._driver.session() as session:
            for statement in statements:
                session.run(statement)

    def clear_repo(self, repo_id: str) -> None:
        with self._driver.session() as session:
            session.run("MATCH (n {repo_id: $repo_id}) DETACH DELETE n", repo_id=repo_id)

    def upsert_file(self, record: FileRecord) -> None:
        with self._driver.session() as session:
            session.run(
                """
                MERGE (f:File {repo_id: $repo_id, path: $path})
                SET f.language = $language, f.content = $content, f.updated_at = datetime()
                """,
                repo_id=record.repo_id,
                path=record.path,
                language=record.language,
                content=_truncate(record.content),
            )

    def upsert_symbol(self, record: SymbolRecord) -> None:
        with self._driver.session() as session:
            session.run(
                """
                MATCH (f:File {repo_id: $repo_id, path: $file_path})
                MERGE (s:Symbol {repo_id: $repo_id, file_path: $file_path, name: $name, line: $line})
                SET s.kind = $kind
                MERGE (f)-[:CONTAINS]->(s)
                """,
                repo_id=record.repo_id,
                file_path=record.file_path,
                name=record.name,
                kind=record.kind,
                line=record.line,
            )

    def upsert_document(self, record: DocumentRecord) -> None:
        label = "Rule" if record.kind == "rule" else "Document"
        with self._driver.session() as session:
            session.run(
                f"""
                MERGE (d:{label} {{repo_id: $repo_id, path: $path}})
                SET d.kind = $kind, d.content = $content, d.tags = $tags, d.updated_at = datetime()
                """,
                repo_id=record.repo_id,
                path=record.path,
                kind=record.kind,
                content=_truncate(record.content),
                tags=record.tags,
            )

    def search(self, repo_id: str, query: str, tags: list[str], limit: int = 8) -> list[KnowledgeChunk]:
        terms = _query_terms(query + " " + " ".join(tags))
        with self._driver.session() as session:
            rows = session.run(
                """
                MATCH (n)
                WHERE n.repo_id = $repo_id AND (n:Document OR n:Rule OR n:File OR n:Symbol)
                RETURN labels(n) AS labels, n.path AS path, n.file_path AS file_path,
                       n.name AS name, n.kind AS kind, n.content AS content, n.tags AS tags, n.line AS line
                LIMIT 250
                """,
                repo_id=repo_id,
            )
            chunks: list[KnowledgeChunk] = []
            for row in rows:
                text = _row_text(row)
                score = _score_text(text, terms, set(tags))
                if score <= 0:
                    continue
                chunks.append(
                    KnowledgeChunk(
                        source=str(row.get("path") or row.get("file_path") or row.get("name") or "neo4j"),
                        kind=str(row.get("kind") or ",".join(row.get("labels") or [])),
                        text=text,
                        score=score,
                        tags=list(row.get("tags") or []),
                    )
                )
            return sorted(chunks, key=lambda item: item.score, reverse=True)[:limit]

    def close(self) -> None:
        self._driver.close()


class InMemoryGraphStore:
    def __init__(self):
        self.files: list[FileRecord] = []
        self.symbols: list[SymbolRecord] = []
        self.documents: list[DocumentRecord] = []

    def ping(self) -> None:
        return None

    def initialize(self) -> None:
        return None

    def clear_repo(self, repo_id: str) -> None:
        self.files = [item for item in self.files if item.repo_id != repo_id]
        self.symbols = [item for item in self.symbols if item.repo_id != repo_id]
        self.documents = [item for item in self.documents if item.repo_id != repo_id]

    def upsert_file(self, record: FileRecord) -> None:
        self.files.append(record)

    def upsert_symbol(self, record: SymbolRecord) -> None:
        self.symbols.append(record)

    def upsert_document(self, record: DocumentRecord) -> None:
        self.documents.append(record)

    def search(self, repo_id: str, query: str, tags: list[str], limit: int = 8) -> list[KnowledgeChunk]:
        terms = _query_terms(query + " " + " ".join(tags))
        chunks: list[KnowledgeChunk] = []
        for doc in self.documents:
            if doc.repo_id != repo_id:
                continue
            score = _score_text(doc.content + " " + " ".join(doc.tags), terms, set(tags))
            if score > 0:
                chunks.append(KnowledgeChunk(doc.path, doc.kind, _truncate(doc.content), score, doc.tags))
        for symbol in self.symbols:
            if symbol.repo_id != repo_id:
                continue
            text = f"{symbol.kind} {symbol.name} in {symbol.file_path}:{symbol.line}"
            score = _score_text(text, terms, set(tags))
            if score > 0:
                chunks.append(KnowledgeChunk(symbol.file_path, "symbol", text, score, []))
        return sorted(chunks, key=lambda item: item.score, reverse=True)[:limit]

    def close(self) -> None:
        return None


def language_for(path: Path) -> str:
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(path.suffix.lower(), path.suffix.lower().lstrip(".") or "text")


def _query_terms(text: str) -> list[str]:
    return [item.lower() for item in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text)]


def _score_text(text: str, terms: list[str], tags: set[str]) -> float:
    haystack = text.lower()
    score = sum(1 for term in terms if term in haystack)
    score += sum(2 for tag in tags if tag and tag.lower() in haystack)
    return float(score)


def _truncate(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _row_text(row: object) -> str:
    getter = row.get  # type: ignore[attr-defined]
    name = getter("name")
    line = getter("line")
    content = getter("content")
    if name:
        return f"{getter('kind') or 'symbol'} {name} at {getter('file_path')}:{line}"
    return str(content or getter("path") or "")
