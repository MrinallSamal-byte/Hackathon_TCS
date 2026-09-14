"""Abuse guards + conversational-gap verification (offline-safe).

Guards: vote dedupe, chat/comment length caps, session-id cap, memory caps.
Gaps (behavior must already work — these pin it): past-order reorder,
avoid/exclusions, diabetic greeting.
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient

import backend.app as app_module
from backend.memory import blank, MemoryStore
from backend.recommender import diabetic_fit
from backend.store import MenuStore

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app_module.app)
FEEDBACK = ROOT / "data" / "feedback_log.json"
ORDERS = ROOT / "data" / "order_history.json"
MENU = ROOT / "data" / "menu_data.json"


def _rows(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def _write(p, rows):
    p.write_text(json.dumps(rows, indent=2))


def _drop_session(sid):
    try:
        app_module.memory_store._data.pop(sid, None)
        app_module.memory_store._save_local()
    except Exception:
        pass


# ---------- 1. vote dedupe ----------

def test_vote_dedupe_same_direction_counts_once():
    item = "samosa"
    s = MenuStore(MENU)
    before = s.get(item).popularity_score
    sid = "tg_vote"
    try:
        r1 = client.post("/feedback", json={"item_id": item, "rating": 1,
                                            "session_id": sid}).json()
        assert r1["deduped"] is False
        mid = MenuStore(MENU).get(item).popularity_score
        assert mid == min(100, before + 1)
        r2 = client.post("/feedback", json={"item_id": item, "rating": 1,
                                            "session_id": sid}).json()
        assert r2["deduped"] is True
        assert MenuStore(MENU).get(item).popularity_score == mid
        # Changing your mind still counts.
        r3 = client.post("/feedback", json={"item_id": item, "rating": -1,
                                            "session_id": sid}).json()
        assert r3["deduped"] is False
        assert MenuStore(MENU).get(item).popularity_score == max(0, mid - 1)
    finally:
        rows = [r for r in _rows(FEEDBACK)
                if not (r.get("item_id") == item and r.get("session_id") == sid)]
        _write(FEEDBACK, rows)
        s2 = MenuStore(MENU)
        s2.get(item).popularity_score = before
        s2.save()
        _drop_session(sid)


# ---------- 2. length caps ----------

def test_chat_message_cap():
    r = client.post("/chat", json={"message": "a " * 1001})  # 2002 chars
    assert r.status_code == 422
    r = client.post("/chat", json={"message": "a " * 1000})  # 2000 chars
    assert r.status_code == 200


def test_feedback_comment_cap():
    r = client.post("/feedback", json={"item_id": "maggi", "rating": 1,
                                       "comment": "x" * 501})
    assert r.status_code == 422


def test_session_id_capped():
    sid = "s" * 200
    try:
        r = client.post("/chat", json={"message": "hi", "session_id": sid}).json()
        assert len(r["session_id"]) <= 64
    finally:
        _drop_session(("s" * 200)[:64])


# ---------- 3. memory caps ----------

def test_memory_maps_stay_bounded():
    mem = blank("tg_caps")
    for i in range(250):
        MemoryStore.record_feedback(mem, mem, f"item_{i}", 1)
        MemoryStore.record_order(mem, mem, [f"item_{i}"])
        MemoryStore.mark_warned(mem, mem, f"item_{i}")
    assert len(mem["likes"]) <= 200
    assert len(mem["orders"]) <= 200
    assert len(mem["health_warned"]) <= 100
    # Newest entries survive, oldest evict.
    assert "item_249" in mem["likes"] and "item_0" not in mem["likes"]


# ---------- 5. daily-spend analytics shapes ----------

def test_spending_by_day_shape():
    s = client.get("/spending", params={"session_id": "t20_nobody_xyz"}).json()
    assert len(s["by_day"]) == 7
    totals = [d["total"] for d in s["by_day"]]
    assert all(t == 0 for t in totals)  # unknown session: zeros, still shaped
    assert [d["count"] for d in s["by_day"]] == [0] * 7


def test_admin_revenue_by_day_shape():
    a = client.get("/admin/analytics").json()
    days = a["revenue_by_day"]
    assert len(days) == 7 and all(set(d) == {"date", "total", "count"} for d in days)
    assert sum(d["total"] for d in days) <= a["revenue"]
    assert all(d["total"] >= 0 and d["count"] >= 0 for d in days)


# ---------- 6. serverless-deploy plumbing ----------

def test_vercel_data_dir_override(tmp_path):
    import subprocess, sys
    target = tmp_path / "writable"
    code = ("import backend.app as a, backend.memory as m;"
            "print(a.ORDERS_PATH); print(a.FEEDBACK_PATH);"
            "print(m.MemoryStore().path); print(len(a.store.all()))")
    env = dict(__import__("os").environ,
               CAMPUSBITE_DATA_DIR=str(target), CAMPUSBITE_OFFLINE="1")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, env=env, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    lines = out.stdout.strip().splitlines()
    assert all(str(target) in ln for ln in lines[:3])
    assert lines[3].strip() == "53"  # menu still reads from the bundle


def test_menu_save_silent_on_readonly_fs(tmp_path):
    from backend.store import MenuStore
    s = MenuStore(ROOT / "data" / "menu_data.json")
    s.path = tmp_path  # a directory: writes fail like a read-only bundle
    s.save()  # must never raise (Supabase upserts persist instead)


# ---------- 4. conversational gaps ----------

def test_past_order_reorder_flow():
    sid = "tg_reorder"
    token = None
    try:
        o = client.post("/order", json={"tray_ids": ["maggi"],
                                        "session_id": sid}).json()
        token = o["token"]
        r = client.post("/chat", json={"message": "repeat last order",
                                       "session_id": sid}).json()
        assert r["intent"] == "reorder"
        assert r["singles"]
    finally:
        if token:
            rows = [x for x in _rows(ORDERS) if x.get("token") != token]
            _write(ORDERS, rows)
        _drop_session(sid)


def test_avoid_exclusion_filters_and_acknowledges():
    sid = "tg_avoid"
    try:
        r = client.post("/chat", json={"message": "something under 150 without paneer",
                                       "session_id": sid}).json()
        assert "paneer" in r["reply"].lower()
        for c in r["singles"]:
            hay = " ".join([c.get("name", ""), c.get("description", ""),
                            " ".join(c.get("ingredients", []))]).lower()
            assert "paneer" not in hay
    finally:
        _drop_session(sid)


def test_diabetic_greeting_is_fit_first():
    sid = "tg_diagreet"
    try:
        client.post("/chat", json={"message": "i have diabetes",
                                   "session_id": sid}).json()
        r = client.post("/chat", json={"message": "hi",
                                       "session_id": sid}).json()
        assert "diabetes in mind" in r["reply"]
        live = {i.id: i for i in MenuStore(MENU).all()}
        cards = r.get("singles", []) + r.get("combos", [])
        assert cards
        for c in cards:
            if c.get("is_dynamic"):
                continue
            assert diabetic_fit(live[c["id"]]), c["id"]
    finally:
        _drop_session(sid)
