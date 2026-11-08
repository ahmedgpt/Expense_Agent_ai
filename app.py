"""Streamlit chat interface for the Personal Expense Management Agent."""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from typing import Any

import streamlit as st

from src.agent import AgentInvocationError, create_expense_agent
from src.logging_utils import log_tool_call
from src.memory_store import MemoryStore


@st.cache_resource(show_spinner=False)
def get_agent(user_id: str):
    """Reuse the shared agent implementation for each user in this app process."""
    return asyncio.run(create_expense_agent(user_id=user_id))


def _format_memory_change(pending: dict[str, Any]) -> str:
    key = pending["memory_key"]
    value = pending["value"]
    if pending["kind"] == "budget":
        try:
            amount = float(value)
        except (TypeError, ValueError):
            amount = None
        if amount is None or not math.isfinite(amount) or amount <= 0:
            value = f"{value} (invalid budget amount; cancel this change)"
        else:
            value = f"PKR {amount:,.0f}"
    return f"{pending['kind'].title()}: **{key}** → **{value}**"


def _render_rag_result(raw_result: Any) -> None:
    try:
        result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except json.JSONDecodeError:
        st.code(str(raw_result))
        return
    if not isinstance(result, dict):
        st.code(str(raw_result))
        return
    results = result.get("results", [])
    if not results:
        st.info("No matching knowledge chunks were retrieved.")
    for chunk in results:
        st.markdown(f"**Source:** `{chunk.get('source', 'unknown')}`")
        st.caption(
            f"Chunk {chunk.get('chunk_id', '?')} · "
            f"retrieval score {chunk.get('score', 'n/a')}"
        )
        st.write(chunk.get("content", ""))


def _render_evidence(evidence: dict[str, Any], show_evidence: bool) -> None:
    if not show_evidence:
        return
    tools = evidence.get("tools", [])
    chunks = evidence.get("retrieved_chunks", [])
    memory_entries = evidence.get("memory_entries", {})
    with st.expander(
        f"Evidence ({len(tools)} tool call(s))", expanded=False
    ):
        if memory_entries:
            st.markdown("#### Long-term memory available to this session")
            st.json(memory_entries)
        if not tools and not chunks:
            if not memory_entries:
                st.caption("No tools, memory entries, or knowledge chunks were used for this reply.")
        for index, tool_call in enumerate(tools, start=1):
            st.markdown(f"**{index}. {tool_call.get('name', 'Tool')}**")
            st.json(tool_call.get("args", {}))
            if "result" in tool_call:
                st.code(str(tool_call["result"]), language="json")
        if chunks:
            st.markdown("#### Retrieved knowledge")
            for chunk in chunks:
                _render_rag_result(chunk.get("result", ""))


def _run_turn(agent: Any, text: str, thread_id: str) -> dict[str, Any]:
    return asyncio.run(agent.ainvoke(text, thread_id))


def main() -> None:
    st.set_page_config(page_title="Expense Assistant", page_icon="💸", layout="wide")
    st.title("💸 Personal Expense Assistant")
    st.caption("Ask about spending, budgets, savings guidance, and your remembered goals.")

    with st.sidebar:
        st.header("Your session")
        user_id = st.text_input("User ID", value=st.session_state.get("user_id", "alice"))
        user_id = user_id.strip()
        if not user_id:
            st.warning("Enter a user ID to continue.")
            st.stop()
        if user_id != st.session_state.get("active_user_id"):
            st.session_state["active_user_id"] = user_id
            st.session_state["thread_id"] = str(uuid.uuid4())
            st.session_state["messages"] = []

        st.caption(f"Session: `{st.session_state.get('thread_id', '')[:8]}`")
        if st.button("＋ New session", use_container_width=True):
            st.session_state["thread_id"] = str(uuid.uuid4())
            st.session_state["messages"] = []
            st.rerun()

        show_evidence = st.toggle("Show evidence", value=True)
        st.divider()

        memory = MemoryStore()
        recalled = memory.recall_memory(user_id)
        st.subheader("Stored budgets")
        if recalled["budgets"]:
            for category, amount in recalled["budgets"].items():
                st.metric(category, f"PKR {amount:,.0f}")
        else:
            st.caption("No saved budgets yet.")

        st.subheader("Goals")
        if recalled["goals"]:
            for goal, value in recalled["goals"].items():
                st.write(f"**{goal}:** {value}")
        else:
            st.caption("No saved goals yet.")

        pending = memory.get_pending_memory(user_id)
        if pending:
            st.divider()
            st.subheader("Confirm memory change")
            st.write(_format_memory_change(pending))
            confirm_col, reject_col = st.columns(2)
            if confirm_col.button("Yes, save", type="primary", use_container_width=True):
                started = time.perf_counter()
                result = memory.confirm_latest_memory(user_id)
                log_tool_call(
                    "save_memory",
                    {"user_id": user_id, "confirmed_in_ui": True},
                    result,
                    (time.perf_counter() - started) * 1000,
                )
                if result.get("saved"):
                    st.session_state["messages"].append(
                        {
                            "role": "assistant",
                            "content": f"Saved the confirmed {_format_memory_change(pending).replace('**', '')}.",
                            "evidence": {"tools": [], "retrieved_chunks": []},
                        }
                    )
                    st.rerun()
                st.error(result.get("error", "Could not save this change."))
            if reject_col.button("No, cancel", use_container_width=True):
                started = time.perf_counter()
                result = memory.discard_latest_memory(user_id)
                log_tool_call(
                    "discard_memory_change",
                    {"user_id": user_id},
                    result,
                    (time.perf_counter() - started) * 1000,
                )
                st.session_state["messages"].append(
                    {
                        "role": "assistant",
                        "content": "Cancelled. No memory change was saved.",
                        "evidence": {"tools": [], "retrieved_chunks": []},
                    }
                )
                st.rerun()

    try:
        agent = get_agent(user_id)
    except RuntimeError as exc:
        st.error(f"Could not start the expense agent: {exc}")
        st.info("Add your Groq API key to the project’s `.env` file, then restart Streamlit.")
        st.stop()

    thread_id = f"{user_id}:{st.session_state['thread_id']}"
    for message in st.session_state.get("messages", []):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                _render_evidence(message.get("evidence", {}), show_evidence)

    prompt = st.chat_input("Ask about spending, budgets, or a finance concept")
    if prompt:
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response = _run_turn(agent, prompt, thread_id)
                except AgentInvocationError as exc:
                    response = {
                        "answer": f"I couldn't complete that request after retrying. {exc}",
                        "tools": [],
                        "retrieved_chunks": [],
                    }
            st.markdown(response["answer"])
            _render_evidence(response, show_evidence)
        st.session_state["messages"].append(
            {
                "role": "assistant",
                "content": response["answer"],
                "evidence": response,
            }
        )
        st.rerun()


if __name__ == "__main__":
    main()
