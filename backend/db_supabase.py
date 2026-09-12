"""Supabase Postgres adapter for CampusBite (PostgREST via httpx, no new deps).

- Active only when SUPABASE_URL + (SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY)
  are set; otherwise every function is a silent no-op and the JSON files in
  data/ remain the source of truth.
- Server-side writes prefer the SERVICE key (bypasses RLS); reads work with
  either key. Keys are read from the environment only — never logged.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from backend.models import MenuItem


def _base() -> Optional[tuple[str, str]]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
    if not url or not key:
        return None
    return url, key


def is_configured() -> bool:
    return _base() is not None


def _headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"}


def item_to_row(item: MenuItem) -> dict[str, Any]:
    d = item.model_dump()
    for k in ("category", "cuisine", "portion_size"):
        d[k] = getattr(item, k).value
    d["allergens"] = [str(a).split(".")[-1] for a in item.allergens]
    d["dietary_tags"] = [str(x).split(".")[-1] for x in item.dietary_tags]
    d["serving_times"] = [str(s).split(".")[-1] for s in item.serving_times]
    return d  # available_until passes through as str|None from model_dump


def row_to_item(row: dict[str, Any]) -> MenuItem:
    return MenuItem(**{k: v for k, v in row.items() if k != "updated_at"})


def fetch_menu() -> Optional[list[MenuItem]]:
    cfg = _base()
    if not cfg:
        return None
    url, key = cfg
    try:
        import httpx
        r = httpx.get(f"{url}/rest/v1/menu_items",
                      params={"select": "*", "order": "price.asc"},
                      headers={**_headers(key)}, timeout=10)
        if r.status_code != 200:
            return None
        return [row_to_item(row) for row in r.json()]
    except Exception:
        return None


def upsert_menu(items: list[MenuItem]) -> bool:
    """Full-menu upsert (used by the sync script and admin edits)."""
    cfg = _base()
    if not cfg:
        return False
    url, key = cfg
    try:
        import httpx
        rows = [item_to_row(i) for i in items]
        # PostgREST bulk upsert in one round-trip (chunked for safety).
        for j in range(0, len(rows), 100):
            r = httpx.post(
                f"{url}/rest/v1/menu_items", timeout=20,
                headers={**_headers(key), "Prefer": "resolution=merge-duplicates"},
                json=rows[j:j + 100])
            if r.status_code not in (200, 201):
                return False
        return True
    except Exception:
        return False


def log_feedback(row: dict[str, Any]) -> bool:
    cfg = _base()
    if not cfg:
        return False
    url, key = cfg
    try:
        import httpx
        payload = {"item_id": row.get("item_id"), "rating": row.get("rating"),
                   "comment": row.get("comment"), "budget": row.get("budget"),
                   "mood": row.get("mood")}
        r = httpx.post(f"{url}/rest/v1/feedback_log", timeout=10,
                       headers={**_headers(key)}, json=payload)
        return r.status_code in (200, 201)
    except Exception:
        return False


def log_order(row: dict[str, Any]) -> bool:
    cfg = _base()
    if not cfg:
        return False
    url, key = cfg
    try:
        import httpx
        payload = {"token": row.get("token"), "tray": row.get("tray", []),
                   "total": row.get("total", 0), "budget": row.get("budget"),
                   "eta": row.get("eta")}
        r = httpx.post(f"{url}/rest/v1/order_history", timeout=10,
                       headers={**_headers(key)}, json=payload)
        return r.status_code in (200, 201)
    except Exception:
        return False


# ---------- per-session memory (chat_memory table) ----------

def memory_get(session_id: str) -> Optional[dict[str, Any]]:
    cfg = _base()
    if not cfg or not session_id:
        return None
    url, key = cfg
    try:
        import httpx
        r = httpx.get(
            f"{url}/rest/v1/chat_memory",
            params={"select": "data", "session_id": f"eq.{session_id}", "limit": 1},
            headers={**_headers(key)}, timeout=10)
        if r.status_code != 200:
            return None
        rows = r.json()
        if rows and isinstance(rows[0].get("data"), dict):
            return rows[0]["data"]
        return None
    except Exception:
        return None


def memory_put(session_id: str, data: dict[str, Any]) -> bool:
    cfg = _base()
    if not cfg or not session_id:
        return False
    url, key = cfg
    try:
        import httpx
        r = httpx.post(
            f"{url}/rest/v1/chat_memory", timeout=10,
            headers={**_headers(key), "Prefer": "resolution=merge-duplicates"},
            json={"session_id": session_id, "data": data})
        return r.status_code in (200, 201)
    except Exception:
        return False
