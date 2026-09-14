"""Regression tests for bugfix pass: dyn combos, tokens, null-money rows, prep range."""
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.memory import MemoryStore
from backend.models import UserPreferences
from backend.store import MenuStore

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
ORDERS = ROOT / "data" / "order_history.json"


def _rows():
    try:
        return json.loads(ORDERS.read_text())
    except Exception:
        return []


def _drop(tokens):
    toks = set(tokens)
    ORDERS.write_text(json.dumps([r for r in _rows() if r.get("token") not in toks],
                                 indent=2, ensure_ascii=False))


def _drop_session(sid):
    try:
        from backend.app import memory_store
        memory_store._data.pop(sid, None)
        memory_store._save_local()
    except Exception:
        pass


def test_dynamic_combo_validates_and_orders():
    # Dynamic combos previously 404'd (virtual id is not a menu item).
    v = client.post("/tray/validate",
                    json={"tray_ids": ["dyn_maggi__masala_chai"], "budget": 100}).json()
    assert v["total"] == 55.0 and v["count"] == 2
    o = client.post("/order", json={"tray_ids": ["dyn_maggi__masala_chai"],
                                    "budget": 100}).json()
    try:
        assert o["token"].startswith("CB-") and o["total"] == 55.0
    finally:
        _drop([o["token"]])
    bad = client.post("/tray/validate", json={"tray_ids": ["dyn_maggi__nope"]})
    assert bad.status_code == 404
    bad2 = client.post("/tray/validate", json={"tray_ids": ["no_such_item"]})
    assert bad2.status_code == 404


def test_order_tokens_unique():
    toks = []
    try:
        for _ in range(5):
            o = client.post("/order", json={"tray_ids": ["maggi"]}).json()
            toks.append(o["token"])
        assert len(set(toks)) == 5
    finally:
        _drop(toks)


def test_null_money_rows_dont_500():
    rows = _rows()
    rows.append({"token": "CB-NULLFIX", "tray": ["maggi"], "total": None,
                 "payable": None, "eta": 5, "at": "2026-09-14T10:00:00",
                 "session_id": "tfix_null"})
    ORDERS.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    try:
        assert client.get("/admin/analytics").status_code == 200
        s = client.get("/spending", params={"session_id": "tfix_null"}).json()
        assert s["order_count"] == 1 and s["today_total"] == 0.0
        r = client.post("/chat", json={"message": "my orders",
                                       "session_id": "tfix_null"}).json()
        assert r["intent"] == "orders"
    finally:
        _drop(["CB-NULLFIX"])
        _drop_session("tfix_null")


def test_prep_edit_range_matches_menu_contract():
    s = MenuStore(ROOT / "data" / "menu_data.json")
    orig = s.get("maggi").prep_time_minutes
    try:
        assert client.patch("/admin/items/maggi",
                            json={"prep_time_minutes": 1}).status_code == 400
        assert client.patch("/admin/items/maggi",
                            json={"prep_time_minutes": 30}).status_code == 400
        ok = client.patch("/admin/items/maggi",
                          json={"prep_time_minutes": 9}).json()
        assert ok["prep_time_minutes"] == 9
    finally:
        client.patch("/admin/items/maggi", json={"prep_time_minutes": orig})


def test_profile_max_spice_zero_preserved():
    ms = MemoryStore()
    mem = {"profile": {"max_spice": 0, "goal": "high_protein"}, "budgets": [],
           "moods": [], "orders": {}, "likes": {}, "chats": 0, "favorites": {}}
    mem["favorites"] = []
    out = ms.apply_profile_defaults(mem, UserPreferences())
    assert out.max_spice == 0 and out.goal == "high_protein"


def test_favorites_and_profile_echo_session():
    sid = "tfix_sid"
    try:
        f = client.get("/favorites", params={"session_id": sid}).json()
        assert f["session_id"] == sid
        p = client.get("/profile", params={"session_id": sid}).json()
        assert p["session_id"] == sid and p["profile"] == {}
    finally:
        _drop_session(sid)


def test_add_item_rejects_bad_taste_profile():
    r = client.post("/admin/items", json={
        "id": "tfix_tmp_dish", "name": "TFix Tmp Dish", "price": 10,
        "category": "snack", "cuisine": "north_indian",
        "prep_time_minutes": 5, "calories": 100, "portion_size": "medium",
        "spice_level": 1, "popularity_score": 50,
        "taste_profile": ["savory", "fresh"], "mood_tags": ["comfort"],
        "serving_times": ["all_day"], "dietary_tags": ["veg"]})
    assert r.status_code == 400


def test_specials_deterministic_and_live():
    from backend.store import MenuStore as _MS
    live_ids = {i.id for i in _MS(ROOT / "data" / "menu_data.json").live()}
    a = client.get("/specials").json()
    b = client.get("/specials").json()
    assert a["count"] == 3 and a["date"] == b["date"]
    assert [i["id"] for i in a["items"]] == [i["id"] for i in b["items"]]
    assert all(i["id"] in live_ids for i in a["items"])


def test_menu_exclude_allergen():
    from backend.nlu import detect_intent as _di
    assert _di("surprise me") == "surprise"
    assert _di("today's special") == "special"
    all_n = client.get("/menu").json()["count"]
    ex = client.get("/menu", params={"exclude": "peanuts,dairy"}).json()
    assert ex["count"] < all_n
    for it in ex["items"]:
        tags = {str(x).lower() for x in it["allergens"]}
        assert not (tags & {"peanuts", "dairy"})
    # unknown allergens are ignored, not errors
    ok = client.get("/menu", params={"exclude": "vibranium"}).json()
    assert ok["count"] == all_n


def test_weekly_budget_profile_roundtrip_and_intents():
    sid = "tfix_weekly"
    try:
        s = client.post("/profile", json={"session_id": sid, "weekly_budget": 400}).json()
        assert s["profile"]["weekly_budget"] == 400.0
        r = client.post("/chat", json={"message": "surprise me", "session_id": sid}).json()
        assert r["intent"] == "surprise" and len(r["singles"]) == 1
        r2 = client.post("/chat", json={"message": "show today's specials",
                                        "session_id": sid}).json()
        assert r2["intent"] == "special" and len(r2["singles"]) == 3
    finally:
        _drop_session(sid)


# ---------- diabetic answer-quality regressions (reported failure) ----------

def test_diabetic_typo_detected():
    from backend.nlu import parse_goal
    assert parse_goal("i have diabetise") == "diabetic"
    assert parse_goal("diabities problem") == "diabetic"
    assert parse_goal("sugar patient") == "diabetic"
    assert parse_goal("need protien rich food") == "high_protein"


def test_diabetic_picks_are_honest():
    from backend.recommender import diabetic_fit, diabetic_score
    from backend.store import MenuStore as _MS
    s = _MS(ROOT / "data" / "menu_data.json")
    samosa = s.get("samosa")
    assert not diabetic_fit(samosa)  # fried — must never qualify
    assert diabetic_score(samosa)[1] in ("watch", "avoid")
    assert diabetic_fit(s.get("peanut_masala"))
    assert diabetic_fit(s.get("green_tea"))
    assert not diabetic_fit(s.get("gulab_jamun"))
    assert diabetic_score(s.get("gulab_jamun"))[0] < 0


def test_diabetic_chat_never_overclaims():
    sid = "tfix_diab"
    try:
        r = client.post("/chat", json={"message": "i have diabetise",
                                       "session_id": sid}).json()
        assert r["intent"] == "recommend"
        assert "not a doctor" in r["reply"]  # medical disclaimer present
        assert r["prefs"]["goal"] == "diabetic"
        for card in r["singles"] + r["combos"]:
            expl = (card.get("explanation") or "").lower()
            if "diabetic-friendly" in expl:
                assert card.get("sugar_g", 99) <= 10, card["name"]
        # top singles must all be low-sugar (no dessert/syrup lead)
        sugars = [c.get("sugar_g", 0) for c in r["singles"]]
        assert sugars and max(sugars) <= 10, sugars
        assert r["chips"] != ["Something cheaper", "Less spicy", "More filling",
                              "Quicker", "Show combos", "No onion/garlic"]
    finally:
        _drop_session(sid)


def test_diabetic_refine_and_recommend_carry_note():
    r = client.post("/recommend", json={"preferences": {"goal": "diabetic", "budget": 100},
                                        "meal": "dinner"}).json()
    assert "health_note" in r and "not a doctor" in r["health_note"]
    c = client.post("/chat", json={"message": "less spicy",
                                   "prefs": {"goal": "diabetic", "budget": 100},
                                   "session_id": "tfix_d2"}).json()
    try:
        assert "not a doctor" in c["reply"]
    finally:
        _drop_session("tfix_d2")


def test_menu_nutrition_filters_and_cards():
    m = client.get("/menu", params={"max_sugar": 5}).json()
    assert m["count"] > 0 and all(i["sugar_g"] <= 5 for i in m["items"])
    m2 = client.get("/menu", params={"min_protein": 15}).json()
    assert m2["count"] > 0 and all(i["protein_g"] >= 15 for i in m2["items"])
    m3 = client.get("/menu", params={"max_carbs": 10}).json()
    assert m3["count"] > 0 and all(i["carbs_g"] <= 10 for i in m3["items"])
    m4 = client.get("/menu", params={"max_calories": 100}).json()
    assert m4["count"] > 0 and all(i["calories"] <= 100 for i in m4["items"])
    assert "carbs_g" in m["items"][0] and "fiber_g" in m["items"][0]
    # ingredient search now matches
    q = client.get("/menu", params={"q": "khoya"}).json()
    assert any("khoya" in " ".join(i["ingredients"]) for i in q["items"])


def test_admin_nutrition_edit_and_export():
    s = MenuStore(ROOT / "data" / "menu_data.json")
    sug = s.get("green_tea").sugar_g
    r = client.patch("/admin/items/green_tea", json={"sugar_g": 1}).json()
    assert r["sugar_g"] == 1
    client.patch("/admin/items/green_tea", json={"sugar_g": sug})
    bad = client.patch("/admin/items/green_tea", json={"sugar_g": -2})
    assert bad.status_code == 400
    csv_text = client.get("/admin/export", params={"kind": "menu"}).text
    assert "sugar_g" in csv_text.splitlines()[0]


# ---------- health memory + counter-to-self redirects ----------

def test_health_condition_persisted_to_profile():
    from backend.nlu import parse_health_conditions
    assert parse_health_conditions("i have diabetise") == ["diabetes"]
    assert parse_health_conditions("i am diabetic") == ["diabetes"]
    assert parse_health_conditions("i want something sweet") == []
    sid = "tfix_health"
    try:
        r = client.post("/chat", json={"message": "i have diabetise",
                                       "session_id": sid}).json()
        assert "diabetes" in r["reply"].lower()  # acknowledgement note
        prof = client.get("/profile", params={"session_id": sid}).json()["profile"]
        assert prof["goal"] == "diabetic"
        assert "diabetes" in prof.get("health_conditions", [])
        # next visit, no goal stated: profile applies silently with a note
        r2 = client.post("/chat", json={"message": "something under Rs 60",
                                        "session_id": sid}).json()
        assert r2["prefs"]["goal"] == "diabetic"
        assert "keeping your diabetes in mind" in r2["reply"].lower()
    finally:
        _drop_session(sid)


def test_diabetic_named_dish_redirect_then_autonomy():
    sid = "tfix_redir"
    try:
        client.post("/chat", json={"message": "i am diabetic", "session_id": sid})
        r = client.post("/chat", json={"message": "i want gulab jamun",
                                       "session_id": sid}).json()
        assert r["intent"] == "health_redirect"
        assert "gulab jamun" in r["reply"].lower()
        assert "32g sugar" in r["reply"]
        assert all(s.get("sugar_g", 99) <= 10 for s in r["singles"]), \
            [s["name"] for s in r["singles"]]
        # insisting a second time respects autonomy: normal recommend path
        r2 = client.post("/chat", json={"message": "no, get me gulab jamun",
                                        "session_id": sid}).json()
        assert r2["intent"] == "recommend"
    finally:
        _drop_session(sid)


def test_diabetic_sweet_craving_conflict_flag():
    from backend.recommender import detect_conflict
    from backend.models import UserPreferences
    c = detect_conflict(UserPreferences(goal="diabetic", cravings=["chocolate"]))
    assert c and "spike" in c.lower()
    assert detect_conflict(UserPreferences(cravings=["chocolate"])) is None


def test_supabase_payloads_carry_new_fields():
    from backend import db_supabase as db
    import backend.db_supabase as _m
    seen = {}

    class _R:
        status_code = 200

    def fake_post(url, timeout=None, headers=None, json=None):
        seen.update(json)
        return _R()

    import httpx
    real_post, real_url = httpx.post, os.environ.get("SUPABASE_URL")
    httpx.post = fake_post
    os.environ["SUPABASE_URL"] = "https://x.supabase.co"
    os.environ["SUPABASE_SERVICE_KEY"] = "k"
    try:
        assert db.log_order({"token": "CB-1", "tray": ["maggi"], "total": 40,
                             "payable": 36, "coupon": "STUDENT10", "discount": 4,
                             "counter": "snacks", "counter_label": "Snacks Counter",
                             "eta": 5, "session_id": "s"}) is True
        for k in ("payable", "coupon", "discount", "counter", "counter_label", "session_id"):
            assert k in seen, k
        assert db.log_feedback({"item_id": "maggi", "rating": 1,
                                "session_id": "s"}) is True
        assert seen.get("session_id") == "s"
    finally:
        httpx.post = real_post
        if real_url is None:
            os.environ.pop("SUPABASE_URL", None)
        else:
            os.environ["SUPABASE_URL"] = real_url
        os.environ.pop("SUPABASE_SERVICE_KEY", None)
