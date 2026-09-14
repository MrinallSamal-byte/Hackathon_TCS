"""AI robustness batch: phrase cache, fact-check, chain budget, query matching.

All offline-safe (conftest forces CAMPUSBITE_OFFLINE=1; network faked via
monkeypatch where the test needs the "key present" path).
"""
from fastapi.testclient import TestClient

import backend.app as app_module
import backend.llm as llm
from backend.app import find_named_item
from backend.nlu import (normalize_hinglish, parse_goal,
                         parse_health_conditions)

client = TestClient(app_module.app)


def _drop_session(sid):
    # Mirror test_top20: purge singleton cache AND the JSON mirror.
    try:
        app_module.memory_store._data.pop(sid, None)
        app_module.memory_store._save_local()
    except Exception:
        pass


def _online(monkeypatch):
    monkeypatch.setenv("CAMPUSBITE_OFFLINE", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


# 1. Phrase cache: identical batch costs one model call, repeats are free.
def test_phrase_cache_serves_repeats_without_second_call(monkeypatch):
    _online(monkeypatch)
    calls = []

    def fake_complete(*a, **k):
        calls.append(1)
        return ('["Warm Dosa pick.", "Cozy Chai add-on."]', "test-model")

    monkeypatch.setattr(llm, "complete", fake_complete)
    texts = ["Dosa (Rs 60, ~10 min) — fits budget.",
             "Chai (Rs 15, ~3 min) — pairs well."]
    out1, m1 = llm.batch_phrase(texts)
    out2, m2 = llm.batch_phrase(texts)
    assert out1 == out2 == ["Warm Dosa pick.", "Cozy Chai add-on."]
    assert (m1, m2) == ("test-model", "test-model")
    assert len(calls) == 1


# 2. Fact-check: a paraphrase that drops price/prep digits falls back per-item.
def test_phrase_fact_check_rejects_altered_price_and_prep(monkeypatch):
    _online(monkeypatch)
    monkeypatch.setattr(
        llm, "complete",
        lambda *a, **k: ('["Samosa (2 pc) (Rs 25, ~5 min) lovely.", "Chai treat, on the house!"]',
                         "test-model"))
    texts = ["Samosa (Rs 25, ~5 min) — fits budget.",
             "Filter Coffee (Rs 15, ~3 min) — pairs well."]
    facts = [{"name": "Samosa (2 pc)", "price": 25, "prep": 5},
             {"name": "Filter Coffee", "price": 15, "prep": 3}]
    out, model = llm.batch_phrase(texts, facts)
    assert out[0] == "Samosa (2 pc) (Rs 25, ~5 min) lovely."  # kept: facts intact
    assert out[1] == texts[1]  # dropped: price+prep digits missing
    assert model == "test-model"


def test_phrase_fact_check_all_bad_returns_rule_based(monkeypatch):
    _online(monkeypatch)
    monkeypatch.setattr(llm, "complete",
                        lambda *a, **k: ('["Free food for all!", "Yummy stuff!"]',
                                         "test-model"))
    texts = ["Samosa (Rs 25, ~5 min) — fits budget."]
    out, model = llm.batch_phrase(
        texts, [{"name": "Samosa (2 pc)", "price": 25, "prep": 5}])
    assert out == texts and model == "rule-based"


# 3. Chain budget: an exhausted budget attempts no models (no long hang),
# and a mid-chain stall stops early instead of trying all 9 models.
def test_chain_budget_stops_runaway(monkeypatch):
    _online(monkeypatch)
    monkeypatch.setattr(llm, "_CHAIN_BUDGET", 0)
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return None

    monkeypatch.setattr(llm, "_post_openrouter", fake_post)
    out, model = llm.complete([{"role": "user", "content": "hi"}])
    assert out is None and model == "rule-based" and calls == []


def test_chain_stops_early_on_slow_models(monkeypatch):
    _online(monkeypatch)
    monkeypatch.setattr(llm, "_CHAIN_BUDGET", 0.35)
    import time as _t
    calls = []

    def slow_post(*a, **k):
        calls.append(1)
        _t.sleep(0.2)
        return None

    monkeypatch.setattr(llm, "_post_openrouter", slow_post)
    out, model = llm.complete([{"role": "user", "content": "hi"}])
    assert out is None and model == "rule-based"
    assert 1 <= len(calls) < len(llm.get_model_chain())


def test_chain_uses_first_success(monkeypatch):
    _online(monkeypatch)
    monkeypatch.setattr(llm, "_CHAIN_BUDGET", 25.0)
    seen = []

    def fake_post(model, *a, **k):
        seen.append(model)
        return "hello" if len(seen) == 2 else None

    monkeypatch.setattr(llm, "_post_openrouter", fake_post)
    out, model = llm.complete([{"role": "user", "content": "hi"}])
    assert out == "hello" and len(seen) == 2


# 4. Spaceless dish matching ("gulabjamun" == "Gulab Jamun (2 pc)").
def test_spaceless_dish_match():
    client.get("/health")  # ensure menu loaded
    assert find_named_item("is gulabjamun good?").id == "gulab_jamun"
    assert find_named_item("want gulab jamun please").id == "gulab_jamun"
    assert find_named_item("craving samosa").id == "samosa"
    # Generic queries must NOT match a dish (no hijacking recommend flow).
    assert find_named_item("something masala under 80") is None
    assert find_named_item("what is trending now?") is None


# 5. User's literal misspelling "diabatise" resolves end to end.
def test_diabatise_alias_resolves():
    assert "diabetes" in normalize_hinglish("i have diabatise")
    assert parse_goal("i have diabatise") == "diabetic"
    assert parse_health_conditions("i have diabatise") == ["diabetes"]


def test_health_redirect_fires_on_spaceless_query():
    sid = "trob_health"
    try:
        r = client.post(
            "/chat", json={"message": "i have diabatise",
                           "session_id": sid}).json()
        assert r["prefs"]["goal"] == "diabetic"
        r2 = client.post(
            "/chat", json={"message": "is gulabjamun good?",
                           "session_id": sid}).json()
        assert r2["intent"] == "health_redirect"
        assert "isn't a great pick" in r2["reply"]
        assert "32g sugar" in r2["reply"] and "Note:" in r2["reply"]
    finally:
        _drop_session(sid)
