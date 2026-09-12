"""Tests for the 7 user-benefit features (all offline)."""
from datetime import datetime, timedelta
from pathlib import Path

import backend.app as app_module
from backend.nlu import normalize_hinglish, parse_goal, parse_one_shot
from backend.queue import counter_of, effective_prep, queues_at
from backend.recommender import recommend, soft_score
from backend.models import UserPreferences
from backend.store import MenuStore

ROOT = Path(__file__).resolve().parents[1]
STORE = MenuStore(ROOT / "data" / "menu_data.json")


# ---------- 1. ratings on cards ----------
def test_ratings_surface_on_cards(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "memory_store",
                        __import__("backend.memory", fromlist=["MemoryStore"]).MemoryStore(path=tmp_path / "m.json"))
    c = TestClient(app_module.app)
    before = app_module.store.get("maggi").popularity_score
    c.post("/feedback", json={"item_id": "maggi", "rating": 1})
    c.post("/feedback", json={"item_id": "maggi", "rating": 1})
    maggi = c.get("/menu", params={"q": "Masala Maggi"}).json()["items"][0]
    assert maggi["id"] == "maggi" and maggi["likes"] >= 2
    # cleanup the two test rows + restore popularity
    import json as _json
    fp = ROOT / "data" / "feedback_log.json"
    rows = _json.loads(fp.read_text())
    rows = [x for x in rows if x.get("item_id") != "maggi"]
    fp.write_text(_json.dumps(rows, indent=2))
    app_module.store.get("maggi").popularity_score = before
    app_module.store.save()


# ---------- 2. Hinglish ----------
def test_hinglish_one_shot():
    p = parse_one_shot("sasta teekha khana 50 rupaye me, bahut bhukh, jaldi")
    assert p.budget == 50 and "spicy" in p.cravings
    assert p.hunger == "very_hungry" and p.max_prep_time == 5


def test_hinglish_meal_and_negation():
    p = parse_one_shot("subah ka breakfast, bina pyaaz wala")
    assert p.meal == "breakfast" and p.no_onion_garlic is True


def test_hinglish_normalize_idempotent():
    assert normalize_hinglish("Hello I want maggi") == "hello i want maggi"


# ---------- 5. nutrition goals ----------
def test_goal_parsing():
    assert parse_goal("gym ke liye high protein") == "high_protein"
    assert parse_goal("I am on a diet, low cal please") == "low_calorie"
    assert parse_goal("just tasty food") is None


def test_goal_scoring_boost():
    items = {i.id: i for i in STORE.all()}
    p = UserPreferences(budget=500, goal="high_protein")
    s_hi, parts_hi = soft_score(items["chicken_biryani"], p, "lunch")
    s_lo, parts_lo = soft_score(items["samosa"], p, "lunch")
    assert parts_hi["goal"] == 12.0 and parts_lo["goal"] == 0.0
    assert s_hi > s_lo
    p2 = UserPreferences(budget=500, goal="low_calorie")
    _, pl = soft_score(items["green_tea"], p2, "lunch")
    _, ph = soft_score(items["chicken_biryani"], p2, "lunch")
    assert pl["goal"] == 12.0 and ph["goal"] == 0.0


def test_goal_menu_sort():
    from fastapi.testclient import TestClient
    c = TestClient(app_module.app)
    r = c.get("/menu", params={"goal": "high_protein"}).json()
    prots = [i["protein_g"] for i in r["items"]]
    assert prots == sorted(prots, reverse=True)
    r2 = c.get("/menu", params={"goal": "low_calorie"}).json()
    cals = [i["calories"] for i in r2["items"]]
    assert cals == sorted(cals)


# ---------- 6. live queues ----------
def test_queue_peaks_pure():
    lunch = datetime(2026, 9, 12, 13, 0)
    qs = queues_at(lunch, overrides={})
    assert qs == {"main": 10, "snacks": 5, "beverages": 3}
    night = datetime(2026, 9, 12, 3, 0)
    assert queues_at(night, overrides={}) == {"main": 0, "snacks": 0, "beverages": 0}
    assert counter_of("main_course") == "main"
    assert counter_of("beverage") == "beverages"
    assert effective_prep(8, "snack", qs) == 13


def test_queue_filters_and_eta():
    p = UserPreferences(budget=500, max_prep_time=12)
    maggi = next(i for i in STORE.all() if i.id == "maggi")  # snack, prep 8
    res = recommend(STORE.all(), p, meal="lunch",
                    queue={"main": 0, "snacks": 10, "beverages": 0})
    ids = [it.id for it, _, _ in res["singles"]]
    assert "maggi" not in ids  # 8 + 10 > 12


def test_queue_endpoints():
    from fastapi.testclient import TestClient
    c = TestClient(app_module.app)
    assert set(c.get("/queue").json()["queues"][0].keys()) == {"counter", "label", "wait_minutes"}
    # conftest zeroes current_queues, so assert override state directly
    r = c.patch("/admin/queue", json={"counter": "main", "minutes": 9}).json()
    assert r["ok"] is True
    import backend.queue as q
    assert q._overrides.get("main") == 9
    assert c.request("DELETE", "/admin/queue").json()["ok"] is True
    assert q._overrides == {}
    bad = c.patch("/admin/queue", json={"counter": "nope", "minutes": 1})
    assert bad.status_code == 404


# ---------- 4. reorder + 3. status ----------
def test_reorder_flow(tmp_path, monkeypatch):
    from backend.memory import MemoryStore
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "memory_store", MemoryStore(path=tmp_path / "m.json"))
    c = TestClient(app_module.app)
    sid = "reorder-s1"
    o = c.post("/order", json={"tray_ids": ["maggi", "masala_chai"], "budget": 100, "session_id": sid}).json()
    assert o["token"].startswith("CB-")
    r = c.post("/chat", json={"message": "repeat last order", "session_id": sid}).json()
    assert r["intent"] == "reorder"
    assert set(r["quick_add"]) == {"maggi", "masala_chai"}
    # cleanup order row
    import json as _json
    op = ROOT / "data" / "order_history.json"
    rows = [x for x in _json.loads(op.read_text()) if x.get("token") != o["token"]]
    op.write_text(_json.dumps(rows, indent=2))


def test_status_flow(tmp_path, monkeypatch):
    from backend.memory import MemoryStore
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app_module, "memory_store", MemoryStore(path=tmp_path / "m.json"))
    c = TestClient(app_module.app)
    sid = "status-s1"
    o = c.post("/order", json={"tray_ids": ["samosa"], "budget": 100, "session_id": sid}).json()
    tok = o["token"]
    st = c.get(f"/order/{tok}").json()
    assert st["state"] == "PREPARING" and "Samosa" in ",".join(st["items"])
    r = c.post("/chat", json={"message": f"where is my order {tok}", "session_id": sid}).json()
    assert r["intent"] == "status" and tok in r["reply"]
    assert c.get("/order/CB-000").status_code == 404
    # backdate the order -> READY
    import json as _json
    op = ROOT / "data" / "order_history.json"
    rows = _json.loads(op.read_text())
    for x in rows:
        if x.get("token") == tok:
            x["at"] = (datetime.now() - timedelta(minutes=60)).isoformat()
    op.write_text(_json.dumps(rows, indent=2))
    assert c.get(f"/order/{tok}").json()["state"] == "READY"
    rows = [x for x in _json.loads(op.read_text()) if x.get("token") != tok]
    op.write_text(_json.dumps(rows, indent=2))


# ---------- 7. complete-my-meal ----------
def test_suggest_math_and_safety():
    from fastapi.testclient import TestClient
    c = TestClient(app_module.app)
    # dosa 60 + budget 100 -> 40 left; must respect peanut allergy
    r = c.post("/tray/suggest", json={
        "tray_ids": ["masala_dosa"], "budget": 100,
        "prefs": {"allergies": ["peanuts"]}}).json()
    assert r["spent"] == 60.0 and r["remaining"] == 40.0
    assert r["suggestions"]
    for s in r["suggestions"]:
        assert s["price"] <= 40.0
        assert "peanuts" not in [a.lower() for a in s["allergens"]]
        assert s["category"] in ("beverage", "snack", "dessert")
    bad = c.post("/tray/suggest", json={"tray_ids": ["maggi"]})
    assert bad.status_code == 400
    full = c.post("/tray/suggest", json={"tray_ids": ["chicken_biryani"], "budget": 100}).json()
    assert full["suggestions"] == []


# ---------- AI-response bugfix regressions ----------
def test_bare_under_budget_recommends():
    from fastapi.testclient import TestClient
    c = TestClient(app_module.app)
    r = c.post("/chat", json={"message": "under 100"}).json()
    assert r["intent"] == "recommend" and r["singles"]
    assert all(s["price"] <= 100 for s in r["singles"])


def test_generic_hunger_recommends():
    from fastapi.testclient import TestClient
    c = TestClient(app_module.app)
    r = c.post("/chat", json={"message": "I want something to eat"}).json()
    assert r["intent"] == "recommend" and (r["singles"] or r["combos"])


def test_gibberish_is_nonsense():
    from backend.nlu import detect_intent
    assert detect_intent("xyz123!!") == "nonsense"
    assert detect_intent("ok") == "nonsense"


def test_thanks_not_exit():
    from fastapi.testclient import TestClient
    c = TestClient(app_module.app)
    assert c.post("/chat", json={"message": "thank you"}).json()["intent"] == "thanks"
    assert c.post("/chat", json={"message": "is my order done?"}).json()["intent"] == "status"


def test_non_veg_only_meat():
    from fastapi.testclient import TestClient
    c = TestClient(app_module.app)
    r = c.post("/chat", json={"message": "non veg under 200"}).json()
    assert r["singles"]
    for s in r["singles"]:
        assert "non_veg" in [d.lower() for d in s["dietary_tags"]]


def test_on_diet_goal_and_headline():
    from fastapi.testclient import TestClient
    c = TestClient(app_module.app)
    r = c.post("/chat", json={"message": "I am on diet, under 150"}).json()
    assert r["prefs"]["goal"] == "low_calorie"
    assert "under Rs 150" in r["reply"] and "picks for" in r["reply"]


def test_combos_only_hides_singles():
    res = recommend(STORE.all(), UserPreferences(budget=200, combos_only=True), meal="lunch")
    assert res["singles"] == [] and len(res["combos"]) > 0


def test_dynamic_combo_cards_complete():
    from fastapi.testclient import TestClient
    c = TestClient(app_module.app)
    r = c.post("/chat", json={"message": "Rs 70, spicy veg, 10 mins"}).json()
    dyn = next(x for x in r["combos"] if x.get("is_dynamic"))
    assert dyn["id"].startswith("dyn_") and dyn["calories"] > 0
    assert dyn["protein_g"] >= 0 and dyn["spice_level"] >= 0
    assert dyn["portion_size"] in ("light", "medium", "heavy", "filling")
    assert dyn["dietary_tags"]  # never empty/mislabeled
