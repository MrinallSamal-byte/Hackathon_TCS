"""Top-20 real-world features: additive endpoints + chat intents (offline-safe)."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.nlu import detect_intent
from backend.store import MenuStore

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
ORDERS = ROOT / "data" / "order_history.json"
FEEDBACK = ROOT / "data" / "feedback_log.json"
MEMORY = ROOT / "data" / "memory.json"


def _rows(path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def _write(path, rows):
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))


def _drop_orders(tokens):
    rows = [r for r in _rows(ORDERS) if r.get("token") not in set(tokens)]
    _write(ORDERS, rows)


def _drop_feedback(item_id, comment=None):
    rows = [r for r in _rows(FEEDBACK)
            if not (r.get("item_id") == item_id and (comment is None or r.get("comment") == comment))]
    _write(FEEDBACK, rows)


def _drop_session(sid):
    # Purge from the live singleton cache AND the JSON mirror (file-only
    # edits get resurrected by the singleton's next save).
    try:
        from backend.app import memory_store
        memory_store._data.pop(sid, None)
        memory_store._save_local()
    except Exception:
        pass


# 1. Order history
def test_orders_history_empty_and_filled():
    r = client.get("/orders", params={"session_id": "t20_nobody"}).json()
    assert r["count"] == 0 and r["orders"] == []
    o = client.post("/order", json={"tray_ids": ["maggi"], "session_id": "t20_hist"}).json()
    try:
        r2 = client.get("/orders", params={"session_id": "t20_hist"}).json()
        assert r2["count"] >= 1 and r2["orders"][0]["token"] == o["token"]
        assert "state" in r2["orders"][0]
    finally:
        _drop_orders([o["token"]])
        _drop_session("t20_hist")


# 2. Cancel order
def test_cancel_order_flow():
    o = client.post("/order", json={"tray_ids": ["maggi"], "session_id": "t20_cancel"}).json()
    try:
        d = client.delete(f"/order/{o['token']}").json()
        assert d["state"] == "CANCELLED"
        st = client.get(f"/order/{o['token']}").json()
        assert st["state"] == "CANCELLED"
    finally:
        _drop_orders([o["token"]])
        _drop_session("t20_cancel")


# 3. Favorites toggle + list
def test_favorites_roundtrip():
    sid = "t20_fav"
    try:
        on = client.post("/favorites", json={"item_id": "maggi", "session_id": sid}).json()
        assert on["favorited"] is True
        lst = client.get("/favorites", params={"session_id": sid}).json()
        assert "maggi" in lst["favorites"] and lst["items"]
        off = client.post("/favorites", json={"item_id": "maggi", "session_id": sid}).json()
        assert off["favorited"] is False
    finally:
        _drop_session(sid)


# 4. Profile save/get
def test_profile_roundtrip():
    sid = "t20_prof"
    try:
        s = client.post("/profile", json={"session_id": sid, "dietary_restrictions": ["veg"],
                                           "goal": "high_protein", "budget": 90}).json()
        assert s["profile"]["goal"] == "high_protein"
        g = client.get("/profile", params={"session_id": sid}).json()
        assert "veg" in g["profile"]["dietary_restrictions"]
    finally:
        _drop_session(sid)


# 5. Coupons in tray + order
def test_coupon_math_additive():
    v = client.post("/tray/validate", json={"tray_ids": ["maggi"], "coupon_code": "STUDENT10"}).json()
    assert v["total"] == 40.0 and v["discount"] == 4.0 and v["payable"] == 36.0
    bad = client.post("/tray/validate", json={"tray_ids": ["maggi"], "coupon_code": "NOPE"}).json()
    assert bad["payable"] == 40.0 and bad["coupon_error"]
    o = client.post("/order", json={"tray_ids": ["maggi"], "coupon_code": "STUDENT10",
                                    "session_id": "t20_coupon"}).json()
    try:
        assert o["total"] == 40.0 and o["payable"] == 36.0 and o["coupon"] == "STUDENT10"
    finally:
        _drop_orders([o["token"]])
        _drop_session("t20_coupon")


# 6. Reviews with comments
def test_reviews_endpoint():
    client.post("/feedback", json={"item_id": "maggi", "rating": 1,
                                   "comment": "t20 tasty", "session_id": "t20_rev"}).json()
    try:
        r = client.get("/feedback/maggi").json()
        assert r["likes"] >= 1 and any(c["comment"] == "t20 tasty" for c in r["comments"])
    finally:
        _drop_feedback("maggi", "t20 tasty")
        _drop_session("t20_rev")


# 7. Pickup counter present
def test_order_counter_assignment():
    o = client.post("/order", json={"tray_ids": ["maggi", "masala_chai"]}).json()
    try:
        assert o["counter"] in ("main", "snacks", "beverages") and o["counter_label"]
        st = client.get(f"/order/{o['token']}").json()
        assert st["counter"] == o["counter"]
    finally:
        _drop_orders([o["token"]])


# 8. Bill split
def test_bill_split():
    r = client.post("/bill/split", json={"tray_ids": ["maggi", "masala_chai"], "people": 2}).json()
    assert r["total"] == 55.0 and r["per_person"] == 27.5 and len(r["breakdown"]) == 2
    r2 = client.post("/bill/split", json={"tray_ids": ["maggi"], "people": 2,
                                          "coupon_code": "STUDENT10"}).json()
    assert r2["payable"] == 36.0 and r2["per_person"] == 18.0


# 9. Trending
def test_trending():
    r = client.get("/trending", params={"limit": 3}).json()
    assert r["count"] == 3 and all("price" in i for i in r["items"])


# 10. Spending tracker
def test_spending_tracker():
    sid = "t20_spend"
    o = client.post("/order", json={"tray_ids": ["maggi"], "session_id": sid}).json()
    try:
        s = client.get("/spending", params={"session_id": sid}).json()
        assert s["order_count"] >= 1 and s["today_total"] >= 40.0
    finally:
        _drop_orders([o["token"]])
        _drop_session(sid)


# 11. Admin orders list
def test_admin_orders_lists_recent():
    o = client.post("/order", json={"tray_ids": ["maggi"], "session_id": "t20_adm"}).json()
    try:
        r = client.get("/admin/orders", params={"q": o["token"]}).json()
        assert r["count"] >= 1 and r["orders"][0]["token"] == o["token"]
    finally:
        _drop_orders([o["token"]])
        _drop_session("t20_adm")


# 12. Admin order status override
def test_admin_order_status_override():
    o = client.post("/order", json={"tray_ids": ["maggi"]}).json()
    try:
        r = client.patch(f"/admin/orders/{o['token']}", json={"status": "READY"}).json()
        assert r["state"] == "READY"
        st = client.get(f"/order/{o['token']}").json()
        assert st["state"] == "READY"
    finally:
        _drop_orders([o["token"]])


# 13. Analytics extended (additive keys)
def test_analytics_extended_keys():
    r = client.get("/admin/analytics").json()
    for k in ("revenue", "avg_order_value", "orders_by_hour", "category_split",
              "sold_out_count", "min_budget", "max_budget", "top_items", "orders"):
        assert k in r, f"missing {k}"


# 14. Feedback inbox
def test_admin_feedback_inbox():
    client.post("/feedback", json={"item_id": "maggi", "rating": -1,
                                   "comment": "t20 salty", "session_id": "t20_inbox"}).json()
    try:
        r = client.get("/admin/feedback", params={"limit": 5}).json()
        assert r["count"] >= 1 and "item_name" in r["feedback"][0]
    finally:
        _drop_feedback("maggi", "t20 salty")
        _drop_session("t20_inbox")


# 15. Bulk availability roundtrip
def test_bulk_availability():
    s = MenuStore(ROOT / "data" / "menu_data.json")
    orig = s.get("maggi").availability
    r = client.post("/admin/items/bulk-availability",
                    json={"ids": ["maggi"], "available": not orig}).json()
    assert r["updated"] == 1
    client.post("/admin/items/bulk-availability", json={"ids": ["maggi"], "available": orig})


# 16. Generic item edit (prep time roundtrip)
def test_generic_item_edit():
    s = MenuStore(ROOT / "data" / "menu_data.json")
    orig = s.get("maggi").prep_time_minutes
    new = orig + 1 if orig < 60 else orig - 1
    r = client.patch("/admin/items/maggi", json={"prep_time_minutes": new}).json()
    assert r["prep_time_minutes"] == new
    client.patch("/admin/items/maggi", json={"prep_time_minutes": orig})
    bad = client.patch("/admin/items/maggi", json={"prep_time_minutes": 999})
    assert bad.status_code == 400


# 17. CSV export
def test_export_csv():
    m = client.get("/admin/export", params={"kind": "menu"})
    assert m.status_code == 200 and m.text.splitlines()[0].startswith("id,name")
    o = client.get("/admin/export", params={"kind": "orders"})
    assert o.status_code == 200 and o.text.splitlines()[0].startswith("token,at")


# 18. Alerts
def test_alerts_shape():
    r = client.get("/admin/alerts").json()
    assert "sold_out" in r and "long_queues" in r and "disliked" in r
    assert r["sold_out_count"] == len(r["sold_out"])


# 19. Mark-all-live restores and preserves seed sold-outs
def test_mark_all_live_restores():
    s = MenuStore(ROOT / "data" / "menu_data.json")
    sold_before = [i.id for i in s.all() if not i.availability]
    r = client.post("/admin/items/mark-all-live").json()
    assert r["restored"] == len(sold_before)
    # restore seed state
    if sold_before:
        client.post("/admin/items/bulk-availability", json={"ids": sold_before, "available": False})
    s2 = MenuStore(ROOT / "data" / "menu_data.json")
    assert {i.id for i in s2.all() if not i.availability} == set(sold_before)


# 20. New chat + NLU intents
def test_new_intents_nlu():
    assert detect_intent("show my orders") == "orders"
    assert detect_intent("my favorite dishes") == "favorites"
    assert detect_intent("how much did I spend today?") == "spending"
    assert detect_intent("what is trending now?") == "trending"
    assert detect_intent("any coupon code?") == "coupon"
    assert detect_intent("save my diet profile") == "profile"
    assert detect_intent("split the bill 3 ways") == "split"
    assert detect_intent("cancel my order CB-123") == "cancel_order"


def test_new_intents_chat():
    sid = "t20_chat"
    try:
        assert client.post("/chat", json={"message": "my orders", "session_id": sid}).json()["intent"] == "orders"
        assert client.post("/chat", json={"message": "what is trending?", "session_id": sid}).json()["intent"] == "trending"
        assert client.post("/chat", json={"message": "any coupons?", "session_id": sid}).json()["intent"] == "coupon"
        assert client.post("/chat", json={"message": "my favorites", "session_id": sid}).json()["intent"] == "favorites"
        assert client.post("/chat", json={"message": "how much did i spend?", "session_id": sid}).json()["intent"] == "spending"
        assert client.post("/chat", json={"message": "my profile", "session_id": sid}).json()["intent"] == "profile"
        # cancel via chat
        o = client.post("/order", json={"tray_ids": ["maggi"], "session_id": sid}).json()
        try:
            r = client.post("/chat", json={"message": f"cancel my order {o['token']}",
                                           "session_id": sid}).json()
            assert r["intent"] == "cancel_order" and "cancelled" in r["reply"].lower()
        finally:
            _drop_orders([o["token"]])
    finally:
        _drop_session(sid)
