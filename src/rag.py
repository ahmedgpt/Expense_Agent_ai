"""Persistent Chroma ingestion and source-attributed knowledge retrieval."""

from __future__ import annotations

import re
import time
import math
from pathlib import Path
from typing import Any

from src.config import CHROMA_PATH, RAG_DOCS_PATH
from src.logging_utils import log_tool_call

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "expense_knowledge"


def _chunks_from_docs(docs_path: Path | None = None) -> list[dict[str, Any]]:
    root = docs_path or RAG_DOCS_PATH
    files = sorted(root.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No Markdown knowledge documents found in {root}")
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        splitter = None
    else:
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=80)

    chunks: list[dict[str, Any]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        pieces = splitter.split_text(text) if splitter else _simple_chunks(text, 500, 80)
        for index, content in enumerate(pieces):
            chunks.append(
                {
                    "page_content": content,
                    "metadata": {"source": path.name, "chunk_id": index},
                }
            )
    return chunks


def _simple_chunks(text: str, size: int, overlap: int) -> list[str]:
    result = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        result.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in result if chunk]


def _embeddings():
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError as exc:
        raise RuntimeError(
            "RAG ingestion requires langchain-huggingface and sentence-transformers; "
            "install requirements.txt."
        ) from exc
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )


def ingest_knowledge_base(
    docs_path: str | Path | None = None, persist_path: str | Path | None = None
) -> dict[str, Any]:
    """Split Markdown sources and persist locally embedded chunks in Chroma."""
    try:
        from langchain_chroma import Chroma
        from langchain_core.documents import Document
    except ImportError as exc:
        raise RuntimeError(
            "Chroma ingestion dependencies are missing; install requirements.txt."
        ) from exc
    docs = _chunks_from_docs(Path(docs_path) if docs_path else None)
    destination = Path(persist_path) if persist_path else CHROMA_PATH
    destination.mkdir(parents=True, exist_ok=True)
    documents = [
        Document(page_content=chunk["page_content"], metadata=chunk["metadata"])
        for chunk in docs
    ]
    Chroma.from_documents(
        documents=documents,
        embedding=_embeddings(),
        collection_name=COLLECTION_NAME,
        persist_directory=str(destination),
        ids=[f"{item['metadata']['source']}::{item['metadata']['chunk_id']}" for item in docs],
    )
    return {"indexed_chunks": len(documents), "sources": len({d["metadata"]["source"] for d in docs}), "path": str(destination)}


def _lexical_search(query: str, k: int) -> list[dict[str, Any]]:
    stop_words = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "how", "i", "in", "is", "it", "my", "of", "on", "or", "should",
        "the", "to", "was", "what",
    }
    query_tokens = set(re.findall(r"[a-z0-9]+", query.casefold())) - stop_words
    scored: list[tuple[int, dict[str, Any]]] = []
    for chunk in _chunks_from_docs():
        content_tokens = set(re.findall(r"[a-z0-9]+", chunk["page_content"].casefold()))
        score = len(query_tokens & content_tokens)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["metadata"]["source"], pair[1]["metadata"]["chunk_id"]))
    return [
        {
            "content": chunk["page_content"],
            "source": chunk["metadata"]["source"],
            "chunk_id": chunk["metadata"]["chunk_id"],
            "score": score,
        }
        for score, chunk in scored[:k]
    ]


def search_knowledge_base(query: str, k: int = 3) -> dict[str, Any]:
    """Retrieve relevant document chunks with source filenames for citations."""
    started = time.perf_counter()
    if not isinstance(query, str) or not query.strip():
        result = {"error": "query must be a non-empty string.", "results": []}
        log_tool_call(
            "search_knowledge_base",
            {"query": query, "k": k},
            result,
            (time.perf_counter() - started) * 1000,
        )
        return result
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 10:
        result = {"error": "k must be an integer from 1 to 10.", "results": []}
        log_tool_call(
            "search_knowledge_base",
            {"query": query, "k": k},
            result,
            (time.perf_counter() - started) * 1000,
        )
        return result
    if CHROMA_PATH.exists() and any(CHROMA_PATH.iterdir()):
        try:
            from langchain_chroma import Chroma
        except ImportError as exc:
            raise RuntimeError("The Chroma index exists but its query dependency is missing.") from exc
        store = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=str(CHROMA_PATH),
            embedding_function=_embeddings(),
        )
        matches = store.similarity_search_with_score(query, k=k)
        results = [
            {
                "content": document.page_content,
                "source": document.metadata.get("source", "unknown"),
                "chunk_id": document.metadata.get("chunk_id"),
                "score": round(max(0.0, 1.0 - float(distance) / math.sqrt(2)), 4),
            }
            for document, distance in matches
            if 1.0 - float(distance) / math.sqrt(2) > 0
        ]
        backend = "chroma"
    else:
        results = _lexical_search(query, k)
        backend = "keyword fallback (Chroma index not built)"
    result = {
        "query": query,
        "results": results,
        "sources": list(dict.fromkeys(item["source"] for item in results)),
        "backend": backend,
    }
    log_tool_call(
        "search_knowledge_base",
        {"query": query, "k": k},
        {"backend": backend, "sources": result["sources"], "result_count": len(results)},
        (time.perf_counter() - started) * 1000,
    )
    return result
