"""Seed realistic demo data so the site looks alive on first open.

Writes deterministic (seeded) rows to the gitignored runtime mirrors:
  data/order_history.json  ~60 orders across the last 7 days (demo_* sessions)
  data/feedback_log.json   ~45 ratings with real student-style comments
  data/memory.json         4 demo sessions (budgets, moods, orders, likes,
                           profiles — incl. a diabetic + a gym-goer)

Idempotent: if any demo_* rows already exist it exits without changes
(pass --force to reseed). NEVER touches data/menu_data.json (no popularity
drift, seed of truth stays intact).

Usage:
    .venv/bin/python data/seed_demo.py [--force]
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MENU_PATH = ROOT / "data" / "menu_data.json"
ORDERS_PATH = ROOT / "data" / "order_history.json"
FEEDBACK_PATH = ROOT / "data" / "feedback_log.json"
MEMORY_PATH = ROOT / "data" / "memory.json"

SEED = 20260914
TOKEN_PREFIX = "CB-D"

COUNTER_LABEL = {"main": "Main Counter", "snacks": "Snacks Counter",
                 "beverages": "Beverages Counter"}
CAT_COUNTER = {"main_course": "main", "breakfast": "main", "combo": "main",
               "snack": "snacks", "beverage": "beverages", "dessert": "beverages"}
COUPONS = {"STUDENT10": 0.10, "FESTIVE15": 0.15, "FIRSTORDER": 0.20}

# (session, diet filter, goal, weekly budget, profile extras)
PERSONAS = [
    ("demo_arjun", None, "high_protein", 900, {"hunger": "hungry"}),
    ("demo_priya", "veg", None, 600, {"no_onion_garlic": False}),
    ("demo_kabir", None, "diabetic", 700, {"health_conditions": ["diabetes"]}),
    ("demo_meera", "veg", "low_calorie", 500, {}),
]

BUDGETS = [60, 70, 80, 80, 90, 100, 120, 150]
MOODS = ["hungry", "stressed", "happy", "tired", "exam-mode", "celebrating"]
COMMENTS_POS = [
    "tastes just like home, will order again",
    "perfect between lectures, quick and hot",
    "great value for the price",
    "my usual — never disappoints",
    "good portion, filling enough for dinner",
    "canteen classic, always fresh",
    "loved it with extra chutney",
    "best thing under Rs 100 here",
]
COMMENTS_NEG = [
    "too spicy for me",
    "arrived a bit cold",
    "portion felt small for the price",
]


def _read_list(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _read_dict(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def has_demo() -> bool:
    for r in _read_list(ORDERS_PATH) + _read_list(FEEDBACK_PATH):
        if str(r.get("session_id", "")).startswith("demo_"):
            return True
    return any(k.startswith("demo_") for k in _read_dict(MEMORY_PATH))


def fits_diet(item: dict, diet: str | None) -> bool:
    if not diet:
        return True
    tags = [str(t).lower() for t in item.get("dietary_tags", [])]
    if diet == "veg":
        return "non_veg" not in tags and "egg" not in tags
    return True


def diabetic_ok(item: dict) -> bool:
    if item.get("is_combo"):
        return False
    if str(item.get("category", "")).lower() == "dessert":
        return False
    try:
        return float(item.get("sugar_g", 99)) <= 10 and float(item.get("carbs_g", 99)) <= 45
    except (TypeError, ValueError):
        return False


def build_demo_orders(menu: list) -> list[dict]:
    rng = random.Random(SEED)
    live = [m for m in menu if m.get("availability")]
    orders: list[dict] = []
    n = 0
    now = datetime.now()
    for day_ago in range(6, -1, -1):
        day = now - timedelta(days=day_ago)
        # 6-10 orders/day, clustered at breakfast / lunch / dinner rush.
        for _ in range(rng.randint(6, 10)):
            sid, diet, goal, _, _ = rng.choice(PERSONAS)
            pool = [m for m in live if fits_diet(m, diet)]
            if goal == "diabetic":
                pool = [m for m in pool if diabetic_ok(m)] or pool
            if not pool:
                continue
            tray = sorted(rng.sample([m["id"] for m in pool],
                                     k=min(len(pool), rng.choice([1, 1, 2, 2, 3]))))
            items = [m for m in pool if m["id"] in tray]
            total = round(sum(float(m["price"]) for m in items), 2)
            coupon, discount, payable = None, 0.0, total
            roll = rng.random()
            if sid == "demo_meera" and day_ago == 6 and n == 0:
                coupon = "FIRSTORDER"
            elif roll < 0.25:
                coupon = "STUDENT10"
            elif roll < 0.33:
                coupon = "FESTIVE15"
            if coupon:
                discount = round(total * COUPONS[coupon], 2)
                payable = round(total - discount, 2)
            hour = rng.choice([8, 9, 9, 12, 13, 13, 14, 17, 19, 20, 20, 21])
            at = day.replace(hour=hour, minute=rng.randint(0, 59),
                             second=0, microsecond=0)
            if at > now:
                at = now - timedelta(minutes=rng.randint(5, 40))
            counter = CAT_COUNTER.get(str(items[0].get("category", "")), "main")
            n += 1
            orders.append({
                "token": f"{TOKEN_PREFIX}{1000 + n}",
                "tray": tray, "total": total, "payable": payable,
                "coupon": coupon, "discount": discount,
                "counter": counter, "counter_label": COUNTER_LABEL[counter],
                "budget": total + rng.choice([0, 5, 10, 15, 20]),
                "eta": max(int(m.get("prep_time_minutes", 5)) for m in items),
                "at": at.isoformat(), "session_id": sid,
            })
    return orders


def build_demo_feedback(menu: list) -> list[dict]:
    rng = random.Random(SEED + 1)
    live = [m for m in menu if m.get("availability")]
    popular = sorted(live, key=lambda m: -float(m.get("popularity_score", 0)))[:18]
    rows: list[dict] = []
    now = datetime.now()
    for i in range(45):
        item = rng.choice(popular)
        sid, _, _, _, _ = rng.choice(PERSONAS)
        neg = rng.random() < 0.15
        at = now - timedelta(days=rng.randint(0, 6),
                             hours=rng.randint(0, 12))
        rows.append({
            "item_id": item["id"], "rating": -1 if neg else 1,
            "comment": rng.choice(COMMENTS_NEG if neg else COMMENTS_POS),
            "budget": rng.choice(BUDGETS), "mood": rng.choice(MOODS),
            "at": at.isoformat(), "session_id": sid,
        })
    rows.sort(key=lambda r: r["at"])
    return rows


def build_demo_memories(orders: list[dict], feedbacks: list[dict]) -> dict[str, dict]:
    mems: dict[str, dict] = {}
    for sid, diet, goal, weekly, extra in PERSONAS:
        mine_o = [o for o in orders if o["session_id"] == sid]
        mine_f = [f for f in feedbacks if f["session_id"] == sid]
        counts: dict[str, int] = {}
        for o in mine_o:
            for tid in o["tray"]:
                counts[tid] = counts.get(tid, 0) + 1
        likes: dict[str, int] = {}
        for f in mine_f:
            likes[f["item_id"]] = f["rating"]
        budgets = sorted({int(o["budget"]) for o in mine_o})[:8] or [80]
        profile = {"weekly_budget": weekly}
        if diet:
            profile["dietary_restrictions"] = [diet]
        if goal:
            profile["goal"] = goal
            if goal == "diabetic":
                profile["health_conditions"] = ["diabetes"]
        profile.update(extra)
        mems[sid] = {
            "session_id": sid, "prefs": {"budget": budgets[-1]},
            "budgets": budgets, "moods": MOODS[:6],
            "orders": counts, "likes": likes, "chats": len(mine_o) + 4,
            "favorites": sorted(counts, key=lambda k: -counts[k])[:4],
            "profile": profile,
            "health_conditions": ["diabetes"] if goal == "diabetic" else [],
            "health_warned": {}, "coupons_used": [],
            "updated_at": datetime.now().isoformat(),
        }
    return mems


def main() -> int:
    force = "--force" in sys.argv
    if has_demo() and not force:
        print("Demo data already present (demo_* rows). Pass --force to reseed.")
        return 0
    menu = json.loads(MENU_PATH.read_text(encoding="utf-8"))
    orders = build_demo_orders(menu)
    feedbacks = build_demo_feedback(menu)
    mems = build_demo_memories(orders, feedbacks)
    if force:
        orders = [r for r in _read_list(ORDERS_PATH)
                  if not str(r.get("session_id", "")).startswith("demo_")] + orders
        feedbacks = [r for r in _read_list(FEEDBACK_PATH)
                     if not str(r.get("session_id", "")).startswith("demo_")] + feedbacks
        mem_all = {k: v for k, v in _read_dict(MEMORY_PATH).items()
                   if not k.startswith("demo_")}
        mem_all.update(mems)
    else:
        orders = _read_list(ORDERS_PATH) + orders
        feedbacks = _read_list(FEEDBACK_PATH) + feedbacks
        mem_all = _read_dict(MEMORY_PATH)
        mem_all.update(mems)
    _write(ORDERS_PATH, orders)
    _write(FEEDBACK_PATH, feedbacks)
    _write(MEMORY_PATH, mem_all)
    print(f"Seeded {len([o for o in orders if o['session_id'].startswith('demo_')])} orders, "
          f"{len([f for f in feedbacks if f['session_id'].startswith('demo_')])} feedback rows, "
          f"{len(mems)} demo sessions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
