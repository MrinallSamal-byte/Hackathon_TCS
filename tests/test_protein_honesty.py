"""High-protein honesty: tiers, ranking, conflict, goal_note (offline-safe)."""
from fastapi.testclient import TestClient

import backend.app as app_module
from backend.models import UserPreferences
from backend.recommender import (detect_conflict, explain_item, protein_tier,
                                 recommend, soft_score)
from backend.store import MenuStore
from pathlib import Path

STORE = MenuStore(Path(__file__).resolve().parents[1] / "data" / "menu_data.json")
client = TestClient(app_module.app)


def test_protein_tiers():
    items = {i.id: i for i in STORE.all()}
    assert protein_tier(items["chicken_biryani"]) == "fit"
    assert protein_tier(items["masala_chai"]) == "low"


def test_spec_weights_untouched_without_goal():
    items = {i.id: i for i in STORE.all()}
    p = UserPreferences(budget=500, cravings=["sweet"])
    _, parts = soft_score(items["masala_chai"], p, "dinner")
    assert parts["taste"] == 25.0  # full taste when no goal competes


def test_low_protein_sweet_loses_top_spot():
    p = UserPreferences(budget=80, goal="high_protein", cravings=["sweet"])
    res = recommend(STORE.all(), p, "dinner")
    top_single = res["singles"][0][0]
    assert protein_tier(top_single) != "low"
    names = [i.name for i, _, _ in res["singles"]]
    assert "Masala Chai" not in names[:1]


def test_explanation_honesty_tiers():
    items = {i.id: i for i in STORE.all()}
    p = UserPreferences(budget=500, goal="high_protein")
    assert "packs" in explain_item(items["chicken_biryani"], p, "lunch")
    mid = explain_item(items["pb_smoothie"], p, "lunch")
    assert "packs" not in mid and "shy of" in mid
    low = explain_item(items["masala_chai"], p, "lunch")
    assert "protein" not in low.lower()


def test_conflict_flags_protein_vs_sweet():
    p = UserPreferences(budget=80, goal="high_protein", cravings=["sweet"])
    assert "rarely high-protein" in (detect_conflict(p) or "")
    p2 = UserPreferences(budget=80, goal="high_protein", cravings=["spicy"])
    assert detect_conflict(p2) is None


def test_goal_note_fires_only_when_nothing_fit():
    tight = UserPreferences(budget=80, goal="high_protein", cravings=["sweet"])
    res = recommend(STORE.all(), tight, "dinner")
    assert res["goal_note"] and "15g" in res["goal_note"]
    wide = UserPreferences(budget=500, goal="high_protein")
    res2 = recommend(STORE.all(), wide, "dinner")
    assert res2["goal_note"] is None


def test_recommend_and_chat_carry_goal_note():
    r = client.post("/recommend", json={
        "preferences": {"budget": 80, "goal": "high_protein",
                        "cravings": ["sweet"]}}).json()
    assert r["goal_note"] and "15g" in r["goal_note"]
    c = client.post("/chat", json={
        "message": "high protein sweet under Rs 80",
        "session_id": "tprot_honesty"}).json()
    try:
        assert "15g" in c["reply"] and "rarely high-protein" in c["reply"]
    finally:
        try:
            app_module.memory_store._data.pop("tprot_honesty", None)
            app_module.memory_store._save_local()
        except Exception:
            pass
