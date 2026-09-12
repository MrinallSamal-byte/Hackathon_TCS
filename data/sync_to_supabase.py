"""One-shot sync: push data/menu_data.json into Supabase `menu_items`.

Run:
    python3 data/sync_to_supabase.py            # upsert all 53 items
    python3 data/sync_to_supabase.py --dry-run  # show first row payload only

Requires SUPABASE_URL + SUPABASE_SERVICE_KEY in the environment or repo .env.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db_supabase as db  # noqa: E402
from backend.llm import ensure_env  # noqa: E402 (reuses the no-dep .env loader)
from backend.store import MenuStore  # noqa: E402

ensure_env()


def main() -> None:
    dry = "--dry-run" in sys.argv
    store = MenuStore()
    items = store.all()
    if dry or not db.is_configured():
        row = db.item_to_row(items[0])
        print(f"[dry-run] {len(items)} items ready. First row:")
        print(json.dumps(row, indent=2)[:800])
        if not dry:
            print("Supabase not configured — set SUPABASE_URL + SUPABASE_SERVICE_KEY.")
        return
    ok = db.upsert_menu(items)
    print(f"Upserted {len(items)} items -> {'OK' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
