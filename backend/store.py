"""MenuStore — JSON-backed live menu with admin mutations + analytics hooks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from backend.models import MenuItem

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "menu_data.json"


class MenuStore:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self._items: dict[str, MenuItem] = {}
        # Minimal analytics counters (also persisted to feedback log by API layer).
        self.analytics: dict[str, Any] = {"views": {}, "orders": {}, "feedbacks": []}
        self.reload()

    # ----- loading / persistence -----
    def reload(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._items = {r["id"]: MenuItem(**r) for r in raw}

    def save(self) -> None:
        # Best-effort: on read-only hosts (e.g. Vercel serverless) the bundled
        # menu file can't be rewritten — Supabase upserts (done by callers)
        # remain the persistent path, so a file failure must never 500.
        try:
            payload = [i.model_dump() for i in self._items.values()]
            self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    # ----- reads -----
    def all(self) -> list[MenuItem]:
        return list(self._items.values())

    def load_items(self, items: list[MenuItem], persist: bool = False) -> int:
        """Replace in-memory menu (e.g. from Supabase); optionally persist."""
        self._items = {i.id: i for i in items}
        if persist:
            self.save()
        return len(self._items)

    def live(self) -> list[MenuItem]:
        return [i for i in self._items.values() if i.availability]

    def get(self, item_id: str) -> Optional[MenuItem]:
        return self._items.get(item_id)

    def cheapest(self, n: int = 3, available_only: bool = True) -> list[MenuItem]:
        pool = self.live() if available_only else self.all()
        return sorted(pool, key=lambda i: i.price)[:n]

    # ----- admin mutations (runtime toggles) -----
    def set_availability(self, item_id: str, available: bool, persist: bool = True) -> MenuItem:
        item = self._require(item_id)
        item.availability = available
        if persist:
            self.save()
        return item

    def toggle_availability(self, item_id: str, persist: bool = True) -> MenuItem:
        item = self._require(item_id)
        return self.set_availability(item_id, not item.availability, persist=persist)

    def update_price(self, item_id: str, new_price: float, persist: bool = True) -> MenuItem:
        if new_price < 0:
            raise ValueError("Price must be >= 0")
        item = self._require(item_id)
        item.price = new_price
        if persist:
            self.save()
        return item

    def update_item(self, item_id: str, patch: dict, persist: bool = True) -> MenuItem:
        """Generic admin edit (additive): price, prep_time, popularity, nutrition, availability."""
        item = self._require(item_id)
        allowed = {"price", "prep_time_minutes", "popularity_score", "calories",
                   "protein_g", "carbs_g", "sugar_g", "fiber_g",
                   "availability", "description", "spice_level"}
        data = item.model_dump()
        for k, v in (patch or {}).items():
            if k not in allowed:
                continue
            if k == "price" and (not isinstance(v, (int, float)) or v < 0):
                raise ValueError("Price must be >= 0")
            if k == "prep_time_minutes" and (not isinstance(v, int) or isinstance(v, bool) or not 2 <= v <= 25):
                raise ValueError("prep_time_minutes must be an integer 2..25")
            if k == "popularity_score" and (not isinstance(v, int) or not 0 <= v <= 100):
                raise ValueError("popularity_score must be 0..100")
            if k in ("calories", "protein_g", "carbs_g", "sugar_g", "fiber_g") \
                    and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
                raise ValueError(f"{k} must be an integer >= 0")
            if k == "spice_level" and (not isinstance(v, int) or not 0 <= v <= 3):
                raise ValueError("spice_level must be 0..3")
            if k == "availability" and not isinstance(v, bool):
                raise ValueError("availability must be boolean")
            data[k] = v
        from backend.models import MenuItem as _MI
        updated = _MI(**data)
        self._items[item_id] = updated
        if persist:
            self.save()
        return updated

    def bulk_availability(self, ids: list[str], available: bool, persist: bool = True) -> int:
        n = 0
        for i in ids or []:
            if i in self._items:
                self._items[i].availability = available
                n += 1
        if persist and n:
            self.save()
        return n

    def mark_all_live(self, persist: bool = True) -> int:
        n = 0
        for it in self._items.values():
            if not it.availability:
                it.availability = True
                n += 1
        if persist and n:
            self.save()
        return n

    def add_item(self, data: dict, persist: bool = True) -> MenuItem:
        item = MenuItem(**data)
        if item.id in self._items:
            raise ValueError(f"Item id '{item.id}' already exists")
        self._items[item.id] = item
        if persist:
            self.save()
        return item

    def _require(self, item_id: str) -> MenuItem:
        item = self._items.get(item_id)
        if item is None:
            raise KeyError(f"Unknown menu item '{item_id}'")
        return item
