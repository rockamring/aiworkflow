from __future__ import annotations

import ast
import fnmatch
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .graph import DocumentRecord, FileRecord, GraphStore, SymbolRecord, language_for


@dataclass(slots=True)
class IngestReport:
    repo_id: str
    files_indexed: int
    symbols_indexed: int
    documents_indexed: int


def repo_id_for(repo: Path) -> str:
    resolved = repo.resolve()
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:12]
    return f"{resolved.name}-{digest}"


def ingest_repo(repo: Path, config: AppConfig, store: GraphStore, clear: bool = True) -> IngestReport:
    repo = repo.resolve()
    if not repo.exists() or not repo.is_dir():
        raise ValueError(f"目标仓库不存在或不是目录: {repo}")
    repo_id = repo_id_for(repo)
    store.initialize()
    if clear:
        store.clear_repo(repo_id)

    files_count = 0
    symbols_count = 0
    docs_count = 0
    for path in iter_repo_files(repo, config.repo.include, config.repo.exclude):
        rel = _rel(path, repo)
        if _is_binary_asset(path):
            content = f"Binary asset placeholder: {rel}"
            store.upsert_file(FileRecord(repo_id=repo_id, path=rel, language=language_for(path), content=content))
            files_count += 1
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        store.upsert_file(FileRecord(repo_id=repo_id, path=rel, language=language_for(path), content=content))
        files_count += 1
        for symbol in extract_symbols(path, rel, content, repo_id):
            store.upsert_symbol(symbol)
            symbols_count += 1

    for doc_path, kind in iter_knowledge_docs(repo, config.knowledge.docs_paths):
        try:
            content = doc_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        tags = infer_tags(doc_path.name + " " + content[:2000])
        store.upsert_document(DocumentRecord(repo_id=repo_id, path=_rel(doc_path, repo), kind=kind, content=content, tags=tags))
        docs_count += 1

    return IngestReport(repo_id=repo_id, files_indexed=files_count, symbols_indexed=symbols_count, documents_indexed=docs_count)


def iter_repo_files(repo: Path, include: list[str], exclude: list[str]):
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        rel = _rel(path, repo)
        if _matches_any(rel, exclude):
            continue
        if include and not _matches_any(rel, include):
            continue
        yield path


def iter_knowledge_docs(repo: Path, docs_paths: list[str]):
    seen: set[Path] = set()
    for raw in docs_paths:
        path = (repo / raw).resolve()
        if not path.exists():
            continue
        candidates = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            kind = "rule" if candidate.name.upper() == "AGENTS.MD" else "document"
            yield candidate, kind


def extract_symbols(path: Path, rel_path: str, content: str, repo_id: str) -> list[SymbolRecord]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _extract_python_symbols(rel_path, content, repo_id)
    if suffix in {".cpp", ".cc", ".cxx", ".h", ".hpp"}:
        return _extract_cpp_symbols(rel_path, content, repo_id)
    if suffix == ".cs":
        return _extract_csharp_symbols(rel_path, content, repo_id)
    if suffix == ".lua":
        return _extract_lua_symbols(rel_path, content, repo_id)
    return _extract_text_symbols(rel_path, content, repo_id)


def infer_tags(text: str) -> list[str]:
    mapping = {
        "crash": ["crash", "崩溃"],
        "performance": ["performance", "性能", "优化"],
        "test": ["test", "pytest", "测试"],
        "security": ["security", "安全", "权限"],
        "architecture": ["architecture", "架构", "设计"],
        "style": ["style", "lint", "规范"],
    }
    lowered = text.lower()
    tags = []
    for tag, needles in mapping.items():
        if any(needle.lower() in lowered for needle in needles):
            tags.append(tag)
    return tags


def _extract_python_symbols(rel_path: str, content: str, repo_id: str) -> list[SymbolRecord]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    records = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            records.append(SymbolRecord(repo_id, rel_path, node.name, "class", node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            records.append(SymbolRecord(repo_id, rel_path, node.name, "function", node.lineno))
    return records


def _extract_cpp_symbols(rel_path: str, content: str, repo_id: str) -> list[SymbolRecord]:
    records: list[SymbolRecord] = []
    class_pattern = re.compile(r"\b(class|struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)")
    function_pattern = re.compile(
        r"^\s*(?:template\s*<[^>]+>\s*)?"
        r"(?:(?:static|virtual|inline|constexpr|FORCEINLINE|UFUNCTION\([^)]*\)|UFUNCTION)\s+)*"
        r"(?:[A-Za-z_][A-Za-z0-9_:<>\*&,\s]+\s+)+"
        r"([A-Za-z_][A-Za-z0-9_:]*)\s*\([^;{}]*\)\s*(?:const)?\s*(?:override|final)?\s*(?:\{|;)?"
    )
    for line_no, line in enumerate(content.splitlines(), start=1):
        class_match = class_pattern.search(line)
        if class_match:
            records.append(SymbolRecord(repo_id, rel_path, class_match.group(2), class_match.group(1), line_no))
            continue
        func_match = function_pattern.search(line)
        if func_match:
            name = func_match.group(1).split("::")[-1]
            if name not in {"if", "for", "while", "switch", "return"}:
                container = "::".join(func_match.group(1).split("::")[:-1])
                records.append(SymbolRecord(repo_id, rel_path, name, "function", line_no, container))
    return records


def _extract_csharp_symbols(rel_path: str, content: str, repo_id: str) -> list[SymbolRecord]:
    records: list[SymbolRecord] = []
    type_pattern = re.compile(r"\b(class|struct|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)")
    method_pattern = re.compile(
        r"^\s*(?:\[[^\]]+\]\s*)*"
        r"(?:(?:public|private|protected|internal|static|virtual|override|async|sealed|partial)\s+)*"
        r"(?:[A-Za-z_][A-Za-z0-9_<>,\[\]\?]*\s+)+"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)"
    )
    current_type = ""
    for line_no, line in enumerate(content.splitlines(), start=1):
        type_match = type_pattern.search(line)
        if type_match:
            current_type = type_match.group(2)
            records.append(SymbolRecord(repo_id, rel_path, current_type, type_match.group(1), line_no))
            continue
        method_match = method_pattern.search(line)
        if method_match:
            name = method_match.group(1)
            if name not in {"if", "for", "foreach", "while", "switch", "catch"}:
                records.append(SymbolRecord(repo_id, rel_path, name, "method", line_no, current_type))
    return records


def _extract_lua_symbols(rel_path: str, content: str, repo_id: str) -> list[SymbolRecord]:
    records: list[SymbolRecord] = []
    function_pattern = re.compile(r"^\s*(?:local\s+)?function\s+([A-Za-z_][A-Za-z0-9_:\.]*)")
    assignment_pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_:\.]*)\s*=\s*function\s*\(")
    table_pattern = re.compile(r"^\s*(?:local\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{")
    for line_no, line in enumerate(content.splitlines(), start=1):
        match = function_pattern.search(line) or assignment_pattern.search(line)
        if match:
            full_name = match.group(1)
            parts = re.split(r"[:.]", full_name)
            container = ".".join(parts[:-1])
            records.append(SymbolRecord(repo_id, rel_path, parts[-1], "function", line_no, container))
            continue
        table_match = table_pattern.search(line)
        if table_match:
            records.append(SymbolRecord(repo_id, rel_path, table_match.group(1), "table", line_no))
    return records


def _extract_text_symbols(rel_path: str, content: str, repo_id: str) -> list[SymbolRecord]:
    records = []
    pattern = re.compile(r"\b(?:function|class|interface|const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)")
    for line_no, line in enumerate(content.splitlines(), start=1):
        match = pattern.search(line)
        if match:
            records.append(SymbolRecord(repo_id, rel_path, match.group(1), "symbol", line_no))
    return records


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatch(normalized, pattern[3:]):
            return True
    return False


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _is_binary_asset(path: Path) -> bool:
    return path.suffix.lower() in {".uasset", ".umap"}
