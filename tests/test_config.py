import sys
from types import SimpleNamespace

from src import config


def test_groq_model_factory_uses_configured_model_and_zero_temperature(monkeypatch):
    received = {}

    def fake_chat_groq(**kwargs):
        received.update(kwargs)
        return object()

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(config, "GROQ_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setitem(
        sys.modules, "langchain_groq", SimpleNamespace(ChatGroq=fake_chat_groq)
    )

    config.create_chat_model()

    assert received == {"model": "openai/gpt-oss-120b", "temperature": 0}
