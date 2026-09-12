"""Supabase adapter tests — all offline (HTTP monkeypatched / unconfigured)."""
from pathlib import Path

import backend.db_supabase as db
from backend.store import MenuStore

ROOT = Path(__file__).resolve().parents[1]


def test_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    assert db.is_configured() is False
    assert db.fetch_menu() is None
    assert db.upsert_menu([]) is False
    assert db.log_feedback({}) is False
    assert db.log_order({}) is False


def test_row_round_trip():
    store = MenuStore(ROOT / "data" / "menu_data.json")
    item = store.get("masala_dosa")
    row = db.item_to_row(item)
    assert row["id"] == "masala_dosa" and row["price"] == 60
    assert row["category"] == "breakfast" and "veg" in row["dietary_tags"]
    assert isinstance(row["ingredients"], list)
    back = db.row_to_item(row)
    assert back.id == item.id and back.price == item.price
    assert back.availability == item.availability


def test_upsert_posts_merged_chunks(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc-key")
    posted = []

    class FakeResp:
        status_code = 201

    class FakeHttpx:
        @staticmethod
        def post(url, timeout=None, headers=None, json=None):
            posted.append((url, headers.get("Prefer"), len(json)))
            # key must not leak into printables — assert header shape only
            assert headers["apikey"] == "svc-key"
            return FakeResp()

    monkeypatch.setitem(__import__("sys").modules, "httpx", FakeHttpx)
    store = MenuStore(ROOT / "data" / "menu_data.json")
    assert db.upsert_menu(store.all()) is True
    assert posted and all(p[1] == "resolution=merge-duplicates" for p in posted)
    assert sum(p[2] for p in posted) == len(store.all())


def test_sync_script_dry_run():
    import subprocess
    import sys
    r = subprocess.run(
        [sys.executable, str(ROOT / "data" / "sync_to_supabase.py"), "--dry-run"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    assert "53 items ready" in r.stdout and '"id": "masala_dosa"' in r.stdout
