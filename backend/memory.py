"""Per-session memory — the AI remembers every user across restarts.

What is remembered per session_id:
  prefs      last known preferences snapshot (diet, allergies, hunger, ...)
  budgets    recent budgets (for the "usual budget" fallback)
  moods      recent moods (for trend analytics + greeting tone)
  orders     item_id -> times ordered
  likes      item_id -> +1 / dislikes -> -1 (from feedback)
  chats      number of recommendation turns

Where it lives:
  1. Supabase `chat_memory` table (when configured) — source of truth,
  2. data/memory.json — local mirror + full fallback when offline.

Every interaction updates it: /chat (recommend/refine), /feedback, /order.
Personalization derived from it (all additive, hard filters NEVER relax):
  liked item ......... +8    ordered before ..... +3 (familiarity, capped)
  disliked item ...... -25   fav cuisine ........ +3 (affinity, no hard filter)
  usual budget ....... median of past budgets (used only when user states none)
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "memory.json"
_HISTORY_CAP = 20

LIKED_BOOST = 8.0
ORDERED_BOOST = 3.0
DISLIKED_PENALTY = -25.0
CUISINE_AFFINITY_BOOST = 3.0


def blank(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "prefs": {},
        "budgets": [],
        "moods": [],
        "orders": {},
        "likes": {},
        "chats": 0,
        "updated_at": _now(),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self._data: dict[str, dict] = {}
        self._load_local()

    # ----- persistence -----
    def _load_local(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw
        except Exception:
            self._data = {}

    def _save_local(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get(self, session_id: str) -> dict[str, Any]:
        """Return memory, preferring Supabase when configured (then mirror locally)."""
        mem = self._data.get(session_id)
        try:
            from backend import db_supabase as db
            if db.is_configured():
                remote = db.memory_get(session_id)
                if remote:
                    mem = remote
                    self._data[session_id] = remote
        except Exception:
            pass
        if not mem:
            mem = blank(session_id)
            self._data[session_id] = mem
        return mem

    def save(self, session_id: str, mem: dict[str, Any]) -> None:
        mem["updated_at"] = _now()
        self._data[session_id] = mem
        self._save_local()
        try:
            from backend import db_supabase as db
            if db.is_configured():
                db.memory_put(session_id, mem)
        except Exception:
            pass

    # ----- recorders (called on EVERY interaction) -----
    def record_chat(self, mem: dict, prefs: Any) -> dict:
        try:
            snap = prefs.model_dump()
        except Exception:
            snap = dict(prefs) if isinstance(prefs, dict) else {}
        mem["prefs"] = {k: v for k, v in snap.items() if v not in (None, [], {}, False)}
        if isinstance(snap.get("budget"), (int, float)):
            mem["budgets"].append(float(snap["budget"]))
            mem["budgets"] = mem["budgets"][-_HISTORY_CAP:]
        if snap.get("mood"):
            mem["moods"].append(str(snap["mood"]))
            mem["moods"] = mem["moods"][-_HISTORY_CAP:]
        mem["chats"] = int(mem.get("chats", 0)) + 1
        return mem

    def record_feedback(self, mem: dict, item_id: str, rating: int) -> dict:
        if rating > 0:
            mem["likes"][item_id] = 1
        elif rating < 0:
            mem["likes"][item_id] = -1
        return mem

    def record_order(self, mem: dict, item_ids: list[str]) -> dict:
        orders = mem.setdefault("orders", {})
        for i in item_ids:
            orders[i] = int(orders.get(i, 0)) + 1
        return mem

    # ----- derived personalization -----
    def usual_budget(self, mem: dict) -> Optional[float]:
        budgets = [b for b in mem.get("budgets", []) if isinstance(b, (int, float))]
        if len(budgets) >= 2:
            return round(float(statistics.median(budgets)), 2)
        return None

    def cuisine_affinity(self, mem: dict, cuisine_of: dict[str, str]) -> Optional[str]:
        counts: dict[str, int] = {}
        for item_id, n in (mem.get("orders") or {}).items():
            c = cuisine_of.get(item_id)
            if c:
                counts[c] = counts.get(c, 0) + int(n)
        if not counts or sum(counts.values()) < 2:
            return None
        return max(counts, key=lambda k: counts[k])


def boost_singles(
    scored: list[tuple],
    mem: dict,
    cuisine_of: Optional[dict[str, str]] = None,
) -> list[tuple]:
    """Re-rank (item, score, breakdown) with memory boosts. Never filters."""
    likes = mem.get("likes", {}) or {}
    orders = mem.get("orders", {}) or {}
    affinity: Optional[str] = None
    if cuisine_of:
        counts: dict[str, int] = {}
        for iid, n in orders.items():
            c = cuisine_of.get(iid)
            if c:
                counts[c] = counts.get(c, 0) + int(n)
        if counts and sum(counts.values()) >= 2:
            affinity = max(counts, key=lambda k: counts[k])

    out = []
    for item, score, breakdown in scored:
        delta = 0.0
        mark = likes.get(item.id, 0)
        if mark > 0:
            delta += LIKED_BOOST
        elif mark < 0:
            delta += DISLIKED_PENALTY
        if orders.get(item.id):
            delta += min(ORDERED_BOOST * 2, ORDERED_BOOST)  # capped familiarity
        if affinity and cuisine_of and cuisine_of.get(item.id) == affinity:
            delta += CUISINE_AFFINITY_BOOST
        br = dict(breakdown or {})
        br["memory"] = round(delta, 2)
        out.append((item, round(score + delta, 2), br))
    out.sort(key=lambda t: (t[1], t[0].popularity_score), reverse=True)
    return out
