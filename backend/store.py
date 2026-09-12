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
        payload = [i.model_dump() for i in self._items.values()]
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

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
