"""Period & menstrual cramp nutritional intelligence tests."""
from pathlib import Path
from fastapi.testclient import TestClient

import backend.app as app_module
from backend.models import UserPreferences
from backend.nlu import parse_goal, parse_health_conditions, parse_one_shot
from backend.recommender import (
    detect_conflict,
    explain_item,
    period_comfort_score,
    recommend,
    soft_score,
)
from backend.store import MenuStore

STORE = MenuStore(Path(__file__).resolve().parents[1] / "data" / "menu_data.json")
client = TestClient(app_module.app)


def test_nlu_period_typos_and_goal():
    queries = [
        "i have periads so whats best for me",
        "i have periad cramps",
        "priods pain whats good to eat",
        "suffering from menstrual cramps",
        "food for pms mood swings",
    ]
    for q in queries:
        assert parse_goal(q) == "period_friendly", f"Failed to parse goal for: {q}"

    # Check health condition extraction
    conds = parse_health_conditions("i have periads and cramps")
    assert "periods" in conds

    # Check parse_one_shot sets comfort mood
    p = parse_one_shot("i have periads so whats best for me")
    assert p.goal == "period_friendly"
    assert p.mood == "comfort"


def test_period_comfort_tiers():
    items = {i.id: i for i in STORE.all()}
    # Boosted: Iron, magnesium, pelvic warmth, anti-bloating
    for boost_id in ["palak_roti", "jain_khichdi", "tomato_soup", "choco_mousse", "chaas"]:
        pts, tier, reason = period_comfort_score(items[boost_id])
        assert tier == "boost", f"{boost_id} should be boost tier"
        assert pts >= 16.0

    # Avoid: deep-fried prostaglandins or high refined sugar spikes
    for avoid_id in ["chole_bhature", "samosa", "gulab_jamun", "fries", "combo_biryani_jamun"]:
        pts, tier, reason = period_comfort_score(items[avoid_id])
        assert tier == "avoid", f"{avoid_id} should be avoid tier"
        assert pts <= -20.0


def test_chat_exact_user_query():
    resp = client.post("/chat", json={"message": "i have periads so whats best for me", "meal_override": "dinner"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("intent") == "recommend"
    reply = data.get("reply", "")
    assert "period-comfort & cramp-relief" in reply
    assert "Comfort Note:" in reply

    chips = data.get("chips", [])
    assert "Warm & comforting" in chips
    assert "Iron-rich meals" in chips

    singles = data.get("singles", [])
    assert len(singles) > 0
    top_ids = [s["id"] for s in singles]
    # Palak Paneer + Roti, Jain Dal Khichdi, or Dal Tadka should be top picks
    assert any(bid in top_ids for bid in ["palak_roti", "jain_khichdi", "dal_rice", "tomato_soup"])

    # Harmful items must NOT appear in top singles
    assert "chole_bhature" not in top_ids
    assert "chicken_biryani" not in top_ids
    assert "gulab_jamun" not in top_ids


def test_conflict_on_craving_fried_during_periods():
    p = UserPreferences(goal="period_friendly", cravings=["chole bhature"])
    conflict = detect_conflict(p)
    assert conflict is not None
    assert "prostaglandins" in conflict or "cramps" in conflict

    p_clean = UserPreferences(goal="period_friendly", cravings=["soup"])
    assert detect_conflict(p_clean) is None


def test_counter_to_self_period_redirect():
    import uuid
    # Unique sid per run: the warn-once flag lives in the persistent memory
    # mirror, so a fixed sid would see "already warned" on re-runs and flake
    # from recommend-vs-redirect. Fresh sid => deterministic first-turn redirect.
    sid = f"test_period_redirect_{uuid.uuid4().hex[:8]}"
    # Turn 1: user asks for Chole Bhature with period cramps -> caring redirect
    r1 = client.post("/chat", json={"message": "i have cramps but i crave chole bhature", "session_id": sid})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1.get("intent") == "health_redirect"
    assert "Chole Bhature" in d1.get("reply", "")
    assert "prostaglandins" in d1.get("reply", "") or "bloating" in d1.get("reply", "")

    # Turn 2: user insists -> autonomy respected, recommend normally
    r2 = client.post("/chat", json={"message": "i still want chole bhature", "session_id": sid})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("intent") == "recommend"


def test_menu_goal_sorting():
    resp = client.get("/menu?goal=period_friendly")
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("items", [])
    assert len(items) > 0
    top_id = items[0]["id"]
    pts, tier, _ = period_comfort_score(STORE.get(top_id))
    assert tier == "boost"
