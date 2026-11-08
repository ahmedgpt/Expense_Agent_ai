import asyncio
from types import SimpleNamespace

import pytest

from src.agent import AgentInvocationError, ExpenseAgent, _extract_evidence, create_expense_agent
from src.memory_store import MemoryStore
from src.prompts import SYSTEM_PROMPT


class FakeGraph:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, input_value, config):
        self.calls.append((input_value, config))
        final_message = SimpleNamespace(type="ai", content="Dining Out was PKR 20,000.")
        return {"messages": [*input_value["messages"], final_message]}


def test_agent_keeps_thread_id_and_only_recalls_at_thread_start(tmp_path):
    graph = FakeGraph()
    runtime = ExpenseAgent(graph, "alice", MemoryStore(tmp_path / "memory.db"), object())

    async def run_turns():
        first = await runtime.ainvoke("October dining total?", "alice:s1")
        await runtime.ainvoke("And September?", "alice:s1")
        third = await runtime.ainvoke("New session", "alice:s2")
        return first, third

    first, third = asyncio.run(run_turns())

    assert [call[1]["configurable"]["thread_id"] for call in graph.calls] == [
        "alice:s1",
        "alice:s1",
        "alice:s2",
    ]
    assert sum(
        message.get("role") == "system"
        for call, _ in graph.calls
        for message in call["messages"]
    ) == 2
    assert first["memory_entries"]["user_id"] == "alice"
    assert third["memory_entries"]["user_id"] == "alice"


def test_agent_retries_once_and_surfaces_persistent_errors(tmp_path):
    class RetryOnceGraph(FakeGraph):
        async def ainvoke(self, input_value, config):
            self.calls.append((input_value, config))
            if len(self.calls) == 1:
                raise RuntimeError("temporary API error")
            return {"messages": [SimpleNamespace(type="ai", content="Recovered.")]}

    graph = RetryOnceGraph()
    runtime = ExpenseAgent(graph, "alice", MemoryStore(tmp_path / "memory.db"), object())
    result = asyncio.run(runtime.ainvoke("Continue", "alice:s1"))
    assert result["answer"] == "Recovered."
    assert len(graph.calls) == 2

    class AlwaysFailGraph(FakeGraph):
        async def ainvoke(self, input_value, config):
            raise RuntimeError("provider unavailable")

    failing = ExpenseAgent(
        AlwaysFailGraph(), "alice", MemoryStore(tmp_path / "other.db"), object()
    )
    with pytest.raises(AgentInvocationError, match="after one retry"):
        asyncio.run(failing.ainvoke("Continue", "alice:s2"))


def test_agent_extracts_tool_and_rag_evidence():
    state = {
        "messages": [
            SimpleNamespace(
                type="ai",
                content="",
                tool_calls=[{"name": "search_knowledge_base", "args": {"query": "emergency fund"}}],
            ),
            SimpleNamespace(
                type="tool",
                name="search_knowledge_base",
                content='{"sources": ["03_emergency_fund_and_savings.md"]}',
            ),
            SimpleNamespace(type="ai", content="Common guidance is 3-6 months."),
        ]
    }
    evidence = _extract_evidence(state)
    assert evidence["answer"] == "Common guidance is 3-6 months."
    assert evidence["tools"][0]["args"] == {"query": "emergency fund"}
    assert evidence["tools"][0]["result"]
    assert evidence["retrieved_chunks"][0]["name"] == "search_knowledge_base"


def test_prompt_contains_required_boundaries():
    for requirement in ("TOOL SELECTION", "HUMAN OVERSIGHT", "PRIVACY", "source filename"):
        assert requirement.casefold() in SYSTEM_PROMPT.casefold()


def test_agent_invokes_mcp_with_a_fake_model(tmp_path):
    pytest.importorskip("langchain_core")
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class FakeChatModel(BaseChatModel):
        @property
        def _llm_type(self):
            return "local-test"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if isinstance(messages[-1], HumanMessage) and messages[-1].content == "Run anomaly tool and search emergency fund":
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "detect_anomalies",
                            "args": {"month": "2026-10"},
                            "id": "anomaly-call",
                            "type": "tool_call",
                        },
                        {
                            "name": "search_knowledge_base",
                            "args": {"query": "emergency fund"},
                            "id": "rag-call",
                            "type": "tool_call",
                        },
                    ],
                )
            else:
                message = AIMessage(content="I found the unusual Daraz and Foodpanda entries.")
            return ChatResult(generations=[ChatGeneration(message=message)])

    async def run():
        runtime = await create_expense_agent(
            "agent_test_user",
            model=FakeChatModel(),
            memory=MemoryStore(tmp_path / "memory.db"),
        )
        return await runtime.ainvoke(
            "Run anomaly tool and search emergency fund", "agent_test_user:scenario"
        )

    result = asyncio.run(run())
    assert result["answer"] == "I found the unusual Daraz and Foodpanda entries."
    assert any(tool["name"] == "detect_anomalies" for tool in result["tools"])
    assert any(tool["name"] == "search_knowledge_base" for tool in result["tools"])
    assert "98000" in str(result["tools"])
    assert "03_emergency_fund_and_savings.md" in str(result["retrieved_chunks"])
