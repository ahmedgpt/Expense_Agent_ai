"""Run deterministic assignment scenarios without an external LLM/API key."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault(
    "AGENT_LOG_PATH",
    str(PROJECT_ROOT / "demo" / "sample_session_logs" / "demo_tool_calls.jsonl"),
)

from src.logging_utils import log_tool_call, logged_tool
from src.memory_store import MemoryStore
from src.rag import search_knowledge_base
from src.transactions import (
    check_budget,
    list_transactions,
    monthly_summary,
)

OUT_PATH = PROJECT_ROOT / "demo" / "demo_output.md"
DEMO_DB = PROJECT_ROOT / "demo" / "sample_session_logs" / "demo_memory.db"


def _record(lines: list[str], title: str, data: Any) -> None:
    lines.append(f"\n### {title}\n")
    if isinstance(data, str):
        lines.append(data)
    else:
        lines.append("```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```")


def _staged_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "change_id"}


def _logged(name: str, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return logged_tool(name)(function)(*args, **kwargs)


async def _call_mcp_anomaly_tool(month: str) -> dict[str, Any]:
    """Invoke the assignment's anomaly tool through an actual MCP stdio session."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    started = time.perf_counter()
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server"],
        cwd=str(PROJECT_ROOT),
    )
    try:
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.call_tool("detect_anomalies", {"month": month})
        if response.isError:
            raise RuntimeError(f"MCP detect_anomalies failed: {response.content}")
        structured = getattr(response, "structuredContent", None)
        if structured is None:
            structured = getattr(response, "structured_content", None)
        if isinstance(structured, dict):
            result = structured
        else:
            result = {}
            for block in response.content:
                text = getattr(block, "text", "")
                if text:
                    result = json.loads(text)
                    break
            if not result:
                raise RuntimeError("MCP detect_anomalies returned no structured content.")
    except Exception as exc:
        log_tool_call(
            "detect_anomalies",
            {"month": month},
            {"error": str(exc)},
            (time.perf_counter() - started) * 1000,
        )
        raise
    log_tool_call(
        "detect_anomalies",
        {"month": month},
        result,
        (time.perf_counter() - started) * 1000,
    )
    return result


def run_demo() -> Path:
    """Execute scenarios A-G with deterministic tools and save a Markdown transcript."""
    lines = [
        "# Personal Expense Management Agent — Reproducible Demo",
        "",
        "Offline deterministic run: transaction and memory tools are real; LLM responses "
        "are scripted so no API key or network call is required.",
    ]

    oct_summary = _logged("monthly_summary", monthly_summary, "2026-10")
    sep_summary = _logged("monthly_summary", monthly_summary, "2026-09")
    dining_oct = oct_summary["by_category"]["Dining Out"]["spent_pkr"]
    dining_sep = sep_summary["by_category"]["Dining Out"]["spent_pkr"]
    october_dining = _logged(
        "list_transactions", list_transactions, "Dining Out", "2026-10", 100
    )["transactions"]
    largest = max(october_dining, key=lambda row: row["amount_pkr"])
    _record(
        lines,
        "A. Short-term conversational context",
        {
            "turn_1": f"October Dining Out spending was PKR {dining_oct:,.0f}.",
            "turn_2": f"September was PKR {dining_sep:,.0f}; October was "
            f"PKR {dining_oct - dining_sep:,.0f} "
            f"{'higher' if dining_oct >= dining_sep else 'lower'}.",
            "turn_3": {
                "biggest_transaction": largest,
                "source": "data/transactions.csv",
            },
        },
    )

    memory = MemoryStore(DEMO_DB)
    _logged("recall_memory", memory.recall_memory, "demo_alice")
    _logged("save_memory", memory.stage_memory, "demo_alice", "budget", "Dining Out", "15000")
    session_one = _logged("save_memory", memory.confirm_latest_memory, "demo_alice")
    _logged("save_memory", memory.stage_memory, "demo_alice", "goal", "emergency fund", "6 months")
    goal_saved = _logged("save_memory", memory.confirm_latest_memory, "demo_alice")
    recall_script = (
        "import json,sys; from src.memory_store import MemoryStore; "
        "print(json.dumps(MemoryStore(sys.argv[1]).recall_memory('demo_alice')))"
    )
    process_result = subprocess.run(
        [sys.executable, "-c", recall_script, str(DEMO_DB)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    session_two = json.loads(process_result.stdout)
    log_tool_call("recall_memory", {"user_id": "demo_alice"}, session_two, 0)
    budget_check = _logged(
        "check_budget",
        check_budget,
        "Dining Out",
        "2026-10",
        session_two["budgets"]["Dining Out"],
    )
    _record(
        lines,
        "B. Long-term memory across sessions",
        {
            "session_1_confirmed_budget": session_one,
            "session_1_confirmed_goal": goal_saved,
            "session_2_recalled": session_two,
            "session_2_budget_check": budget_check,
        },
    )

    rag_results = []
    for query in ("What is the 50/30/20 rule?", "How big should my emergency fund be?", "Avalanche vs snowball?"):
        result = search_knowledge_base(query, k=2)
        rag_results.append(
            {
                "question": query,
                "sources": result["sources"],
                "backend": result["backend"],
                "retrieved_chunks": result["results"],
                "scripted_answer": (
                    "The retrieved guidance is summarized below; see the listed source file(s)."
                ),
            }
        )
    rag_results.append(
        {
            "question": "Which stock should I buy?",
            "answer": "I can’t recommend specific investments; that is outside my scope, and the supplied documents do not cover stock picks.",
        }
    )
    _record(lines, "C. RAG-grounded finance concepts and out-of-scope request", rag_results)

    anomaly_result = asyncio.run(_call_mcp_anomaly_tool("2026-10"))
    planted = [
        item
        for item in anomaly_result["anomalies"]
        if item.get("merchant") in {"Daraz", "Foodpanda"}
    ]
    _record(
        lines,
        "D. MCP anomaly tool",
        {
            "tool": "detect_anomalies",
            "args": {"month": "2026-10"},
            "result": planted,
            "agent_response": [
                "The tool shows a Daraz charge of PKR 98,000 on 2026-10-20, which is much higher than the category median. Was this expected?",
                "It also shows two Foodpanda charges of PKR 2,150 on 2026-10-21. Could you check whether both are valid?",
            ],
        },
    )

    summary_for_plan = _logged("monthly_summary", monthly_summary, "2026-10")
    tips = search_knowledge_base("ways to reduce everyday spending", k=2)
    before_plan = [
        "Get October category totals from monthly_summary.",
        "Retrieve cost-saving guidance from search_knowledge_base.",
        "Identify candidate reductions totaling PKR 10,000; ask before any action.",
    ]
    after_plan = [
        "Update the rent assumption by +PKR 5,000 only after confirmation.",
        "Find PKR 15,000 of cuts to offset the rent increase and still reduce total spending by PKR 10,000.",
        "Use the October summary and retrieved tips; present options and ask before saving.",
    ]
    staged_rent = _staged_summary(
        _logged(
            "save_memory",
            memory.stage_memory,
            "demo_alice",
            "profile",
            "monthly_rent_increase_pkr",
            "5000",
        )
    )
    _record(
        lines,
        "E. Planning and replanning after a change",
        {
            "plan_before_change": before_plan,
            "tools_used": {
                "monthly_summary": summary_for_plan["total_pkr"],
                "saving_tip_sources": tips["sources"],
            },
            "change_event": "Actually my rent just went up by PKR 5,000.",
            "plan_after_change": after_plan,
            "confirmation": "Please confirm before the rent assumption is saved.",
            "staged_change_not_applied": staged_rent,
        },
    )

    invalid_month = _logged("monthly_summary", monthly_summary, "2026-13")
    missing_csv = _logged("monthly_summary", monthly_summary, "2026-10", "missing.csv")
    empty_rag = search_knowledge_base("quasars and black holes")
    attempts = 0

    def fake_transient_model() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated temporary model API error")
        return "retry succeeded"

    try:
        try:
            fake_transient_model()
        except RuntimeError as first_error:
            retry_output = {"first_error": str(first_error), "retry_result": fake_transient_model()}
    except RuntimeError as retry_error:
        retry_output = {"error": f"I couldn't complete the model request after retrying: {retry_error}"}
    _record(
        lines,
        "F. Error handling",
        {
            "invalid_month": invalid_month,
            "missing_csv": missing_csv,
            "empty_retrieval": empty_rag,
            "simulated_llm_retry": retry_output,
        },
    )

    previous_budget = MemoryStore(DEMO_DB).get_budget("demo_alice", "Dining Out")
    staged_change = _staged_summary(
        _logged("save_memory", memory.stage_memory, "demo_alice", "budget", "Dining Out", "17000")
    )
    after_unconfirmed = MemoryStore(DEMO_DB).get_budget("demo_alice", "Dining Out")
    _record(
        lines,
        "G. Human oversight",
        {
            "request": "Change the Dining Out budget to PKR 17,000.",
            "agent_response": "I can change it from PKR 15,000 to PKR 17,000 after your explicit confirmation. Should I save this?",
            "staged_change": staged_change,
            "budget_before": previous_budget,
            "budget_after_without_confirmation": after_unconfirmed,
        },
    )

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Demo transcript written to {OUT_PATH}")
    return OUT_PATH


if __name__ == "__main__":
    run_demo()
