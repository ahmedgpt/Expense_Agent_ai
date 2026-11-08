"""Command-line entry point for building the local Chroma knowledge index."""

from __future__ import annotations

from src.rag import ingest_knowledge_base


def main() -> None:
    result = ingest_knowledge_base()
    print(
        f"Indexed {result['indexed_chunks']} chunks from {result['sources']} sources "
        f"in {result['path']}."
    )


if __name__ == "__main__":
    main()
