from app import _format_memory_change


def test_format_memory_change_handles_invalid_existing_budget():
    pending = {
        "kind": "budget",
        "memory_key": "Dining Out",
        "value": "Day1: Food&Drink 30PKR; Total 100PKR",
    }

    formatted = _format_memory_change(pending)

    assert "invalid budget amount; cancel this change" in formatted
    assert "Day1: Food&Drink 30PKR; Total 100PKR" in formatted
