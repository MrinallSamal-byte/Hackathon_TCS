"""Memory tests — personalization math, persistence, and chat integration (offline)."""
from pathlib import Path

import backend.app as app_module
from backend.memory import MemoryStore, blank, boost_singles
from backend.store import MenuStore

ROOT = Path(__file__).resolve().parents[1]


def _mem():
    m = blank("s1")
    return m


def test_usual_budget_needs_two_points():
    ms = MemoryStore(path="/tmp/cb-mem-test.json")
    m = _mem()
    assert ms.usual_budget(m) is None
    m["budgets"] = [80]
    assert ms.usual_budget(m) is None
    m["budgets"] = [80, 100]
    assert ms.usual_budget(m) == 90.0


def test_cuisine_affinity():
    ms = MemoryStore(path="/tmp/cb-mem-test.json")
    m = _mem()
    cmap = {"a": "chinese", "b": "chinese", "c": "north_indian"}
    m["orders"] = {"a": 1}
    assert ms.cuisine_affinity(m, cmap) is None  # only 1 order
    m["orders"] = {"a": 1, "b": 1, "c": 1}
    assert ms.cuisine_affinity(m, cmap) == "chinese"


def test_boost_math_and_resort():
    store = MenuStore(ROOT / "data" / "menu_data.json")
    items = {i.id: i for i in store.all()}
    scored = [(items["samosa"], 50.0, {}), (items["maggi"], 55.0, {}),
              (items["vada_pav"], 52.0, {})]
    m = _mem()
    m["likes"] = {"samosa": 1, "maggi": -1}
    m["orders"] = {"vada_pav": 2}
    out = boost_singles(scored, m, {})
    by_id = {i.id: (s, b) for i, s, b in out}
    assert by_id["samosa"][0] == 58.0 and by_id["samosa"][1]["memory"] == 8.0
    assert by_id["maggi"][0] == 30.0  # 55 - 25
    assert by_id["vada_pav"][0] == 55.0  # 52 + 3 capped familiarity
    assert out[0][0].id == "samosa"  # liked jumps to top


def test_recorders_and_caps():
    ms = MemoryStore(path="/tmp/cb-mem-test.json")
    m = _mem()
    from backend.models import UserPreferences
    ms.record_chat(m, UserPreferences(budget=70, mood="happy"))
    assert m["budgets"] == [70.0] and m["moods"] == ["happy"] and m["chats"] == 1
    ms.record_feedback(m, "maggi", 1)
    ms.record_feedback(m, "samosa", -1)
    assert m["likes"] == {"maggi": 1, "samosa": -1}
    ms.record_order(m, ["maggi", "maggi", "samosa"])
    assert m["orders"] == {"maggi": 2, "samosa": 1}


def test_json_round_trip(tmp_path):
    p = tmp_path / "memory.json"
    ms = MemoryStore(path=p)
    m = ms.get("abc")
    m["budgets"] = [60, 80]
    ms.save("abc", m)
    ms2 = MemoryStore(path=p)
    assert ms2.get("abc")["budgets"] == [60, 80]


def test_supabase_memory_offline(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    from backend import db_supabase as db
    assert db.memory_get("x") is None
    assert db.memory_put("x", {}) is False


def test_chat_remembers_across_turns(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "memory_store", MemoryStore(path=tmp_path / "m.json"))
    c = TestClient(app_module.app)
    sid = "test-session-1"
    r1 = c.post("/chat", json={"message": "Rs 90, spicy veg", "session_id": sid}).json()
    assert r1["session_id"] == sid
    r2 = c.post("/chat", json={"message": "Rs 110, chinese", "prefs": r1["prefs"], "session_id": sid}).json()
    # third turn states no budget -> usual-budget fallback (median of 90,110 = 100)
    r3 = c.post("/chat", json={"message": "something comforting", "prefs": {"dietary_restrictions": ["veg"]}, "session_id": sid}).json()
    assert "usual Rs 100 budget" in r3["reply"]
    assert all(s["price"] <= 100 for s in r3["singles"])


def test_feedback_like_boosts_next_rank(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "memory_store", MemoryStore(path=tmp_path / "m.json"))
    c = TestClient(app_module.app)
    sid = "test-session-2"
    c.post("/chat", json={"message": "Rs 200, snacks", "session_id": sid})
    c.post("/feedback", json={"item_id": "samosa", "rating": 1, "session_id": sid})
    r = c.post("/chat", json={"message": "Rs 200, snacks", "session_id": sid}).json()
    samosa = next(s for s in r["singles"] if s["id"] == "samosa")
    assert samosa["breakdown"]["memory"] == 8.0
