from src.memory_store import MemoryStore


def test_memory_persists_across_new_connections(tmp_path):
    database = tmp_path / "memory.db"
    first = MemoryStore(database)
    saved = first.save_memory("alice", "budget", "Dining Out", "15000", confirmed=True)
    assert saved["saved"] is True
    first.save_memory("alice", "goal", "emergency fund", "6 months", confirmed=True)

    reopened = MemoryStore(database)
    remembered = reopened.recall_memory("alice")
    assert remembered["budgets"] == {"Dining Out": 15000.0}
    assert remembered["goals"] == {"emergency fund": "6 months"}
    assert reopened.recall_memory("bob")["budgets"] == {}


def test_memory_requires_confirmation_and_pending_change_can_be_confirmed(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    not_saved = store.save_memory("alice", "budget", "Dining Out", "15000")
    assert not_saved["confirmation_required"] is True
    assert store.recall_memory("alice")["budgets"] == {}

    staged = store.stage_memory("alice", "budget", "Dining Out", "15000")
    assert staged["confirmation_required"] is True
    assert store.has_pending_memory("alice")
    assert store.confirm_latest_memory("alice")["saved"] is True
    assert store.recall_memory("alice")["budgets"]["Dining Out"] == 15000.0
    assert not store.has_pending_memory("alice")


def test_invalid_memory_is_reported(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    result = store.save_memory("alice", "budget", "Unknown", "12000", confirmed=True)
    assert "error" in result


def test_pending_memory_can_be_inspected_and_declined(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    store.stage_memory("alice", "budget", "Dining Out", "15000")

    pending = store.get_pending_memory("alice")
    assert pending is not None
    assert pending["memory_key"] == "Dining Out"
    assert pending["value"] == "15000"

    declined = store.discard_latest_memory("alice")
    assert declined["discarded"] is True
    assert store.get_pending_memory("alice") is None
    assert store.recall_memory("alice")["budgets"] == {}


def test_invalid_budget_proposal_is_rejected_before_staging(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")

    result = store.stage_memory(
        "alice",
        "budget",
        "Dining Out",
        "Day1: Food&Drink 30PKR; Total 100PKR",
    )

    assert result == {"error": "A budget value must be a positive number."}
    assert store.get_pending_memory("alice") is None


def test_non_finite_budget_proposals_are_rejected(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")

    for value in ("nan", "inf", "-inf"):
        result = store.stage_memory("alice", "budget", "Dining Out", value)
        assert result == {"error": "A budget value must be a positive number."}
    assert store.get_pending_memory("alice") is None
