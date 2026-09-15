"""Hard-filter, scoring, combo-math, and guardrail tests."""
import json
from pathlib import Path

import pytest

from backend.models import MenuItem, UserPreferences
from backend.recommender import (
    passes_dietary, passes_hard_filters, recommend, soft_score, substitutes_for,
)
from backend.store import MenuStore

ROOT = Path(__file__).resolve().parents[1]
STORE = MenuStore(ROOT / "data" / "menu_data.json")
ITEMS = STORE.all()


def test_menu_schema_and_counts():
    assert 40 <= len(ITEMS) <= 100
    assert sum(1 for i in ITEMS if i.is_combo) >= 5
    assert sum(1 for i in ITEMS if not i.availability) >= 5
    for i in ITEMS:
        assert 10 <= i.price <= 250
        assert 2 <= i.prep_time_minutes <= 25


def test_hard_filters_budget_time_availability_meal():
    prefs = UserPreferences(budget=50, max_prep_time=8)
    for i in ITEMS:
        if passes_hard_filters(i, prefs, "lunch"):
            assert i.availability and i.price <= 50 and i.prep_time_minutes <= 8
            st = {s.value for s in i.serving_times}
            assert "lunch" in st or "all_day" in st


def test_allergen_exclusion_never_relaxed():
    prefs = UserPreferences(allergies=["peanuts"], budget=500)
    res = recommend(ITEMS, prefs, meal=None)
    for it, _, _ in res["singles"]:
        assert "peanuts" not in {str(a).split(".")[-1] for a in it.allergens}
    # even with zero-match relaxation, allergens stay excluded
    strict = UserPreferences(allergies=["peanuts", "dairy", "gluten"], budget=20)
    res2 = recommend(ITEMS, strict, meal="dinner")
    for it, _, _ in res2["singles"]:
        alls = {str(a).split(".")[-1] for a in it.allergens}
        assert not (alls & {"peanuts", "dairy", "gluten"})


def test_jain_filter_no_onion_garlic():
    prefs = UserPreferences(dietary_restrictions=["jain"], budget=500)
    for i in ITEMS:
        if passes_hard_filters(i, prefs, None):
            assert "jain" in {str(d).split(".")[-1] for d in i.dietary_tags}
            assert not any("onion" in x.lower() or "garlic" in x.lower() for x in i.ingredients)


def test_vegan_filter():
    prefs = UserPreferences(dietary_restrictions=["vegan"], budget=500)
    for i in ITEMS:
        if passes_hard_filters(i, prefs, None):
            assert "vegan" in {str(d).split(".")[-1] for d in i.dietary_tags}


def test_soft_scoring_weights():
    prefs = UserPreferences(budget=100, mood="celebratory", cravings=["sweet"], hunger="light_bite")
    choc = next(i for i in ITEMS if i.id == "choco_mousse")  # sweet, celebratory
    soup = next(i for i in ITEMS if i.id == "tomato_soup")
    s_choc, parts = soft_score(choc, prefs, "lunch")
    assert parts["mood"] == 30.0 and parts["taste"] == 25.0
    assert 0 <= parts["popularity"] <= 15.0
    s_soup, _ = soft_score(soup, prefs, "lunch")
    assert s_choc > s_soup


def test_combo_math_within_budget():
    prefs = UserPreferences(budget=100)
    res = recommend(ITEMS, prefs, meal="lunch")
    assert len(res["combos"]) <= 2
    for c in res["combos"]:
        assert c["total_price"] <= 100 + 1e-9
        if c.get("is_dynamic"):
            parts = c["items"]
            assert abs(sum(p.price for p in parts) - c["total_price"]) < 0.01
            assert c["eta"] == max(p.prep_time_minutes for p in parts)


def test_availability_toggle():
    s = MenuStore(ROOT / "data" / "menu_data.json")
    target = "maggi"
    before = s.get(target).availability
    s.toggle_availability(target, persist=False)
    assert s.get(target).availability is (not before)
    prefs = UserPreferences(budget=500)
    res = recommend(s.all(), prefs, meal=None)
    ids = [it.id for it, _, _ in res["singles"]]
    if before:  # was live, now off -> must disappear
        assert target not in ids


def test_low_budget_path():
    prefs = UserPreferences(budget=5)
    res = recommend(ITEMS, prefs, meal="lunch")
    assert res["cheapest_note"] is not None
    assert len(res["cheapest"]) >= 2
    prices = [i.price for i in res["cheapest"]]
    assert prices == sorted(prices)


def test_conflict_vegan_chicken():
    prefs = UserPreferences(dietary_restrictions=["vegan"], cravings=["chicken"], budget=500)
    res = recommend(ITEMS, prefs, meal=None)
    assert res["conflict"] is not None and "vegan" in res["conflict"].lower()
    for it, _, _ in res["singles"]:
        assert "non_veg" not in {str(d).split(".")[-1] for d in it.dietary_tags}


def test_substitutes_available_and_close():
    target = next(i for i in ITEMS if not i.availability)
    subs = substitutes_for(target, ITEMS, UserPreferences(budget=500), None, n=3)
    assert 1 <= len(subs) <= 3
    assert all(s.availability and s.id != target.id for s in subs)
