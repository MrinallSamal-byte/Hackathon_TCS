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


def _default_path() -> Path:
    """Honor CAMPUSBITE_DATA_DIR (serverless-writable override); on Vercel /
    Lambda default to /tmp (bundle is read-only); else the bundled data dir."""
    import os as _os
    raw = _os.environ.get("CAMPUSBITE_DATA_DIR")
    if raw:
        return Path(raw) / "memory.json"
    if _os.environ.get("VERCEL") or _os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp/campusbite-data") / "memory.json"
    return Path(__file__).resolve().parents[1] / "data" / "memory.json"
_HISTORY_CAP = 20
# Abuse guard: per-session maps must stay bounded no matter how many
# feedback/order/chat turns a client fires. Oldest entries evict first.
_LIKES_CAP = 200
_ORDERS_MAP_CAP = 200
_WARNED_CAP = 100
_COUPONS_CAP = 10
# Global session cap: the memory mirror is a dict keyed by client-supplied
# ids — without a bound one client minting random ids could grow the JSON
# file without limit (disk/memory DOS).
_SESSIONS_CAP = 2000

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
        "favorites": [],
        "profile": {},
        "health_conditions": [],
        "health_warned": {},
        "updated_at": _now(),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cap_map(d: dict, cap: int) -> dict:
    """Evict oldest keys while a per-session map exceeds its cap."""
    while len(d) > cap:
        d.pop(next(iter(d)))
    return d


class MemoryStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else _default_path()
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
        # Backfill new keys for memories created before these features existed.
        mem.setdefault("favorites", [])
        mem.setdefault("profile", {})
        mem.setdefault("health_conditions", [])
        mem.setdefault("health_warned", {})
        mem.setdefault("orders", {})
        mem.setdefault("likes", {})
        mem.setdefault("budgets", [])
        mem.setdefault("moods", [])
        mem.setdefault("chats", 0)
        return mem

    def save(self, session_id: str, mem: dict[str, Any]) -> None:
        mem["updated_at"] = _now()
        self._data[session_id] = mem
        # Bound total sessions (evict oldest-inserted first).
        while len(self._data) > _SESSIONS_CAP:
            try:
                self._data.pop(next(iter(self._data)))
            except StopIteration:
                break
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
        likes = mem.setdefault("likes", {})
        if rating > 0:
            likes[item_id] = 1
        elif rating < 0:
            likes[item_id] = -1
        _cap_map(likes, _LIKES_CAP)
        return mem

    def record_order(self, mem: dict, item_ids: list[str]) -> dict:
        orders = mem.setdefault("orders", {})
        for i in item_ids:
            orders[i] = int(orders.get(i, 0)) + 1
        _cap_map(orders, _ORDERS_MAP_CAP)
        return mem

    # ----- favorites + profile (additive; never affect hard filters) -----
    def toggle_favorite(self, mem: dict, item_id: str) -> bool:
        favs = mem.setdefault("favorites", [])
        if item_id in favs:
            favs.remove(item_id)
            return False
        favs.append(item_id)
        mem["favorites"] = favs[-50:]
        return True

    def get_profile(self, mem: dict) -> dict:
        return dict(mem.get("profile") or {})

    def save_profile(self, mem: dict, patch: dict) -> dict:
        prof = dict(mem.get("profile") or {})
        for k in ("dietary_restrictions", "allergies", "goal", "budget",
                  "weekly_budget", "no_onion_garlic", "hunger", "cuisine",
                  "max_spice", "max_prep_time", "health_conditions"):
            if k in patch and patch[k] is not None:
                prof[k] = patch[k]
        mem["profile"] = prof
        return prof

    def record_health(self, mem: dict, stated: dict) -> list[str]:
        """Persist user-stated health facts so next visits auto-respect them.

        stated: {"goal":..|None, "dietary":[..], "allergies":[..], "conditions":[..]}.
        Diet is REPLACED (a new claim supersedes), allergies/conditions UNION.
        Returns the newly-added conditions (for acknowledgement replies).
        """
        prof = dict(mem.get("profile") or {})
        if stated.get("goal"):
            prof["goal"] = stated["goal"]
        if stated.get("dietary"):
            prof["dietary_restrictions"] = list(stated["dietary"])
        if stated.get("allergies"):
            cur = list(prof.get("allergies") or [])
            for a in stated["allergies"]:
                if a not in cur:
                    cur.append(a)
            prof["allergies"] = cur
        added: list[str] = []
        if stated.get("conditions"):
            cur_c = list(mem.get("health_conditions") or []) + list(prof.get("health_conditions") or [])
            for c in stated["conditions"]:
                if c not in cur_c:
                    cur_c.append(c)
                    added.append(c)
            mem["health_conditions"] = sorted(set(cur_c))
            prof["health_conditions"] = sorted(set(cur_c))
        mem["profile"] = prof
        return added

    def mark_warned(self, mem: dict, item_id: str) -> None:
        warned = mem.setdefault("health_warned", {})
        warned[item_id] = warned.get(item_id, 0) + 1
        _cap_map(warned, _WARNED_CAP)

    def was_warned(self, mem: dict, item_id: str) -> bool:
        return int((mem.get("health_warned") or {}).get(item_id, 0)) > 0

    def apply_profile_defaults(self, mem: dict, prefs: Any) -> Any:
        """Fill prefs fields the user didn't state from their saved profile."""
        prof = mem.get("profile") or {}
        if not prof:
            return prefs
        try:
            data = prefs.model_dump()
            is_model = True
        except Exception:
            data = dict(prefs) if isinstance(prefs, dict) else {}
            is_model = False
        if not data.get("dietary_restrictions") and prof.get("dietary_restrictions"):
            data["dietary_restrictions"] = list(prof["dietary_restrictions"])
        if not data.get("allergies") and prof.get("allergies"):
            try:
                from backend.models import Allergen as _Alg
                conv = []
                for a in prof["allergies"]:
                    try:
                        conv.append(_Alg(a))
                    except Exception:
                        continue
                if conv:
                    data["allergies"] = conv
            except Exception:
                pass
        def _missing(v: Any) -> bool:
            # NOTE: `0 in (None, [], {}, False)` is True in Python (0 == False),
            # so max_spice=0 ("no spice") must NOT count as missing.
            return v is None or v is False or v == [] or v == {}

        def _present(v: Any) -> bool:
            return v is not None and v != [] and v != {}

        for k in ("goal", "hunger", "cuisine", "max_spice", "max_prep_time",
                  "no_onion_garlic", "budget"):
            if _missing(data.get(k)) and _present(prof.get(k)):
                # budget=False never happens; keep guard simple and safe
                if k == "no_onion_garlic" and not prof.get(k):
                    continue
                data[k] = prof[k]
        if is_model:
            try:
                from backend.models import UserPreferences as _UP
                return _UP(**{k: v for k, v in data.items() if k in _UP.model_fields})
            except Exception:
                return prefs
        return data

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
