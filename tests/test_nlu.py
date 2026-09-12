"""NLU one-shot parsing + refinement tests."""
from backend.nlu import (apply_refinement, detect_intent, parse_budget, parse_one_shot,
                         parse_time, clarifying_questions)
from backend.models import UserPreferences


def test_budget_formats():
    assert parse_budget("under 80") == 80
    assert parse_budget("₹100 max") == 100
    assert parse_budget("between 50 and 150") == 150
    assert parse_budget("I have Rs 70") == 70


def test_time_parsing():
    assert parse_time("in a hurry") == 5
    assert parse_time("got 20 mins") == 20
    assert parse_time("I have 15 mins") == 15


def test_one_shot_full():
    p = parse_one_shot("I have ₹70, want something spicy and veg, got 15 mins")
    assert p.budget == 70
    assert p.max_prep_time == 15
    assert "veg" in p.dietary_restrictions
    assert "spicy" in p.cravings


def test_refinement_cheaper_less_spicy():
    base = UserPreferences(budget=100, max_spice=3)
    p, note = apply_refinement("make it cheaper, less spicy", base)
    assert p.budget < 100 and p.max_spice == 1


def test_refinement_quicker_no_onion_combos():
    base = UserPreferences()
    p, _ = apply_refinement("quicker, no onions, combos only", base)
    assert p.max_prep_time == 5 and p.no_onion_garlic and p.combos_only


def test_intents():
    assert detect_intent("hello") == "greeting"
    assert detect_intent("What do you have under Rs 50?") == "browse"
    assert detect_intent("make it cheaper") == "refine"
    assert detect_intent("tell me a joke about cricket") == "smalltalk"


def test_clarifying_max_two():
    qs = clarifying_questions(UserPreferences())
    assert 1 <= len(qs) <= 2
    assert clarifying_questions(UserPreferences(budget=80, max_prep_time=10)) == []
