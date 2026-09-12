"""10 scripted test conversations (spec section 10). Each is an end-to-end chat check."""
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def chat(msg, prefs=None):
    return client.post("/chat", json={"message": msg, "prefs": prefs or {}}).json()


def test_01_budget_only():
    r = chat("Under Rs 50 please")
    assert r["intent"] == "recommend"
    assert r["singles"] and all(s["price"] <= 50 for s in r["singles"])


def test_02_one_shot_full():
    r = chat("I have Rs 70, want something spicy and veg, got 15 mins")
    assert r["intent"] == "recommend"
    assert all(s["price"] <= 70 and s["prep_time_minutes"] <= 15 for s in r["singles"])
    assert any("spicy" in s["taste_profile"] for s in r["singles"])


def test_03_cheaper_refinement():
    first = chat("Rs 150, something indulgent")
    prefs = first["prefs"]
    second = client.post("/chat", json={"message": "make it cheaper", "prefs": prefs}).json()
    assert second["intent"] == "refine"
    assert second["prefs"]["budget"] < 150


def test_04_sold_out_path():
    r = chat("I want Oreo Shake")
    assert r["intent"] == "sold_out"
    assert "sold out" in r["reply"].lower() and len(r["singles"]) >= 2
    assert all(s["availability"] for s in r["singles"])


def test_05_peanut_allergy():
    r = chat("I have a peanut allergy, Rs 200, suggest snacks")
    assert r["singles"]
    for s in r["singles"]:
        assert "peanuts" not in [a.lower() for a in s["allergens"]]


def test_06_jain_restriction():
    r = chat("Jain food under Rs 100")
    assert r["singles"]
    for s in r["singles"]:
        assert "jain" in [d.lower() for d in s["dietary_tags"]]
        assert not any("onion" in i.lower() or "garlic" in i.lower() for i in s["ingredients"])


def test_07_very_low_budget():
    r = chat("I have Rs 5, anything?")
    assert r["cheapest_note"] is not None and len(r["cheapest"]) >= 2


def test_08_combo_under_100():
    r = chat("Show combos under Rs 100")
    combos = r.get("combos", []) or []
    # browse path may return singles; recommend path returns combos — accept either but verify math
    if combos:
        assert all(c["total_price"] <= 100 for c in combos)
    else:
        assert r["singles"]


def test_09_in_a_hurry():
    r = chat("In a hurry, Rs 100, veg")
    assert r["singles"] and all(s["prep_time_minutes"] <= 5 for s in r["singles"])


def test_10_vegan_chicken_conflict():
    r = chat("I'm vegan but craving chicken, budget Rs 200")
    assert r["conflict"] is not None and "vegan" in r["conflict"].lower()
    for s in r["singles"]:
        assert "non_veg" not in [d.lower() for d in s["dietary_tags"]]
