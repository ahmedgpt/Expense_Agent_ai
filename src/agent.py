"""LangChain agent runtime wired to MCP, RAG, and persistent memory."""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT
from src.logging_utils import log_tool_call
from src.memory_store import MemoryStore
from src.prompts import SYSTEM_PROMPT
from src.rag import search_knowledge_base

_AFFIRMATIVE = re.compile(
    r"^\s*(yes|yes please|yes,? save it|confirm|confirmed|i confirm|go ahead|save it|do that)[.! ]*\s*$",
    re.IGNORECASE,
)


class AgentInvocationError(RuntimeError):
    """Raised when a live model still fails after the single retry."""


class ExpenseAgent:
    """A user-scoped chat agent with session state and evidence extraction."""

    def __init__(
        self,
        graph: Any,
        user_id: str,
        memory: MemoryStore,
        mcp_client: Any,
        verbose: bool = False,
    ):
        self.graph = graph
        self.user_id = user_id
        self.memory = memory
        self.mcp_client = mcp_client
        self.verbose = verbose
        self._initialized_threads: set[str] = set()
        self._confirmation_context = {"confirmed": False}

    async def ainvoke(self, text: str, thread_id: str) -> dict[str, Any]:
        """Send a message, retry once after model errors, and return answer/evidence."""
        if not text.strip():
            return {"answer": "Please enter a message.", "tools": [], "retrieved_chunks": []}
        self._confirmation_context["confirmed"] = bool(
            self.memory.has_pending_memory(self.user_id) and _AFFIRMATIVE.fullmatch(text)
        )
        messages: list[Any] = []
        recalled_memory: dict[str, Any] | None = None
        if thread_id not in self._initialized_threads:
            recalled_memory = self.memory.recall_memory(self.user_id)
            log_tool_call("recall_memory", {"user_id": self.user_id}, recalled_memory, 0)
            messages.append(
                {
                    "role": "system",
                    "content": f"Session-start memory retrieval: {recalled_memory}",
                }
            )
            self._initialized_threads.add(thread_id)
        messages.append({"role": "user", "content": text})
        config = {"configurable": {"thread_id": thread_id}}
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                state = await self.graph.ainvoke({"messages": messages}, config=config)
                evidence = _extract_evidence(state)
                evidence["memory_entries"] = recalled_memory or {}
                return evidence
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.25)
        raise AgentInvocationError(f"Agent request failed after one retry: {last_error}") from last_error


def _extract_evidence(state: Any) -> dict[str, Any]:
    messages = state.get("messages", []) if isinstance(state, dict) else []
    answer = ""
    tool_calls: list[dict[str, Any]] = []
    retrieved: list[dict[str, Any]] = []
    for message in messages:
        message_type = getattr(message, "type", "")
        if message_type == "ai" or message.__class__.__name__ == "AIMessage":
            content = getattr(message, "content", "")
            if isinstance(content, str) and content:
                answer = content
            for call in getattr(message, "tool_calls", []) or []:
                tool_calls.append(
                    {
                        "name": call.get("name"),
                        "args": call.get("args", {}),
                    }
                )
        if message_type == "tool" or message.__class__.__name__ == "ToolMessage":
            name = getattr(message, "name", "") or ""
            content = getattr(message, "content", "")
            entry = {"name": name, "result": content}
            for call in reversed(tool_calls):
                if call["name"] == name and "result" not in call:
                    call["result"] = content
                    break
            if name == "search_knowledge_base":
                retrieved.append(entry)
    if not answer and messages:
        answer = str(getattr(messages[-1], "content", ""))
    return {"answer": answer, "tools": tool_calls, "retrieved_chunks": retrieved}


async def create_expense_agent(
    user_id: str,
    model: Any | None = None,
    memory: MemoryStore | None = None,
    mcp_client: Any | None = None,
    verbose: bool = False,
) -> ExpenseAgent:
    """Build the live agent and connect transaction tools over MCP stdio."""
    try:
        from langchain.agents import create_agent
        from langchain_core.tools import tool
        from langgraph.checkpoint.memory import InMemorySaver
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:
        raise RuntimeError("Agent dependencies are missing; install requirements.txt.") from exc

    memory_store = memory or MemoryStore()
    confirmation_context = {"confirmed": False}

    @tool
    def recall_memory() -> dict[str, Any]:
        """Retrieve the user's stored profile, budgets, goals, and notes."""
        started = time.perf_counter()
        result = memory_store.recall_memory(user_id)
        log_tool_call("recall_memory", {"user_id": user_id}, result, (time.perf_counter() - started) * 1000)
        return result

    @tool
    def save_memory(kind: str, key: str, value: str, confirmed: bool = False) -> dict[str, Any]:
        """Save a budget, goal, preference, or note only after user confirmation."""
        started = time.perf_counter()
        if confirmation_context["confirmed"]:
            result = memory_store.confirm_latest_memory(user_id)
        else:
            result = memory_store.stage_memory(user_id, kind, key, value)
        log_tool_call(
            "save_memory",
            {
                "user_id": user_id,
                "kind": kind,
                "key": key,
                "value": value,
                "confirmed_by_user": confirmation_context["confirmed"],
            },
            result,
            (time.perf_counter() - started) * 1000,
        )
        return result

    @tool("search_knowledge_base")
    def search_knowledge_base_tool(query: str) -> dict[str, Any]:
        """Search the finance knowledge documents and return cited text chunks."""
        return search_knowledge_base(query)

    if mcp_client is None:
        mcp_client = MultiServerMCPClient(
            {
                "expense-data": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": ["-m", "src.mcp_server"],
                    "cwd": str(Path(PROJECT_ROOT)),
                }
            }
        )
    mcp_tools = await mcp_client.get_tools()
    tools = [*mcp_tools, recall_memory, save_memory, search_knowledge_base_tool]
    chat_model = model
    if chat_model is None:
        from src.config import create_chat_model

        chat_model = create_chat_model()
    graph = create_agent(
        model=chat_model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
    )
    runtime = ExpenseAgent(graph, user_id, memory_store, mcp_client, verbose)
    runtime._confirmation_context = confirmation_context
    return runtime
