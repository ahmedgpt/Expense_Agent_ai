import src.rag as rag


def test_emergency_fund_retrieval_cites_expected_source(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "CHROMA_PATH", tmp_path / "missing_chroma")
    result = rag.search_knowledge_base("emergency fund how many months", k=3)
    assert result["results"]
    assert "03_emergency_fund_and_savings.md" in result["sources"]


def test_empty_retrieval_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "CHROMA_PATH", tmp_path / "missing_chroma")
    result = rag.search_knowledge_base("quasars and black holes")
    assert result["results"] == []
    assert result["sources"] == []


def test_invalid_query_is_reported():
    assert "error" in rag.search_knowledge_base("")


def test_persistent_chroma_ingestion_and_retrieval(tmp_path, monkeypatch):
    import pytest

    pytest.importorskip("langchain_chroma")
    terms = ("emergency", "fund", "savings", "budget", "debt", "avalanche", "snowball", "rule")

    class TinyEmbeddings:
        def embed_query(self, text):
            lowered = text.casefold()
            return [float(term in lowered) for term in terms]

        def embed_documents(self, texts):
            return [self.embed_query(text) for text in texts]

    destination = tmp_path / "chroma"
    monkeypatch.setattr(rag, "CHROMA_PATH", destination)
    monkeypatch.setattr(rag, "_embeddings", TinyEmbeddings)
    indexed = rag.ingest_knowledge_base(persist_path=destination)
    result = rag.search_knowledge_base("emergency fund", k=2)

    assert indexed["indexed_chunks"] > 8
    assert "03_emergency_fund_and_savings.md" in result["sources"]
    assert result["backend"] == "chroma"
