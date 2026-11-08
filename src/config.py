"""Application configuration and paths."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")

DATA_PATH = Path(os.getenv("TRANSACTIONS_CSV", PROJECT_ROOT / "data" / "transactions.csv"))
RAG_DOCS_PATH = Path(os.getenv("RAG_DOCS_DIR", PROJECT_ROOT / "rag_docs"))
CHROMA_PATH = Path(os.getenv("CHROMA_PATH", PROJECT_ROOT / "chroma_db"))
MEMORY_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", PROJECT_ROOT / "memory.db"))
LOG_PATH = Path(os.getenv("AGENT_LOG_PATH", PROJECT_ROOT / "logs" / "agent.log"))
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def create_chat_model():
    """Create the configured LLM; fail clearly when credentials are absent."""
    provider = LLM_PROVIDER or ("groq" if os.getenv("GROQ_API_KEY") else "")
    if provider != "groq":
        raise RuntimeError(
            "Set LLM_PROVIDER=groq and GROQ_API_KEY in .env to use the live agent."
        )
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is required when LLM_PROVIDER=groq.")
    try:
        from langchain_groq import ChatGroq
    except ImportError as exc:
        raise RuntimeError(
            "Live chat dependencies are missing; install requirements.txt."
        ) from exc
    return ChatGroq(model=GROQ_MODEL, temperature=0)
