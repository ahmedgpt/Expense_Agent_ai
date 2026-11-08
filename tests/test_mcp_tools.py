from src.transactions import (
    categorize_transaction,
    check_budget,
    detect_anomalies,
    list_transactions,
    monthly_summary,
)


def test_categorize_transaction_and_ambiguity():
    assert categorize_transaction("Daraz", 98000)["category"] == "Shopping"
    ambiguous = categorize_transaction("Carrefour", 23000)
    assert ambiguous["category"] == "Groceries"
    assert ambiguous["confirmation_needed"] is True
    assert "error" in categorize_transaction("", 5)


def test_monthly_summary_and_invalid_input():
    summary = monthly_summary("2026-10")
    assert summary["month"] == "2026-10"
    assert summary["by_category"]["Dining Out"]["spent_pkr"] > 0
    assert "error" in monthly_summary("2026-13")
    assert "error" in monthly_summary("2026-10", "missing.csv")


def test_check_budget_status_and_validation():
    result = check_budget("Dining Out", "2026-10", 15000)
    assert result["spent_pkr"] > 0
    assert result["remaining_pkr"] == 15000 - result["spent_pkr"]
    assert result["status"] in {"on track", "warning", "overspent"}
    assert "error" in check_budget("Unknown", "2026-10", 15000)
    assert "error" in check_budget("Dining Out", "2026-13", 15000)


def test_anomaly_detection_finds_planted_transaction_and_duplicate():
    result = detect_anomalies("2026-10")
    records = result["anomalies"]
    assert any(
        item["type"] == "transaction_over_3x_category_median"
        and item["merchant"] == "Daraz"
        and item["amount_pkr"] == 98000
        for item in records
    )
    assert any(
        item["type"] == "possible_duplicate"
        and item["merchant"] == "Foodpanda"
        and item["amount_pkr"] == 2150
        and item["date"] == "2026-10-21"
        for item in records
    )
    assert "error" in detect_anomalies("2026-13")


def test_list_transactions_filters_and_validation():
    result = list_transactions("Dining Out", "2026-10", limit=10)
    assert result["count"] > 0
    assert all(row["category"] == "Dining Out" for row in result["transactions"])
    assert "error" in list_transactions(month="2026-13")
    assert "error" in list_transactions(limit=501)
