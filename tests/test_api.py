"""API + order/tray/admin/feedback tests (uses TestClient, restores mutated state)."""
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.store import MenuStore

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_health_and_menu():
    assert client.get("/health").json()["ok"] is True
    m = client.get("/menu", params={"max_price": 50}).json()
    assert m["count"] > 0 and all(i["price"] <= 50 for i in m["items"])
    bev = client.get("/menu", params={"category": "beverage"}).json()
    assert bev["count"] > 0 and all(i["category"] == "beverage" for i in bev["items"])
    chi = client.get("/menu", params={"cuisine": "chinese"}).json()
    assert chi["count"] > 0 and all(i["cuisine"] == "chinese" for i in chi["items"])


def test_recommend_endpoint_respects_budget():
    r = client.post("/recommend", json={"preferences": {"budget": 60}, "meal": "lunch"}).json()
    assert r["singles"]
    assert all(s["price"] <= 60 for s in r["singles"])
    assert all(c["total_price"] <= 60 for c in r["combos"])


def test_tray_budget_warning_and_order():
    v = client.post("/tray/validate", json={"tray_ids": ["maggi", "masala_chai"], "budget": 60}).json()
    assert v["total"] == 55.0 and v["over_budget"] is False and v["eta_minutes"] == 8
    v2 = client.post("/tray/validate", json={"tray_ids": ["chicken_biryani"], "budget": 60}).json()
    assert v2["over_budget"] is True
    o = client.post("/order", json={"tray_ids": ["maggi", "masala_chai"], "budget": 60}).json()
    assert o["token"].startswith("CB-") and o["total"] == 55.0
    # cleanup order history written by test
    p = ROOT / "data" / "order_history.json"
    if p.exists():
        import json
        rows = json.loads(p.read_text())
        p.write_text(json.dumps([r for r in rows if r.get("token") != o["token"]], indent=2))


def test_budget_change_mid_order_recomputes():
    v1 = client.post("/tray/validate", json={"tray_ids": ["maggi", "masala_chai"], "budget": 100}).json()
    assert v1["over_budget"] is False
    v2 = client.post("/tray/validate", json={"tray_ids": ["maggi", "masala_chai"], "budget": 40}).json()
    assert v2["over_budget"] is True and "budget" in (v2["warning"] or "").lower()


def test_admin_toggle_roundtrip():
    s = MenuStore(ROOT / "data" / "menu_data.json")
    orig = s.get("samosa").availability
    r = client.patch("/admin/items/samosa/availability", json={"available": not orig}).json()
    assert r["availability"] is (not orig)
    # restore
    client.patch("/admin/items/samosa/availability", json={"available": orig})


def test_feedback_logs_and_restores_popularity():
    s = MenuStore(ROOT / "data" / "menu_data.json")
    before = s.get("samosa").popularity_score
    client.post("/feedback", json={"item_id": "samosa", "rating": 1}).json()
    # remove test feedback row + restore score
    import json
    fp = ROOT / "data" / "feedback_log.json"
    if fp.exists():
        rows = json.loads(fp.read_text())
        rows = [r for r in rows if not (r.get("item_id") == "samosa" and r.get("rating") == 1 and "comment" not in r or r.get("comment") is None and r.get("item_id") == "samosa")]
        fp.write_text(json.dumps(rows, indent=2))
    s2 = MenuStore(ROOT / "data" / "menu_data.json")
    s2.get("samosa").popularity_score = before
    s2.save()
    assert True
