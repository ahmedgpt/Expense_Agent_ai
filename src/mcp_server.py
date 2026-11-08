"""Official MCP FastMCP server exposing deterministic transaction tools."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.logging_utils import logged_tool
from src.transactions import (
    categorize_transaction as categorize,
    check_budget as check,
    detect_anomalies as anomalies,
    list_transactions as list_rows,
    monthly_summary as summary,
)

mcp = FastMCP("Personal Expense Management")


@mcp.tool()
@logged_tool("categorize_transaction")
def categorize_transaction(merchant: str, amount: float) -> dict[str, Any]:
    """Categorize a merchant using the provided expense taxonomy and return confidence."""
    return categorize(merchant, amount)


@mcp.tool()
@logged_tool("monthly_summary")
def monthly_summary(month: str) -> dict[str, Any]:
    """Return monthly transaction totals by category for a YYYY-MM month."""
    return summary(month)


@mcp.tool()
@logged_tool("check_budget")
def check_budget(category: str, month: str, budget: float) -> dict[str, Any]:
    """Compare category spending to a monthly limit, including status and spending pace."""
    return check(category, month, budget)


@mcp.tool()
@logged_tool("detect_anomalies")
def detect_anomalies(month: str) -> dict[str, Any]:
    """Find unusual transactions, possible duplicates, and category spending increases."""
    return anomalies(month)


@mcp.tool()
@logged_tool("list_transactions")
def list_transactions(
    category: str | None = None, month: str | None = None, limit: int = 100
) -> dict[str, Any]:
    """List transaction rows, optionally filtered by category and YYYY-MM month."""
    return list_rows(category=category, month=month, limit=limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
