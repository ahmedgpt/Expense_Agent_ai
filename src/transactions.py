"""Deterministic transaction-analysis functions used by the MCP server."""

from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

from src.config import DATA_PATH

CATEGORIES = (
    "Groceries",
    "Dining Out",
    "Transport",
    "Utilities",
    "Rent",
    "Health",
    "Education",
    "Entertainment",
    "Shopping",
    "Subscriptions",
    "Savings/Investments",
    "Debt Payments",
    "Transfers",
    "Other",
)


def _read_transactions(csv_path: str | Path | None = None) -> tuple[list[dict[str, Any]], str | None]:
    path = Path(csv_path) if csv_path is not None else DATA_PATH
    if not path.is_file():
        return [], f"Transaction file not found: {path}"
    try:
        with path.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            expected = {"date", "merchant", "amount_pkr"}
            if not reader.fieldnames or not expected.issubset(reader.fieldnames):
                return [], "Transaction CSV must contain date, merchant, amount_pkr columns."
            rows = []
            for line_number, row in enumerate(reader, start=2):
                try:
                    transaction_date = date.fromisoformat(row["date"])
                    amount = float(row["amount_pkr"])
                    if not math.isfinite(amount) or amount < 0:
                        raise ValueError("amount must be finite and non-negative")
                except (TypeError, ValueError) as exc:
                    return [], f"Invalid transaction at CSV line {line_number}: {exc}"
                rows.append(
                    {
                        "date": transaction_date.isoformat(),
                        "merchant": (row["merchant"] or "").strip(),
                        "amount_pkr": amount,
                    }
                )
    except OSError as exc:
        return [], f"Could not read transaction file: {exc}"
    return rows, None


def _valid_month(month: str) -> bool:
    return bool(re.fullmatch(r"(?!0000)\d{4}-(0[1-9]|1[0-2])", month))


def _month_error(month: str) -> dict[str, str] | None:
    if not isinstance(month, str) or not _valid_month(month):
        return {"error": "Invalid month; expected YYYY-MM with a valid month from 01 to 12."}
    return None


def _category_for(merchant: str) -> tuple[str, float]:
    name = merchant.casefold()
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Rent", ("rent", "landlord")),
        ("Groceries", ("supermarket", "carrefour", "imtiaz", "al-fatah", "grocery")),
        ("Dining Out", ("foodpanda", "kfc", "hardee", "starbucks", "restaurant", "cafe")),
        ("Transport", ("fuel", "shell", "careem", "uber", "indrive", "parking", "metro")),
        ("Utilities", ("electric", "lesco", "sngpl", "internet", "ptcl", "jazz", "zong", "top-up", "top up")),
        ("Subscriptions", ("spotify", "netflix", "youtube premium", "cloud storage")),
        ("Health", ("pharmacy", "clinic", "hospital", "lab test")),
        ("Education", ("udemy", "tuition", "course", "book")),
        ("Entertainment", ("cinepax", "cinema", "movie")),
        ("Shopping", ("daraz", "clothing", "electronics", "marketplace")),
        ("Transfers", ("transfer", "wallet top-up", "wallet top up")),
    )
    matches = [category for category, keywords in rules if any(word in name for word in keywords)]
    if len(matches) == 1:
        return matches[0], 0.95
    if len(matches) > 1:
        return matches[0], 0.45
    return "Other", 0.25


def categorize_transaction(merchant: str, amount: float) -> dict[str, Any]:
    """Classify a merchant using the supplied taxonomy and report confidence."""
    if not isinstance(merchant, str) or not merchant.strip():
        return {"error": "merchant must be a non-empty string."}
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return {"error": "amount must be a non-negative number."}
    if not math.isfinite(value) or value < 0:
        return {"error": "amount must be a non-negative number."}
    category, confidence = _category_for(merchant)
    response: dict[str, Any] = {
        "merchant": merchant.strip(),
        "amount_pkr": value,
        "category": category,
        "confidence": confidence,
    }
    if confidence < 0.6 or value > 20_000:
        response["confirmation_needed"] = True
        response["message"] = "Classification is uncertain; confirm the category with the user."
    return response


def monthly_summary(month: str, csv_path: str | Path | None = None) -> dict[str, Any]:
    """Return transaction totals by taxonomy category for a YYYY-MM month."""
    error = _month_error(month)
    if error:
        return error
    rows, read_error = _read_transactions(csv_path)
    if read_error:
        return {"error": read_error}
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row["date"].startswith(month):
            category, _ = _category_for(row["merchant"])
            totals[category] += row["amount_pkr"]
            counts[category] += 1
    return {
        "month": month,
        "total_pkr": round(sum(totals.values()), 2),
        "by_category": {
            category: {"spent_pkr": round(totals.get(category, 0), 2), "transactions": counts.get(category, 0)}
            for category in CATEGORIES
        },
        "source": "data/transactions.csv",
    }


def check_budget(
    category: str, month: str, budget: float, csv_path: str | Path | None = None
) -> dict[str, Any]:
    """Compare category spend to a user-provided monthly budget and spending pace."""
    error = _month_error(month)
    if error:
        return error
    if category not in CATEGORIES:
        return {"error": f"Unknown category. Use one of: {', '.join(CATEGORIES)}."}
    try:
        limit = float(budget)
    except (TypeError, ValueError):
        return {"error": "budget must be a positive number."}
    if not math.isfinite(limit) or limit <= 0:
        return {"error": "budget must be a positive number."}
    summary = monthly_summary(month, csv_path)
    if "error" in summary:
        return summary
    spent = summary["by_category"][category]["spent_pkr"]
    percent = spent / limit * 100
    status = "overspent" if percent > 100 else "warning" if percent >= 80 else "on track"
    year, month_number = (int(part) for part in month.split("-"))
    days_in_month = (date(year + (month_number == 12), month_number % 12 + 1, 1) - date(year, month_number, 1)).days
    today = date.today()
    elapsed_days = min(today.day, days_in_month) if (today.year, today.month) == (year, month_number) else days_in_month
    elapsed_percent = elapsed_days / days_in_month * 100
    return {
        "category": category,
        "month": month,
        "budget_pkr": round(limit, 2),
        "spent_pkr": round(spent, 2),
        "remaining_pkr": round(limit - spent, 2),
        "percent_used": round(percent, 2),
        "status": status,
        "days_elapsed": elapsed_days,
        "days_in_month": days_in_month,
        "month_elapsed_percent": round(elapsed_percent, 2),
        "pace": "ahead of pace" if percent > elapsed_percent else "within pace",
        "source": "data/transactions.csv",
    }


def detect_anomalies(month: str, csv_path: str | Path | None = None) -> dict[str, Any]:
    """Find high transactions, possible duplicates, and category spend increases."""
    error = _month_error(month)
    if error:
        return error
    rows, read_error = _read_transactions(csv_path)
    if read_error:
        return {"error": read_error}
    month_rows = [row for row in rows if row["date"].startswith(month)]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in month_rows:
        row["category"] = _category_for(row["merchant"])[0]
        by_category[row["category"]].append(row)

    findings: list[dict[str, Any]] = []
    for category, category_rows in by_category.items():
        typical = median(row["amount_pkr"] for row in category_rows)
        for row in category_rows:
            if typical > 0 and row["amount_pkr"] > 3 * typical:
                findings.append(
                    {
                        "type": "transaction_over_3x_category_median",
                        "date": row["date"],
                        "merchant": row["merchant"],
                        "amount_pkr": row["amount_pkr"],
                        "category": category,
                        "category_median_pkr": typical,
                    }
                )

    seen_pairs: set[tuple[str, str, str]] = set()
    for index, first in enumerate(month_rows):
        for second in month_rows[index + 1 :]:
            delta = abs((date.fromisoformat(second["date"]) - date.fromisoformat(first["date"])).days)
            key = (first["merchant"].casefold(), str(first["amount_pkr"]), min(first["date"], second["date"]))
            if first["merchant"].casefold() == second["merchant"].casefold() and first["amount_pkr"] == second["amount_pkr"] and delta <= 2 and key not in seen_pairs:
                seen_pairs.add(key)
                findings.append(
                    {
                        "type": "possible_duplicate",
                        "date": second["date"],
                        "merchant": second["merchant"],
                        "amount_pkr": second["amount_pkr"],
                        "other_date": first["date"],
                        "other_amount_pkr": first["amount_pkr"],
                    }
                )

    year, month_number = (int(part) for part in month.split("-"))
    previous_months = []
    for offset in range(1, 4):
        prior_number = month_number - offset
        prior_year = year
        while prior_number <= 0:
            prior_number += 12
            prior_year -= 1
        previous_months.append(f"{prior_year:04d}-{prior_number:02d}")
    prior_rows = [row for row in rows if any(row["date"].startswith(prior) for prior in previous_months)]
    prior_totals: dict[str, float] = defaultdict(float)
    current_totals: dict[str, float] = defaultdict(float)
    for row in prior_rows:
        prior_totals[_category_for(row["merchant"])[0]] += row["amount_pkr"]
    for row in month_rows:
        current_totals[_category_for(row["merchant"])[0]] += row["amount_pkr"]
    available_prior = sum(any(row["date"].startswith(prior) for row in rows) for prior in previous_months)
    if available_prior:
        for category, current_total in current_totals.items():
            average = prior_totals[category] / available_prior
            if average > 0 and current_total > 1.5 * average:
                findings.append(
                    {
                        "type": "category_over_50_percent_vs_prior_month_average",
                        "category": category,
                        "amount_pkr": round(current_total, 2),
                        "prior_month_average_pkr": round(average, 2),
                        "prior_months_available": available_prior,
                    }
                )
    return {
        "month": month,
        "anomalies": findings,
        "source": "data/transactions.csv",
        "note": "Category trend uses up to three available prior months.",
    }


def list_transactions(
    category: str | None = None,
    month: str | None = None,
    limit: int = 100,
    csv_path: str | Path | None = None,
) -> dict[str, Any]:
    """List matching transactions, optionally filtered by category and month."""
    if month is not None:
        error = _month_error(month)
        if error:
            return error
    if category is not None and category not in CATEGORIES:
        return {"error": f"Unknown category. Use one of: {', '.join(CATEGORIES)}."}
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        return {"error": "limit must be an integer from 1 to 500."}
    rows, read_error = _read_transactions(csv_path)
    if read_error:
        return {"error": read_error}
    matches = []
    for row in rows:
        row_category, _ = _category_for(row["merchant"])
        if (month is None or row["date"].startswith(month)) and (category is None or row_category == category):
            matches.append({**row, "category": row_category})
    return {"transactions": matches[:limit], "count": len(matches[:limit]), "source": "data/transactions.csv"}
