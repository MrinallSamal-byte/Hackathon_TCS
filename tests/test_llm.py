"""LLM layer tests — all offline (network calls monkeypatched)."""
import os

import backend.llm as llm
from backend.llm import merge_llm_patch, validate_patch
from backend.models import UserPreferences


def test_validate_patch_keeps_only_known_values():
    patch = validate_patch({
        "budget": 70, "max_prep_time": 15, "mood": "homesick",
        "dietary_restrictions": ["vegan", "martian"],
        "allergies": ["peanuts", "stardust"],
        "cravings": ["spicy"], "hunger": "very_hungry", "meal": "lunch",
        "cuisine": "north_indian", "max_spice": 2, "combos_only": True,
        "no_onion_garlic": False, "price": 999, "secret": "x",
    })
    assert patch["budget"] == 70 and patch["max_prep_time"] == 15
    assert patch["dietary_restrictions"] == ["vegan"]
    assert patch["allergies"] == ["peanuts"]
    assert "secret" not in patch and "price" not in patch


def test_validate_patch_rejects_garbage():
    assert validate_patch({"budget": -5}) == {}
    assert validate_patch({"max_spice": 9}) == {}
    assert validate_patch({"mood": "sleepy-ish"}) == {}
    assert validate_patch("not a dict") == {}
    assert validate_patch(None) == {}


def test_merge_rule_based_wins_budget_time():
    base = UserPreferences(budget=100, max_prep_time=10)
    merged = merge_llm_patch(base, {"budget": 50, "max_prep_time": 5,
                                    "mood": "homesick", "cravings": ["sweet"]})
    assert merged.budget == 100 and merged.max_prep_time == 10  # base wins
    assert merged.mood == "homesick" and "sweet" in merged.cravings  # gaps filled


def test_merge_appends_lists_without_dupes():
    base = UserPreferences(dietary_restrictions=["veg"], cravings=["spicy"])
    merged = merge_llm_patch(base, {"dietary_restrictions": ["veg", "gluten_free"],
                                    "cravings": ["spicy"]})
    assert merged.dietary_restrictions == ["veg", "gluten_free"]
    assert merged.cravings == ["spicy"]


def test_chain_skips_failing_models(monkeypatch):
    monkeypatch.setenv("CAMPUSBITE_OFFLINE", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODELS", "dead/a:free,live/b:free")
    calls = []

    def fake_post(model, messages, max_tokens, temperature, json_mode):
        calls.append(model)
        return "hello" if model == "live/b:free" else None

    monkeypatch.setattr(llm, "_post_openrouter", fake_post)
    text, used = llm.complete([{"role": "user", "content": "hi"}])
    assert text == "hello" and used == "b:free"
    assert calls == ["dead/a:free", "live/b:free"]


def test_no_key_returns_rule_based(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text, used = llm.complete([{"role": "user", "content": "hi"}])
    assert text is None and used == "rule-based"
    assert llm.phrase_explanation("Plain text.") == "Plain text."
    patch, model = llm.parse_prefs_with_llm("anything")
    assert patch == {} and model == "rule-based"


def test_extract_json_tolerant():
    assert llm._extract_json('Sure! {"budget": 80} done') == {"budget": 80}
    assert llm._extract_json("no json here") is None


def test_batch_phrase_offline_returns_originals():
    texts = ["Dosa (Rs 60, ~10 min) — fits budget.", "Chai (Rs 15) — pairs well."]
    out, model = llm.batch_phrase(texts)
    assert out == texts and model == "rule-based"


def test_batch_phrase_applies_valid_array(monkeypatch):
    monkeypatch.setenv("CAMPUSBITE_OFFLINE", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        llm, "complete",
        lambda *a, **k: ('["Warm Dosa pick.", "Cozy Chai add-on."]', "test-model"))
    out, model = llm.batch_phrase(["a", "b"])
    assert out == ["Warm Dosa pick.", "Cozy Chai add-on."] and model == "test-model"


def test_batch_phrase_rejects_mismatched_array(monkeypatch):
    monkeypatch.setenv("CAMPUSBITE_OFFLINE", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(llm, "complete", lambda *a, **k: ('["only one"]', "x"))
    originals = ["a", "b"]
    out, model = llm.batch_phrase(originals)
    assert out == originals and model == "rule-based"
