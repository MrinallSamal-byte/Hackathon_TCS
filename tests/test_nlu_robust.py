"""Real-world input robustness: spacing, typos, word-numbers, greetings,
eggetarian, status-vs-time routing, always-on AI gap-fill (offline-safe)."""
from fastapi.testclient import TestClient

import backend.app as app_module
from backend.models import UserPreferences
from backend.nlu import (_words_to_number, detect_intent, normalize_hinglish,
                         parse_budget, parse_dietary_allergy, parse_one_shot,
                         parse_time)
from backend.recommender import passes_dietary
from backend.store import MenuStore
from pathlib import Path

STORE = MenuStore(Path(__file__).resolve().parents[1] / "data" / "menu_data.json")
client = TestClient(app_module.app)


def _prefs(msg):
    return parse_one_shot(msg, UserPreferences())


def test_budget_nospace_below_slash_notation():
    assert parse_budget("under80 spicy") == 80.0
    assert parse_budget("below 80") == 80.0
    assert parse_budget("below80") == 80.0
    assert parse_budget("80/- mein kuch") == 80.0
    assert parse_budget("Rs.80 maggi") == 80.0


def test_budget_word_numbers():
    assert _words_to_number("eighty") == 80.0
    assert _words_to_number("one hundred twenty") == 120.0
    assert _words_to_number("two hundred") == 200.0
    assert _words_to_number("tasty") is None
    assert parse_budget("eighty rupees veg") == 80.0
    assert parse_budget("budget is eighty") == 80.0
    assert parse_budget("one hundred twenty rupees") == 120.0


def test_time_bare_number_with_cue():
    assert parse_time("ready in 10") == 10
    assert parse_time("dinner in 15") == 15
    assert parse_time("in 80") is None  # budget-scale, never a prep time


def test_status_routing_keeps_time_requests():
    assert detect_intent("ready in 10") == "recommend"
    assert detect_intent("is my order ready") == "status"
    assert detect_intent("is my order done?") == "status"
    assert detect_intent("where is my order CB-123") == "status"


def test_greeting_variants():
    for g in ("helo", "hii", "hiiii", "namaste", "namaskar", "hello", "hey"):
        assert detect_intent(g) == "greeting", g


def test_food_typos_resolve():
    assert "paneer" in normalize_hinglish("panner tikka")
    assert "chicken" in normalize_hinglish("chiken rice")
    assert "biryani" in normalize_hinglish("biriyani")
    assert "momos" in normalize_hinglish("1 plate momo")
    assert "chicken" in _prefs("chiken rice").cravings
    assert "momos" in _prefs("1 plate momo").cravings
    assert detect_intent("chiken rice") == "recommend"


def test_eggetarian_end_to_end():
    diet, allergies, _ = parse_dietary_allergy("eggetarian options")
    assert diet == ["eggetarian"] and "egg" not in allergies
    p = UserPreferences(dietary_restrictions=["eggetarian"])
    assert passes_dietary(STORE.get("bread_omelette"), p) is True
    assert passes_dietary(STORE.get("chicken_biryani"), p) is False
    assert "egg" not in _prefs("eggetarian options").cravings
    assert detect_intent("eggetarian options") == "recommend"


def test_gap_fill_runs_even_when_rules_hit(monkeypatch):    # Rules find the budget; the LLM must still fill the mood gap.
    def fake_gap(text):
        assert "birthday" in text
        return ({"mood": "celebrating"}, "test-model")
    monkeypatch.setattr(app_module, "parse_prefs_with_llm", fake_gap)
    r = client.post("/chat", json={
        "message": "Rs 200 birthday dinner", "session_id": "trob_gap"}).json()
    try:
        assert r["prefs"]["budget"] == 200.0
        assert r["prefs"]["mood"] == "celebrating"
    finally:
        try:
            app_module.memory_store._data.pop("trob_gap", None)
            app_module.memory_store._save_local()
        except Exception:
            pass


def test_merge_never_appends_rival_diet_family():
    from backend.llm import merge_llm_patch
    # The live-discovered bug: LLM "corrected" eggetarian to vegetarian and
    # both stuck — veg silently re-blocked egg. Rules win family disputes.
    m = merge_llm_patch(UserPreferences(dietary_restrictions=["eggetarian"]),
                        {"dietary_restrictions": ["vegetarian"]})
    assert m.dietary_restrictions == ["eggetarian"]
    m2 = merge_llm_patch(UserPreferences(dietary_restrictions=["veg"]),
                         {"dietary_restrictions": ["vegan"]})
    assert m2.dietary_restrictions == ["veg"]
    # Non-rival extras still merge.
    m3 = merge_llm_patch(UserPreferences(dietary_restrictions=["eggetarian"]),
                         {"dietary_restrictions": ["eggetarian", "gluten_free"]})
    assert m3.dietary_restrictions == ["eggetarian", "gluten_free"]
