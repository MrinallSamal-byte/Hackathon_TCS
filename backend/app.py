"""CampusBite FastAPI backend — REST + deterministic recommendation + chat orchestration."""
from __future__ import annotations

import json
import random
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from backend import db_supabase as db
from backend import queue as qmod
from backend.llm import (batch_phrase, merge_llm_patch, openrouter_available,
                         parse_prefs_with_llm)
from backend.memory import MemoryStore, boost_singles
from backend.models import MenuItem, UserPreferences
from backend.nlu import (apply_refinement, clarifying_questions, detect_intent, nonsense_reply,
                         parse_budget, parse_cravings, parse_dietary_allergy, parse_goal, parse_hunger,
                         parse_health_conditions, parse_meal, parse_one_shot, smalltalk_reply)
from backend.recommender import (cross_contamination_warning, diabetic_fit, diabetic_score,
                                 effective_prep_time,
                                 explain_item, infer_meal_period,
                                 passes_hard_filters, rank,
                                 recommend, substitutes_for)
from backend.store import MenuStore

ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_PATH = ROOT / "data" / "feedback_log.json"
ORDERS_PATH = ROOT / "data" / "order_history.json"

app = FastAPI(title="CampusBite", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

store = MenuStore()
memory_store = MemoryStore()
_cuisine_map: dict[str, str] = {}


def _cuisine_of() -> dict[str, str]:
    global _cuisine_map
    if not _cuisine_map:
        _cuisine_map = {i.id: i.cuisine.value for i in store.all()}
    return _cuisine_map


def _session(session_id: Optional[str]) -> tuple[str, dict]:
    # Abuse guard: session ids are client-supplied dict keys — bound their
    # length (real ids are 16-hex; 64 is generous) so one client can't bloat
    # the memory mirror with megabyte keys.
    sid = (session_id or "").strip()[:64] or uuid.uuid4().hex[:16]
    return sid, memory_store.get(sid)


def _expand_tray(tray_ids: list[str]) -> list[str]:
    """Dynamic combo ids (dyn_a__b) expand to component item ids."""
    flat: list[str] = []
    for raw in tray_ids:
        if raw.startswith("dyn_"):
            flat.extend(raw[4:].split("__"))
        else:
            flat.append(raw)
    return [f for f in flat if store.get(f)]


def _session_orders(sid: str) -> list[dict]:
    rows = [r for r in _read_json_list(ORDERS_PATH) if r.get("session_id") == sid]
    rows.sort(key=lambda r: r.get("at", ""), reverse=True)
    return rows


def _order_status(token: str) -> Optional[dict]:
    rows = [r for r in _read_json_list(ORDERS_PATH)
            if str(r.get("token", "")).upper() == token.upper()]
    if not rows:
        return None
    o = rows[-1]
    try:
        placed = datetime.fromisoformat(o.get("at", ""))
        elapsed = max(0, int((datetime.now() - placed).total_seconds() // 60))
    except Exception:
        elapsed = 0
    eta = int(o.get("eta") or 0)
    names = [(store.get(i).name if store.get(i) else i) for i in _expand_tray(o.get("tray", []))]
    override = str(o.get("status_override") or "").upper()
    if override == "CANCELLED":
        state, detail = "CANCELLED", "This order was cancelled — no pickup needed."
    elif override in ("READY", "COMPLETED"):
        state, detail = ("READY", "Ready for pickup — show your token at the counter.") \
            if override == "READY" else ("COMPLETED", "Order completed — enjoy your meal!")
    elif elapsed >= eta:
        state, detail = "READY", "Ready for pickup — show your token at the counter."
    else:
        state, detail = "PREPARING", f"Being prepared — ready in ~{eta - elapsed} min."
    return {"token": o.get("token"), "state": state, "detail": detail,
            "items": names, "total": o.get("total"),
            "payable": o.get("payable", o.get("total")),
            "coupon": o.get("coupon"),
            "counter": o.get("counter"), "counter_label": o.get("counter_label"),
            "eta_minutes": eta, "elapsed_minutes": elapsed}


# ---------- coupons / counters / bills (additive; totals never change) ----------
COUPONS: dict[str, float] = {
    "STUDENT10": 0.10,
    "FESTIVE15": 0.15,
    "FIRSTORDER": 0.20,
}


def _normalize_coupon(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    c = str(code).strip().upper()
    return c or None


def _apply_coupon(total: float, coupon_code: Optional[str]) -> dict[str, Any]:
    code = _normalize_coupon(coupon_code)
    if not code:
        return {"coupon": None, "discount": 0.0, "payable": round(total, 2), "coupon_error": None}
    pct = COUPONS.get(code)
    if pct is None:
        return {"coupon": code, "discount": 0.0, "payable": round(total, 2),
                "coupon_error": f"Unknown coupon '{code}'. Try STUDENT10."}
    discount = round(total * pct, 2)
    return {"coupon": code, "discount": discount, "payable": round(total - discount, 2),
            "coupon_error": None}


def _counter_for_tray(expanded: list) -> tuple[Optional[str], Optional[str]]:
    from backend.queue import counter_of, COUNTERS
    if not expanded:
        return None, None
    counter = counter_of(expanded[0].category.value)
    label = COUNTERS.get(counter, {}).get("label")
    return counter, label


def _cancel_order_row(token: str) -> dict:
    rows = _read_json_list(ORDERS_PATH)
    # Last match wins — same row _order_status() reports, so status and
    # cancel can never disagree even if a legacy duplicate token exists.
    idx = next((i for i in range(len(rows) - 1, -1, -1)
                if str(rows[i].get("token", "")).upper() == token.upper()), None)
    if idx is None:
        raise HTTPException(404, f"No order '{token}'")
    st = _order_status(token)
    if st and st["state"] in ("READY", "COMPLETED", "CANCELLED"):
        raise HTTPException(400, f"Order {token} is already {st['state']} and cannot be cancelled.")
    rows[idx]["status_override"] = "CANCELLED"
    _write_json_atomic(ORDERS_PATH, rows)
    return {"ok": True, "token": rows[idx]["token"], "state": "CANCELLED"}


def _trending_items(limit: int = 5) -> list[dict[str, Any]]:
    rmap = rating_stats()
    live = store.live() or store.all()
    scored = sorted(
        live,
        key=lambda i: ((rmap.get(i.id, {}).get("likes", 0)
                        - rmap.get(i.id, {}).get("dislikes", 0)),
                       i.popularity_score),
        reverse=True,
    )
    out = []
    for it in scored[:max(1, min(limit, 12))]:
        c = item_card(it, UserPreferences(), None, ratings=rmap)
        c["explanation"] = (f"{it.name} (Rs {it.price:.0f}) — trending on campus "
                            f"with {rmap.get(it.id, {}).get('likes', 0)} student likes.")
        out.append(c)
    return out


def _spending_for(sid: str) -> dict[str, Any]:
    rows = [r for r in _read_json_list(ORDERS_PATH) if r.get("session_id") == sid]
    today = datetime.now().date()
    week_tot, today_tot, today_n = 0.0, 0.0, 0
    per_day: dict[str, dict[str, Any]] = {}
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        per_day[d] = {"date": d, "total": 0.0, "count": 0}
    for r in rows:
        try:
            at = datetime.fromisoformat(r.get("at", ""))
        except Exception:
            continue
        day = at.date().isoformat()
        amt = _money(r)
        # week approx: last 7 calendar days by date prefix comparison
        if (today - at.date()).days <= 6:
            week_tot += amt
        if day == today.isoformat():
            today_tot += amt
            today_n += 1
        if day in per_day:
            per_day[day]["total"] = round(per_day[day]["total"] + amt, 2)
            per_day[day]["count"] += 1
    return {"today_total": round(today_tot, 2), "week_total": round(week_tot, 2),
            "today_count": today_n, "order_count": len(rows),
            "by_day": list(per_day.values())}


@app.on_event("startup")
def _startup_supabase() -> None:
    """If Supabase is configured, load the live menu from Postgres (JSON stays fallback)."""
    try:
        if db.is_configured():
            items = db.fetch_menu()
            if items:
                store.load_items(items)
    except Exception:
        pass


# ---------- helpers ----------

def _read_json_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _append_json(path: Path, row: dict) -> None:
    rows = _read_json_list(path)
    rows.append(row)
    _write_json_atomic(path, rows)


def _write_json_atomic(path: Path, rows: list) -> None:
    """Crash-safe write: temp file + atomic replace, so a crash can never
    leave a half-written order/feedback log behind."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _money(row: dict) -> float:
    """Payable amount for an order row. Tolerates legacy rows and explicit
    nulls (float(None) would otherwise 500 spending/analytics endpoints)."""
    for key in ("payable", "total"):
        v = row.get(key)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _mint_token() -> str:
    """Unique order token — the CB-100..999 space collides after ~40 orders
    (birthday paradox), and status/cancel must agree on ONE row."""
    seen = {str(r.get("token", "")).upper() for r in _read_json_list(ORDERS_PATH)}
    for _ in range(50):
        tok = f"CB-{random.randint(100, 999)}"
        if tok not in seen:
            return tok
    return f"CB-{random.randint(1000, 9999)}"  # overflow space, still unique enough


def _budget_stats() -> dict[str, Any]:
    rows = _read_json_list(FEEDBACK_PATH)
    budgets = [r.get("budget") for r in rows if isinstance(r.get("budget"), (int, float))]
    moods: dict[str, int] = {}
    for r in rows:
        m = r.get("mood")
        if m:
            moods[m] = moods.get(m, 0) + 1
    return {
        "feedback_count": len(rows),
        "avg_budget": round(sum(budgets) / len(budgets), 2) if budgets else None,
        "mood_histogram": moods,
    }


def item_card(item: MenuItem, prefs: UserPreferences, meal: Optional[str],
              score: Optional[float] = None, breakdown: Optional[dict] = None,
              pair: Optional[MenuItem] = None,
              ratings: Optional[dict[str, dict[str, int]]] = None) -> dict[str, Any]:
    expl = explain_item(item, prefs, meal, breakdown, pair)
    r = (ratings or {}).get(item.id, {"likes": 0, "dislikes": 0})
    return {
        "id": item.id, "name": item.name, "description": item.description,
        "price": item.price, "category": item.category.value, "cuisine": item.cuisine.value,
        "ingredients": item.ingredients, "allergens": [str(a).split(".")[-1] for a in item.allergens],
        "dietary_tags": [str(d).split(".")[-1] for d in item.dietary_tags],
        "availability": item.availability, "available_until": item.available_until,
        "prep_time_minutes": item.prep_time_minutes, "calories": item.calories,
        "protein_g": item.protein_g,
        "carbs_g": item.carbs_g, "sugar_g": item.sugar_g, "fiber_g": item.fiber_g,
        "likes": r["likes"], "dislikes": r["dislikes"],
        "portion_size": item.portion_size.value, "spice_level": item.spice_level,
        "taste_profile": item.taste_profile, "mood_tags": item.mood_tags,
        "serving_times": [str(s).split(".")[-1] for s in item.serving_times],
        "popularity_score": item.popularity_score,
        "is_combo": item.is_combo, "combo_items": item.combo_items,
        "score": score, "breakdown": breakdown,
        "explanation": expl,  # templated; batched AI phrasing applied by caller
        "cross_contamination_warning": cross_contamination_warning(item, prefs),
    }


def apply_ai_phrasing(cards: list[dict]) -> str:
    """One-model-call phrasing for a batch of cards. Returns model or rule-based.
    Facts (name + price + prep minutes) travel along so a paraphrase that drops
    them falls back per-card instead of shipping altered facts."""
    texts = [c.get("explanation") or "" for c in cards]
    if not any(texts):
        return "rule-based"
    facts = [{"name": c.get("name"), "price": c.get("total_price", c.get("price")),
              "prep": c.get("eta", c.get("prep_time_minutes"))}
             for c in cards]
    out, model = batch_phrase(texts, facts)
    for c, t in zip(cards, out):
        c["explanation"] = t
    return model


def result_payload(res: dict, prefs: UserPreferences) -> dict[str, Any]:
    meal = res["meal"]
    rmap = rating_stats()
    singles = [item_card(it, res["prefs"], meal, sc, br, ratings=rmap)
               for it, sc, br in res["singles"]]
    combos = []
    for c in res["combos"]:
        if c.get("is_dynamic"):
            items = c["items"]
            total = c["total_price"]
            expl = (f"{c['name']} (Rs {total:.0f}, ~{c['eta']} min) — both parts fit your "
                    f"Rs {(res['prefs'].budget or total):.0f} budget as a combo.")
            tags = sorted({t for i in items for t in
                           [str(d).split('.')[-1] for d in i.dietary_tags]})
            # A meat + veg mix is non-veg overall; keep the strictest honest label.
            if "non_veg" in tags:
                tags = ["non_veg" if t in ("veg", "vegan", "jain", "egg") else t for t in tags]
                tags = sorted(set(tags) - {"veg", "vegan", "jain", "egg"})
            portion_rank = {"light": 0, "medium": 1, "heavy": 2, "filling": 3}
            combos.append({
                "is_dynamic": True, "name": c["name"],
                "id": c.get("id", "dyn_" + "__".join(i.id for i in items)),
                "description": "Chef-paired combo: " + " + ".join(i.name for i in items),
                "item_ids": [i.id for i in items],
                "items": [item_card(i, res["prefs"], meal, ratings=rmap) for i in items],
                "total_price": total, "eta": c["eta"], "score": c["score"],
                "calories": sum(i.calories for i in items),
                "protein_g": sum(i.protein_g for i in items),
                "spice_level": max([i.spice_level for i in items] + [0]),
                "dietary_tags": tags,
                "allergens": sorted({str(a).split('.')[-1] for i in items for a in i.allergens}),
                "portion_size": max([i.portion_size.value for i in items],
                                    key=lambda p: portion_rank.get(p, 0)),
                "availability": True,
                "explanation": expl,  # batched AI phrasing applied below
            })
        else:
            it = c["item"]
            combos.append({
                "is_dynamic": False, **item_card(it, res["prefs"], meal, c["score"], c.get("breakdown"), ratings=rmap),
                "total_price": c["total_price"], "eta": c["eta"],
            })
    return {
        "meal": meal, "prefs": res["prefs"].model_dump(),
        "singles": singles, "combos": combos,
        "relaxed": res["relaxed"], "cheapest_note": res.get("cheapest_note"),
        "cheapest": [item_card(i, res["prefs"], meal, ratings=rmap) for i in res.get("cheapest", [])],
        "conflict": res.get("conflict"),
        "ai_phrase": apply_ai_phrasing(singles + combos),
    }


def find_named_item(text: str) -> Optional[MenuItem]:
    t = text.lower()
    flat = re.sub(r"[^a-z]", "", t)  # "gulabjamun" still matches "Gulab Jamun"
    best = None
    for it in store.all():
        name = it.name.lower()
        slug = it.id.replace("_", " ")
        if name in t or slug in t:
            hit = True
        else:
            # Spaceless fallback on alpha words only ("(2 pc)" suffixes are
            # dropped so "gulabjamun" matches "Gulab Jamun (2 pc)"). Only
            # multi-letter runs count — single common words ("masala") must
            # not hijack generic queries like "something masala".
            words = [w for w in re.sub(r"[^a-z ]", " ", name).split() if len(w) > 1]
            keys = {"".join(words), "".join(words[:2])} if words else set()
            hit = bool(keys) and any(k in flat for k in keys if len(k) > 3)
        if hit and (best is None or len(it.name) > len(best.name)):
            best = it
    return best


def greeting_for(meal: str) -> str:
    if meal == "breakfast":
        return "Good morning! Breakfast items are being served."
    if meal == "lunch":
        return "Good afternoon! Lunch service is on."
    return "Good evening! Dinner options are live."


def greeting_recommendations(
    mem: dict, sid: str, meal: str, prefs: UserPreferences
) -> tuple[str, list[dict], list[str]]:
    """Build opening recommendations based on previous orders or top campus favorites to give it a try."""
    live_items = store.live()
    if not live_items:
        live_items = store.all()
    live_map = {it.id: it for it in live_items}
    rmap = rating_stats()
    # Health-critical: a returning diabetic must never be greeted with syrupy
    # bestsellers — rank fit-tier items first (phrases asserted by tests stay).
    dia = ((mem.get("profile") or {}).get("goal") or "") == "diabetic"

    def _pop_key(i):
        base = ((rmap.get(i.id, {}).get("likes", 0) - rmap.get(i.id, {}).get("dislikes", 0)),
                i.popularity_score, -i.prep_time_minutes)
        # reverse=True sorts larger first, so fit maps to 0, others to -1.
        return ((0 if diabetic_fit(i) else -1),) + base if dia else base

    # Identify past orders from session memory and order history
    ordered_ids = list((mem.get("orders") or {}).keys())
    if not ordered_ids and sid:
        session_rows = _session_orders(sid)
        for r in session_rows:
            for raw_id in _expand_tray(r.get("tray", [])):
                if raw_id not in ordered_ids:
                    ordered_ids.append(raw_id)

    prev_items = [store.get(iid) for iid in ordered_ids if store.get(iid)]
    chosen: list[tuple[MenuItem, str]] = []

    if prev_items:
        past_cuisines = [p.cuisine.value for p in prev_items if hasattr(p, "cuisine")]
        past_ids = {p.id for p in prev_items}
        fav_cuisine = max(set(past_cuisines), key=past_cuisines.count) if past_cuisines else None

        # Recommend un-ordered dishes in favorite cuisine or chef pairing
        candidates = [
            it for it in live_items
            if it.id not in past_ids and (fav_cuisine is None or it.cuisine.value == fav_cuisine)
        ]
        candidates.sort(
            key=_pop_key,
            reverse=True
        )

        if candidates:
            try_dish = candidates[0]
            chosen.append((
                try_dish,
                f"Chef recommendation to give it a try based on your past orders — freshly made and ready in ~{try_dish.prep_time_minutes} mins!"
            ))
            if len(candidates) > 1:
                chosen.append((
                    candidates[1],
                    f"Top-rated {candidates[1].cuisine.value.replace('_', ' ').title()} bite live right now — pairs well with your taste!"
                ))

        # Include past favorite if currently live
        past_live = [p for p in prev_items if p.id in live_map]
        if past_live and len(chosen) < 3:
            fav_live = past_live[0]
            order_cnt = (mem.get("orders") or {}).get(fav_live.id, 1)
            chosen.append((
                fav_live,
                f"Your familiar campus favorite (ordered {order_cnt}x) — hot and ready!"
            ))

        if len(chosen) < 2:
            remaining = [it for it in live_items if it.id not in {c[0].id for c in chosen}]
            remaining.sort(key=lambda i: i.popularity_score, reverse=True)
            for it in remaining[:(3 - len(chosen))]:
                chosen.append((it, "Campus canteen bestseller live right now to give it a try!"))

        prev_names_str = " & ".join([p.name for p in prev_items[:2]])
        reply = (
            f"Welcome back to biteMatch! Based on your previous orders of {prev_names_str}, "
            f"here are the best picks live right now in the canteen to give it a try today:"
        )
        if dia:
            reply += " Picked with your diabetes in mind."
        chips = ["Reorder my usual", "Under Rs 50", "Show combos", "Something spicy", "In a hurry"]
    else:
        # First-time or fresh visitor: Recommend best available dishes live
        meal_picks = [i for i in live_items if any(s.value in (meal, "all_day") for s in i.serving_times)]
        if not meal_picks:
            meal_picks = live_items
        meal_picks.sort(
            key=_pop_key,
            reverse=True
        )

        top3 = meal_picks[:3]
        explanations = [
            "⭐ Chef's Top Special today — best available dish in the kitchen to give it a try!",
            "🔥 Campus Bestseller — highly rated by students, ready in ~8 mins!",
            "⚡ Quick Study Snack — great value, freshly prepared, and under Rs 60!"
        ]
        for it, exp in zip(top3, explanations):
            chosen.append((it, exp))

        reply = (
            f"{greeting_for(meal)} To get you started, here are today's top campus favorites live right now to give it a try "
            f"— or tell me your budget and craving:"
        )
        if dia:
            reply += " (Picked with your diabetes in mind.)"
        chips = ["Under Rs 50", "Rs 70, spicy veg, 10 mins", "Show combos", "Vegan", "In a hurry"]

    cards = []
    for it, exp in chosen:
        c = item_card(it, prefs, meal, score=96.0, ratings=rmap)
        c["explanation"] = exp
        cards.append(c)

    return reply, cards, chips


def ai_label() -> str:
    return "openrouter-chain" if openrouter_available() else "rule-based"


def recommend_headline(prefs: UserPreferences, meal: str, n: int) -> str:
    """Warm one-liner summarizing what the picks satisfy: budget, time, craving."""
    bits = []
    if prefs.budget is not None:
        bits.append(f"under Rs {prefs.budget:.0f}")
    if prefs.max_prep_time is not None:
        bits.append(f"ready in ~{prefs.max_prep_time} min")
    if (prefs.goal or "") == "high_protein":
        bits.append("high-protein")
    elif (prefs.goal or "") == "low_calorie":
        bits.append("light")
    elif (prefs.goal or "") == "diabetic":
        bits.append("diabetic-friendly")
    if prefs.cravings:
        bits.append(" + ".join(prefs.cravings[:2]))
    suffix = f" ({', '.join(bits)})" if bits else ""
    variants = [
        f"Here are my top {n} picks for {meal}{suffix}:",
        f"I found {n} great options for {meal}{suffix}:",
        f"Top {n} for {meal}{suffix} — fresh from the live menu:",
    ]
    # Deterministic daily rotation: same answer all day (cache/test friendly),
    # fresher wording across days. Suffix (budget/time/goal) is identical.
    return variants[datetime.now().date().toordinal() % len(variants)]


_ratings_cache: dict[str, Any] = {"key": None, "map": {}}


def rating_stats() -> dict[str, dict[str, int]]:
    """Aggregate feedback likes/dislikes per item (mtime+size-cached file read)."""
    try:
        st = FEEDBACK_PATH.stat() if FEEDBACK_PATH.exists() else None
        key = (st.st_mtime, st.st_size) if st else 0
    except Exception:
        key = 0
    if _ratings_cache["key"] == key:
        return _ratings_cache["map"]
    agg: dict[str, dict[str, int]] = {}
    for row in _read_json_list(FEEDBACK_PATH):
        iid = row.get("item_id")
        if not iid:
            continue
        cell = agg.setdefault(iid, {"likes": 0, "dislikes": 0})
        if (row.get("rating") or 0) > 0:
            cell["likes"] += 1
        elif (row.get("rating") or 0) < 0:
            cell["dislikes"] += 1
    _ratings_cache.update({"key": key, "map": agg})
    return agg


def queue_note(queues: dict[str, int]) -> Optional[str]:
    heavy = [(n, m) for n, m in queues.items() if m >= 8]
    if not heavy:
        return None
    heavy.sort(key=lambda t: t[1], reverse=True)
    name, mins = heavy[0]
    label = qmod.COUNTERS[name]["label"]
    return (f"Live queues add ~{mins} min at the {label} — "
            "picks below already route around it where possible.")


HEALTH_NOTE = ("Note: I'm a canteen recommender, not a doctor — these are "
               "lower-sugar picks from the live menu, not medical advice. "
               "When in doubt, check with your doctor.")


def chips_for_goal(prefs: UserPreferences) -> list[str]:
    """Goal-aware quick replies — every chip maps to a working refinement."""
    goal = (prefs.goal or "").lower()
    if goal == "diabetic":
        return ["High-protein", "More filling", "Quicker", "Show combos", "No onion/garlic"]
    if goal == "high_protein":
        return ["More filling", "Something cheaper", "Quicker", "Show combos"]
    if goal == "low_calorie":
        return ["Something light", "Something cheaper", "Quicker", "Show combos"]
    return ["Something cheaper", "Less spicy", "More filling", "Quicker", "Show combos", "No onion/garlic"]


# ---------- schemas ----------

class RecommendBody(BaseModel):
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    meal: Optional[str] = None
    session_id: Optional[str] = None


class ChatBody(BaseModel):
    message: str = Field(..., max_length=2000)
    prefs: UserPreferences = Field(default_factory=UserPreferences)
    meal_override: Optional[str] = None
    session_id: Optional[str] = None


class TrayBody(BaseModel):
    tray_ids: list[str] = Field(default_factory=list, max_length=50)
    budget: Optional[float] = None
    coupon_code: Optional[str] = None
    session_id: Optional[str] = None


class OrderBody(BaseModel):
    tray_ids: list[str] = Field(default_factory=list, max_length=50)
    budget: Optional[float] = None
    session_id: Optional[str] = None
    coupon_code: Optional[str] = None


class FeedbackBody(BaseModel):
    item_id: str
    rating: int = Field(..., ge=-1, le=1)
    comment: Optional[str] = Field(default=None, max_length=500)
    budget: Optional[float] = None
    mood: Optional[str] = None
    session_id: Optional[str] = None


class AvailabilityBody(BaseModel):
    available: bool


class PriceBody(BaseModel):
    price: float = Field(..., ge=0)


class QueueBody(BaseModel):
    counter: str
    minutes: int = Field(..., ge=0, le=120)


class SuggestBody(BaseModel):
    tray_ids: list[str] = Field(default_factory=list)
    budget: Optional[float] = None
    prefs: UserPreferences = Field(default_factory=UserPreferences)


class FavoriteBody(BaseModel):
    item_id: str
    session_id: Optional[str] = None


class ProfileBody(BaseModel):
    session_id: Optional[str] = None
    dietary_restrictions: Optional[list[str]] = None
    allergies: Optional[list[str]] = None
    goal: Optional[str] = None
    budget: Optional[float] = None
    weekly_budget: Optional[float] = Field(default=None, ge=0)
    hunger: Optional[str] = None
    cuisine: Optional[str] = None
    max_spice: Optional[int] = None
    max_prep_time: Optional[int] = None
    no_onion_garlic: Optional[bool] = None
    health_conditions: Optional[list[str]] = None


class BillSplitBody(BaseModel):
    tray_ids: list[str] = Field(default_factory=list, max_length=50)
    people: int = Field(default=2, ge=1, le=20)
    coupon_code: Optional[str] = None


class BulkAvailabilityBody(BaseModel):
    ids: list[str] = Field(default_factory=list)
    available: bool = True


class OrderStatusBody(BaseModel):
    status: str = Field(..., description="READY | COMPLETED | CANCELLED")


# ---------- routes ----------

@app.get("/health")
def health():
    return {"ok": True, "items": len(store.all()), "live": len(store.live()), "time": datetime.now().isoformat()}


@app.get("/menu")
def list_menu(
    category: Optional[str] = None,
    cuisine: Optional[str] = None,
    max_price: Optional[float] = None,
    dietary: Optional[str] = None,
    max_spice: Optional[int] = None,
    max_prep: Optional[int] = None,
    available_only: bool = True,
    q: Optional[str] = None,
    goal: Optional[str] = None,
    exclude: Optional[str] = None,
    min_protein: Optional[float] = None,
    max_calories: Optional[float] = None,
    max_carbs: Optional[float] = None,
    max_sugar: Optional[float] = None,
):
    items = store.live() if available_only else store.all()
    # exclude=peanuts,dairy — drop dishes containing these allergens (additive filter).
    excluded: set[str] = set()
    if exclude:
        valid = {"peanuts", "tree_nuts", "dairy", "gluten", "soy", "egg", "seafood", "sesame"}
        excluded = {a.strip().lower() for a in exclude.split(",") if a.strip().lower() in valid}
    out = []
    for it in items:
        if excluded:
            item_all = {str(a).split(".")[-1].lower() for a in it.allergens}
            if item_all & excluded:
                continue
        if category and it.category.value != category:
            continue
        if cuisine and it.cuisine.value != cuisine:
            continue
        if max_price is not None and it.price > max_price:
            continue
        if max_spice is not None and it.spice_level > max_spice:
            continue
        if max_prep is not None and it.prep_time_minutes > max_prep:
            continue
        if min_protein is not None and it.protein_g < min_protein:
            continue
        if max_calories is not None and it.calories > max_calories:
            continue
        if max_carbs is not None and it.carbs_g > max_carbs:
            continue
        if max_sugar is not None and it.sugar_g > max_sugar:
            continue
        if dietary and dietary not in [str(d).split(".")[-1] for d in it.dietary_tags]:
            # 'veg' browsing should also surface vegan/jain (they are veg-safe)
            tags = {str(d).split(".")[-1] for d in it.dietary_tags}
            if dietary == "veg" and not (tags & {"veg", "vegan", "jain"}):
                continue
            elif dietary != "veg":
                continue
        if q and q.lower() not in (it.name + " " + it.description + " " + " ".join(it.ingredients)).lower():
            continue
        out.append(it)
    rmap = rating_stats()
    if goal == "high_protein":
        out = sorted(out, key=lambda i: (-i.protein_g, i.price))
    elif goal == "low_calorie":
        out = sorted(out, key=lambda i: (i.calories, i.price))
    elif goal == "diabetic":
        out = sorted(out, key=lambda i: (i.sugar_g, i.carbs_g, -i.protein_g, i.price))
    else:
        out = sorted(out, key=lambda i: (i.price, -i.popularity_score))
    return {"count": len(out), "items": [item_card(i, UserPreferences(), None, ratings=rmap) for i in out[:24]]}


@app.get("/menu/{item_id}")
def get_item(item_id: str):
    it = store.get(item_id)
    if not it:
        raise HTTPException(404, f"Unknown item '{item_id}'")
    rmap = rating_stats()
    payload = item_card(it, UserPreferences(), None, ratings=rmap)
    if not it.availability:
        subs = substitutes_for(it, store.all(), UserPreferences(), None, n=3)
        payload["alternatives"] = [item_card(s, UserPreferences(), None, ratings=rmap) for s in subs]
        payload["sold_out_note"] = (
            f"Sorry, {it.name} is sold out today. Closest available options are listed."
        )
    return payload


@app.get("/queue")
def get_queues():
    qs = qmod.current_queues()
    return {"queues": [
        {"counter": n, "label": qmod.COUNTERS[n]["label"], "wait_minutes": m}
        for n, m in qs.items()]}


@app.get("/order/{token}")
def order_status(token: str):
    st = _order_status(token.upper())
    if not st:
        raise HTTPException(404, f"No order '{token}'")
    return st


@app.post("/recommend")
def recommend_route(body: RecommendBody):
    meal = body.meal or body.preferences.meal or infer_meal_period()
    prefs = body.preferences
    mem_note = ""
    sid = body.session_id or ""
    mem: dict = {}
    if sid:
        sid, mem = _session(sid)
        prefs = memory_store.apply_profile_defaults(mem, prefs)
        if body.preferences.goal is None and (prefs.goal or "").lower() == "diabetic":
            mem_note += "Keeping your diabetes in mind. "
        if prefs.budget is None:
            ub = memory_store.usual_budget(mem)
            if ub is not None:
                prefs = prefs.model_copy(update={"budget": ub})
                mem_note = f"Using your usual Rs {ub:.0f} budget. "
        queues = qmod.current_queues()
        res = recommend(
            store.all(), prefs, meal, queue=queues,
            rank_adjust=lambda lst: boost_singles(lst, mem, _cuisine_of()))
        qn = queue_note(queues)
        if qn:
            res["relaxed"] = [*res.get("relaxed", []), qn]
        memory_store.record_chat(mem, prefs)
        memory_store.save(sid, mem)
    else:
        res = recommend(store.all(), prefs, meal)
    out = result_payload(res, prefs)
    out["ai"] = ai_label()
    out["session_id"] = sid
    if mem_note:
        out["memory_note"] = mem_note
    if (prefs.goal or "").lower() == "diabetic":
        out["health_note"] = HEALTH_NOTE
    return out


@app.post("/chat")
def chat(body: ChatBody):
    text = (body.message or "").strip()[:2000]  # bound LLM + log payloads
    meal = body.meal_override or parse_meal(text) or body.prefs.meal or infer_meal_period()
    intent = detect_intent(text)
    sid, mem = _session(body.session_id)  # memory loads here; saved on every path below
    returning = mem.get("chats", 0) > 0
    # Menu-name mentions always route to food logic (fixes sold-out + dish cravings
    # like "Oreo Shake" / "Samosa" that keyword regexes would otherwise miss).
    _named_pre = find_named_item(text)
    if _named_pre is not None and intent in ("smalltalk", "nonsense"):
        intent = "recommend"

    if intent == "greeting":
        reply, singles, chips = greeting_recommendations(mem, sid, meal, body.prefs)
        memory_store.save(sid, mem)
        return {
            "intent": intent, "ai": ai_label(), "reply": reply, "meal": meal,
            "session_id": sid,
            "prefs": body.prefs.model_dump(),
            "chips": chips,
            "singles": singles, "combos": [],
        }

    if intent in ("smalltalk", "nonsense"):
        # Double check if any food preference or dietary constraint is present before falling back
        if (parse_goal(text) is not None
                or parse_budget(text) is not None
                or parse_cravings(text)
                or parse_hunger(text) is not None
                or parse_dietary_allergy(text)[0]
                or parse_dietary_allergy(text)[1]):
            intent = "recommend"
        elif len(text) > 3:
            _patch, _ = parse_prefs_with_llm(text)
            if _patch:
                intent = "recommend"

    if intent in ("smalltalk", "nonsense"):
        memory_store.save(sid, mem)
        return {
            "intent": intent,
            "ai": ai_label(),
            "session_id": sid,
            "reply": smalltalk_reply() if intent == "smalltalk" else nonsense_reply(),
            "meal": meal, "prefs": body.prefs.model_dump(),
            "chips": ["Under Rs 50", "Show combos", "Something light", "In a hurry"],
            "singles": [], "combos": [],
        }

    if intent == "thanks":
        memory_store.save(sid, mem)
        return {
            "intent": intent, "ai": ai_label(), "session_id": sid,
            "reply": ("You're most welcome! Enjoy your meal. Anything else — "
                      "a snack, a combo, or another round?"),
            "meal": meal, "prefs": body.prefs.model_dump(),
            "singles": [], "combos": [],
            "chips": ["Show combos", "Something sweet", "Under Rs 50"],
        }

    if intent == "exit":
        memory_store.save(sid, mem)
        return {
            "intent": intent,
            "ai": ai_label(),
            "session_id": sid,
            "reply": "Thanks for stopping by CampusBite! Your tray and feedback are saved. Come hungry next time.",
            "meal": meal, "prefs": body.prefs.model_dump(), "singles": [], "combos": [],
        }

    if intent == "browse":
        # "What do you have under Rs 50?" / "Show all veg snacks"
        probe = parse_one_shot(text, body.prefs)
        items = store.live()
        if probe.budget is not None:
            items = [i for i in items if i.price <= probe.budget]
        if probe.dietary_restrictions:
            from backend.recommender import passes_dietary as _pd
            tmp = UserPreferences(dietary_restrictions=probe.dietary_restrictions,
                                  allergies=probe.allergies, no_onion_garlic=probe.no_onion_garlic)
            items = [i for i in items if _pd(i, tmp)]
        # category hint
        tl = text.lower()
        for cat in ["breakfast", "main_course", "snack", "beverage", "dessert", "combo"]:
            if cat.replace("_", " ") in tl or cat in tl:
                items = [i for i in items if i.category.value == cat]
                break
        # Rank the list by the user's goal when one is stated (protein first,
        # sugar first, light first) — otherwise cheapest first.
        _goal = (probe.goal or "").lower()
        if _goal == "high_protein":
            items = sorted(items, key=lambda i: (-i.protein_g, i.price))[:12]
        elif _goal == "low_calorie":
            items = sorted(items, key=lambda i: (i.calories, i.price))[:12]
        elif _goal == "diabetic":
            items = sorted(items, key=lambda i: (i.sugar_g, i.carbs_g, i.price))[:12]
        else:
            items = sorted(items, key=lambda i: (i.price, -i.popularity_score))[:12]
        lines = [f"{i.name} — Rs {i.price:.0f} (~{i.prep_time_minutes} min)" for i in items]
        head = f"Here are {len(items)} options"
        if probe.budget is not None:
            head += f" under Rs {probe.budget:.0f}"
        browse_cards = [item_card(i, probe, meal) for i in items[:6]]
        browse_ai = apply_ai_phrasing(browse_cards)
        memory_store.record_chat(mem, probe)
        memory_store.save(sid, mem)
        browse_head = head + ":\n" + "\n".join(lines) if lines else \
            "No matches for that browse — try raising the budget or clearing a filter."
        if (probe.goal or "").lower() == "diabetic":
            browse_head += f" {HEALTH_NOTE}"
        return {
            "intent": intent, "ai": browse_ai, "reply": browse_head,
            "meal": meal, "session_id": sid, "prefs": probe.model_dump(),
            "singles": browse_cards, "combos": [],
            "chips": ["Something cheaper", "Show combos", "In a hurry"],
        }

    if intent == "refine":
        new_prefs, note = apply_refinement(text, body.prefs)
        # preserve meal context
        queues = qmod.current_queues()
        res = recommend(
            store.all(), new_prefs, meal, queue=queues,
            rank_adjust=lambda lst: boost_singles(lst, mem, _cuisine_of()))
        qn = queue_note(queues)
        if qn:
            res["relaxed"] = [*res.get("relaxed", []), qn]
        memory_store.record_chat(mem, new_prefs)
        memory_store.save(sid, mem)
        payload = result_payload(res, new_prefs)
        reply_note = note + " Here are the updated picks."
        if (new_prefs.goal or "").lower() == "diabetic":
            reply_note += f" {HEALTH_NOTE}"
        payload.update({
            "intent": intent,
            "ai": payload.pop("ai_phrase", "rule-based"),
            "session_id": sid,
            "reply": reply_note,
            "chips": chips_for_goal(new_prefs),
        })
        return payload

    if intent in ("tray", "order"):
        memory_store.save(sid, mem)
        return {
            "intent": intent,
            "ai": ai_label(),
            "session_id": sid,
            "reply": "Use the tray panel: add cards with ADD, then validate against your budget. ETA is the max prep time of parallel items.",
            "meal": meal, "prefs": body.prefs.model_dump(), "singles": [], "combos": [],
        }

    if intent == "orders":
        memory_store.save(sid, mem)
        mine = _session_orders(sid)[:5]
        if not mine:
            return {"intent": intent, "ai": ai_label(), "session_id": sid,
                    "reply": "No orders on this session yet. Build a tray with ADD, confirm, then ask 'my orders' to see history.",
                    "meal": meal, "prefs": body.prefs.model_dump(),
                    "singles": [], "combos": [], "chips": ["Under Rs 50", "Show combos"]}
        lines = []
        for o in mine:
            st = _order_status(o.get("token", ""))
            lines.append(f"{o.get('token')} · Rs {_money(o):.0f} · {(st['state'] if st else '?')}")
        return {"intent": intent, "ai": ai_label(), "session_id": sid,
                "reply": "Your recent orders: " + "; ".join(lines) + ". Ask 'where is my order CB-123?' for live status, or 'repeat last order' to reorder.",
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": [], "combos": [], "orders": mine,
                "chips": ["Repeat last order", "Show combos"]}

    if intent == "cancel_order":
        m = re.search(r"cb-\d+", text.lower())
        tok = m.group(0).upper() if m else None
        if tok is None:
            mine = _session_orders(sid)
            tok = mine[0]["token"] if mine else None
        memory_store.save(sid, mem)
        if tok is None:
            return {"intent": intent, "ai": ai_label(), "session_id": sid,
                    "reply": "No orders on this session to cancel.",
                    "meal": meal, "prefs": body.prefs.model_dump(), "singles": [], "combos": []}
        try:
            res_c = _cancel_order_row(tok)
            return {"intent": intent, "ai": ai_label(), "session_id": sid,
                    "reply": f"Order {res_c['token']} cancelled. No pickup needed.",
                    "meal": meal, "prefs": body.prefs.model_dump(),
                    "singles": [], "combos": []}
        except HTTPException as e:
            return {"intent": intent, "ai": ai_label(), "session_id": sid,
                    "reply": str(e.detail),
                    "meal": meal, "prefs": body.prefs.model_dump(), "singles": [], "combos": []}

    if intent == "favorites":
        memory_store.save(sid, mem)
        favs = [f for f in (mem.get("favorites") or []) if store.get(f)]
        rmap = rating_stats()
        cards = [item_card(store.get(f), body.prefs, meal, ratings=rmap) for f in favs]
        msg = ("Your saved favorites: " + ", ".join(c["name"] for c in cards)) if cards \
            else "No favorites saved yet — tap the heart on any dish to save it here."
        return {"intent": intent, "ai": ai_label(), "session_id": sid, "reply": msg,
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": cards, "combos": [], "chips": ["Trending now", "Show combos"]}

    if intent == "spending":
        memory_store.save(sid, mem)
        sp = _spending_for(sid)
        return {"intent": intent, "ai": ai_label(), "session_id": sid,
                "reply": (f"Today: Rs {sp['today_total']:.0f} across {sp['today_count']} orders. "
                          f"Last 7 days: Rs {sp['week_total']:.0f} across {sp['order_count']} orders."),
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": [], "combos": [], "spending": sp,
                "chips": ["My orders", "Under Rs 50"]}

    if intent == "trending":
        memory_store.save(sid, mem)
        cards = _trending_items(5)
        names = ", ".join(c["name"] for c in cards)
        return {"intent": intent, "ai": ai_label(), "session_id": sid,
                "reply": f"Trending on campus right now: {names}. Tap ADD to build your tray.",
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": cards, "combos": [], "chips": ["Under Rs 100", "Show combos"]}

    if intent == "coupon":
        memory_store.save(sid, mem)
        codes = ", ".join(f"{k} ({int(v*100)}% off)" for k, v in COUPONS.items())
        return {"intent": intent, "ai": ai_label(), "session_id": sid,
                "reply": (f"Active campus coupons: {codes}. Add one in the tray coupon box "
                          "before confirming — e.g. STUDENT10 saves 10% instantly."),
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": [], "combos": [], "coupons": codes,
                "chips": ["Under Rs 100", "Show combos"]}

    if intent == "profile":
        memory_store.save(sid, mem)
        prof = memory_store.get_profile(mem)
        if prof:
            bits = []
            if prof.get("dietary_restrictions"):
                bits.append("diet " + "/".join(prof["dietary_restrictions"]))
            if prof.get("goal"):
                bits.append("goal " + str(prof["goal"]))
            if prof.get("budget"):
                bits.append(f"budget Rs {float(prof['budget']):.0f}")
            summary = ", ".join(bits) if bits else "saved"
            msg = (f"Your saved defaults ({summary}) apply automatically when you don't restate them. "
                   "Update anytime from the Profile panel.")
        else:
            msg = ("No dietary defaults saved yet. Open the Profile panel to save diet, allergies, "
                   "goal and usual budget — I'll apply them automatically.")
        return {"intent": intent, "ai": ai_label(), "session_id": sid, "reply": msg,
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": [], "combos": [], "profile": prof,
                "chips": ["Trending now", "Under Rs 50"]}

    if intent == "split":
        memory_store.save(sid, mem)
        return {"intent": intent, "ai": ai_label(), "session_id": sid,
                "reply": ("To split the bill, open your tray and use SPLIT BILL — "
                          "enter headcount and an optional coupon for per-person shares."),
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": [], "combos": [], "chips": ["My orders", "Show combos"]}

    if intent == "special":
        memory_store.save(sid, mem)
        day = datetime.now().date().isoformat()
        import hashlib as _hl
        live = store.live() or store.all()
        rmap_sp = rating_stats()

        def _day_score(it) -> float:
            h = int(_hl.md5(f"{day}:{it.id}".encode()).hexdigest()[:8], 16) % 20
            lk = rmap_sp.get(it.id, {}).get("likes", 0) - rmap_sp.get(it.id, {}).get("dislikes", 0)
            return it.popularity_score + lk * 2 + h

        picks = sorted(live, key=_day_score, reverse=True)[:3]
        cards = []
        for it in picks:
            c = item_card(it, body.prefs, meal, ratings=rmap_sp)
            c["explanation"] = (f"Today's special: {it.name} (Rs {it.price:.0f}) — "
                                "highlighted today only, tap ADD before it sells out!")
            cards.append(c)
        return {"intent": intent, "ai": ai_label(), "session_id": sid,
                "reply": "Today's specials: " + ", ".join(c["name"] for c in cards) + ".",
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": cards, "combos": [], "chips": ["Surprise me", "Under Rs 100"]}

    if intent == "surprise":
        prefs_sur = memory_store.apply_profile_defaults(mem, parse_one_shot(text, body.prefs))
        res_sur = recommend(
            store.all(), prefs_sur, meal, queue=qmod.current_queues(),
            rank_adjust=lambda lst: boost_singles(lst, mem, _cuisine_of()))
        memory_store.record_chat(mem, prefs_sur)
        memory_store.save(sid, mem)
        pool = [s for s in res_sur["singles"]] or []
        pick = random.choice(pool) if pool else None
        cards = []
        if pick is not None:
            it, sc, br = pick
            c = item_card(it, prefs_sur, meal, sc, br, ratings=rating_stats())
            c["explanation"] = (f"Feeling lucky? {it.name} (Rs {it.price:.0f}) chose YOU — "
                                "a surprise pick that still respects your budget and diet.")
            cards = [c]
        return {"intent": intent, "ai": ai_label(), "session_id": sid,
                "reply": ("Your surprise pick is ready!" if cards
                          else "No safe surprise right now — try 'Show all veg snacks' to browse."),
                "meal": meal, "prefs": prefs_sur.model_dump(),
                "singles": cards, "combos": [], "chips": ["Something else", "Show combos"]}

    if intent == "feedback":
        memory_store.save(sid, mem)
        return {
            "intent": intent,
            "ai": ai_label(),
            "session_id": sid,
            "reply": "Tap thumbs up/down on any card — it logs feedback and tunes popularity. Thanks!",
            "meal": meal, "prefs": body.prefs.model_dump(), "singles": [], "combos": [],
        }

    if intent == "status":
        memory_store.save(sid, mem)
        m = re.search(r"cb-\d+", text.lower())
        st = _order_status(m.group(0)) if m else None
        if st is None:
            mine = _session_orders(sid)
            st = _order_status(mine[0]["token"]) if mine else None
        if st is None:
            return {
                "intent": intent, "ai": ai_label(), "session_id": sid,
                "reply": ("No orders on this session yet. Add cards with ADD, "
                          "confirm, then ask 'where is my order?'."),
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": [], "combos": [],
                "chips": ["Under Rs 50", "Show combos"],
            }
        return {
            "intent": intent, "ai": ai_label(), "session_id": sid,
            "reply": (f"Token {st['token']} · {', '.join(st['items'])} · "
                      f"Rs {float(st.get('payable', st.get('total')) or 0):.0f} — {st['state']}. {st['detail']}"),
            "meal": meal, "prefs": body.prefs.model_dump(),
            "singles": [], "combos": [], "order": st,
            "chips": ["Show combos", "Something else"],
        }

    if intent == "reorder":
        memory_store.save(sid, mem)
        mine = _session_orders(sid)
        if not mine:
            return {
                "intent": intent, "ai": ai_label(), "session_id": sid,
                "reply": ("No past orders on this session yet — order once and "
                          "'repeat last order' will rebuild it in one tap."),
                "meal": meal, "prefs": body.prefs.model_dump(),
                "singles": [], "combos": [],
                "chips": ["Under Rs 50", "Show combos"],
            }
        last = mine[0]
        ids = _expand_tray(last.get("tray", []))
        live_ids = [i for i in ids if store.get(i) and store.get(i).availability]
        off = [store.get(i).name for i in ids if not (store.get(i) and store.get(i).availability)]
        rmap = rating_stats()
        cards = [item_card(store.get(i), body.prefs, meal, ratings=rmap) for i in live_ids]
        apply_ai_phrasing(cards)
        total = round(sum(store.get(i).price for i in live_ids), 2)
        tail = f" Skip now unavailable: {', '.join(off)}." if off else ""
        return {
            "intent": intent, "ai": ai_label(), "session_id": sid,
            "reply": (f"Your last order ({last.get('token')}, Rs {float(last.get('total') or 0):.0f}): "
                      f"{', '.join(store.get(i).name for i in live_ids)}. "
                      f"Rebuild total Rs {total:.0f}.{tail} Tap ADD ALL for one-tap reorder."),
            "meal": meal, "prefs": body.prefs.model_dump(),
            "singles": cards, "combos": [], "quick_add": live_ids,
            "chips": ["Show combos", "Something else"],
        }

    if intent == "suggest":
        memory_store.save(sid, mem)
        return {
            "intent": intent, "ai": ai_label(), "session_id": sid,
            "reply": ("Tell me what's already in your tray plus your budget "
                      "(e.g. 'dosa Rs 60, budget Rs 100'), or tap COMPLETE MY MEAL "
                      "under your tray — I'll fill the remaining budget with the best sides."),
            "meal": meal, "prefs": body.prefs.model_dump(),
            "singles": [], "combos": [],
            "chips": ["Show combos", "Under Rs 100"],
        }

    # intent == recommend (default): check sold-out named item first
    named = find_named_item(text)
    if named and not named.availability:
        subs = substitutes_for(named, store.all(), parse_one_shot(text, body.prefs), meal, n=3)
        sub_cards = [item_card(s, body.prefs, meal) for s in subs]
        sub_ai = apply_ai_phrasing(sub_cards)
        memory_store.record_chat(mem, body.prefs)
        memory_store.save(sid, mem)
        return {
            "intent": "sold_out",
            "ai": sub_ai,
            "session_id": sid,
            "reply": (f"Sorry, {named.name} is sold out today. "
                      f"Closest available options: {', '.join(s.name for s in subs)}."),
            "meal": meal, "prefs": body.prefs.model_dump(),
            "singles": sub_cards, "combos": [],
            "sold_out_item": named.id,
            "chips": ["Something cheaper", "Show combos", "Something else"],
        }

    # ---- health memory: persist what THIS message states (diet/allergy/goal/
    # ---- condition) into the profile + DB, so next visits auto-respect it.
    fresh = parse_one_shot(text)
    stated_goal = fresh.goal
    stated_diet = list(fresh.dietary_restrictions)
    stated_allergies = [str(a).split(".")[-1].lower() for a in fresh.allergies]
    stated_conds = parse_health_conditions(text)
    new_conds: list[str] = []
    if stated_goal or stated_diet or stated_allergies or stated_conds:
        new_conds = memory_store.record_health(
            mem, {"goal": stated_goal, "dietary": stated_diet,
                  "allergies": stated_allergies, "conditions": stated_conds})

    # ---- counter-to-self redirect: diabetic asks for a sugary dish by name.
    # ---- First time -> caring redirect + better options; insisted -> respect
    # ---- autonomy and recommend normally (honest tier labels still apply).
    eff_goal = stated_goal or body.prefs.goal or (mem.get("profile") or {}).get("goal")
    if (named and named.availability and (eff_goal or "").lower() == "diabetic"
            and not diabetic_fit(named)):
        if not memory_store.was_warned(mem, named.id):
            memory_store.mark_warned(mem, named.id)
            memory_store.record_chat(mem, body.prefs)
            memory_store.save(sid, mem)
            gprefs = body.prefs.model_copy(update={"goal": "diabetic"})
            subs = substitutes_for(named, store.all(), gprefs, meal, n=10)
            # Keep only fit/watch tiers — an "avoid" item is never a "better option".
            ok = [s for s in subs if diabetic_score(s)[0] > -10]
            if len(ok) < 2:
                # Fall back to the lowest-sugar live dishes within budget.
                pool = [i for i in store.live() if not i.is_combo and diabetic_fit(i)]
                if gprefs.budget is not None:
                    pool = [i for i in pool if i.price <= gprefs.budget + 1e-9]
                seen = {s.id for s in ok}
                ok += [i for i in pool if i.id not in seen]
            subs = sorted(ok, key=lambda s: (0 if diabetic_fit(s) else 1,
                                             s.sugar_g, s.carbs_g, s.price))[:3]
            rmap_h = rating_stats()
            alt_cards = [item_card(s, gprefs, meal, ratings=rmap_h) for s in subs]
            # Deliberately NO AI phrasing here: health-critical wording
            # ("isn't a great pick", gram counts) must stay verbatim.
            return {
                "intent": "health_redirect",
                "ai": ai_label(),
                "session_id": sid,
                "reply": (f"Since you're managing diabetes, {named.name} "
                          f"({named.sugar_g}g sugar, {named.carbs_g}g carbs) isn't a great "
                          f"pick — it can spike blood sugar. Here are closer options "
                          f"you'll still enjoy: {', '.join(s.name for s in subs)}. {HEALTH_NOTE}"),
                "meal": meal, "prefs": gprefs.model_dump(),
                "singles": alt_cards, "combos": [],
                "redirected_from": named.id,
                "chips": ["Show combos", "Surprise me", "Something else"],
            }

    prefs = parse_one_shot(text, body.prefs)
    # AI gap-fill: rule-based parsing found nothing new -> one OpenRouter pass
    # (strictly validated; rule-based values always win ties). Engine still
    # decides every recommendation from real menu data.
    parse_used = ""
    if prefs.model_dump() == body.prefs.model_dump() and len(text) > 3:
        patch, used = parse_prefs_with_llm(text)
        if patch:
            prefs = merge_llm_patch(prefs, patch)
            parse_used = used
    # "something else" with no new constraints -> shuffle via refinement path
    if text.strip().lower() in ("something else", "another", "other", "different"):
        prefs, _ = apply_refinement("something else", prefs)
    # Saved profile defaults fill gaps the user didn't restate; then usual-budget.
    prefs = memory_store.apply_profile_defaults(mem, prefs)
    mem_note = ""
    if new_conds:
        mem_note += f"Noted — I'll remember your {', '.join(new_conds)} for next time. "
    elif (body.prefs.goal is None and stated_goal is None
            and (prefs.goal or "").lower() == "diabetic"):
        mem_note += "Keeping your diabetes in mind. "
    new_avoid = [a for a in (fresh.avoid or []) if a not in (body.prefs.avoid or [])]
    if new_avoid:
        mem_note += f"Skipping {', '.join(new_avoid)} as asked. "
    if prefs.budget is None:
        ub = memory_store.usual_budget(mem)
        if ub is not None:
            prefs = prefs.model_copy(update={"budget": ub})
            mem_note = f"Using your usual Rs {ub:.0f} budget. "
    res = recommend(
        store.all(), prefs, meal, queue=qmod.current_queues(),
        rank_adjust=lambda lst: boost_singles(lst, mem, _cuisine_of()))
    memory_store.record_chat(mem, prefs)
    memory_store.save(sid, mem)
    payload = result_payload(res, prefs)
    qs = clarifying_questions(prefs)
    # Never interrogate: recommend AND ask at most one follow-up inline.
    follow = f" ({qs[0]})" if qs and not (prefs.budget is not None and prefs.max_prep_time is not None) else ""
    head_bits = []
    if res.get("conflict"):
        head_bits.append(res["conflict"])
    for r_ in res.get("relaxed", []):
        head_bits.append(r_)
    if res.get("cheapest_note"):
        head_bits.append(res["cheapest_note"])
    if not (payload["singles"] or payload["combos"]):
        head = " ".join(head_bits) + " No safe matches right now — try 'Show all veg snacks' to browse." if head_bits else "No safe matches right now."
    else:
        n = len(payload["singles"]) + len(payload["combos"])
        auto = recommend_headline(prefs, meal, n)
        head = " ".join(head_bits + [auto]) if head_bits else auto
    if (prefs.goal or "").lower() == "diabetic":
        head = f"{head} {HEALTH_NOTE}"
    payload.update({
        "intent": "recommend",
        "ai": parse_used or payload.pop("ai_phrase", "rule-based"),
        "session_id": sid,
        "reply": (mem_note + head + follow).strip(),
        "chips": chips_for_goal(prefs),
    })
    return payload


@app.post("/tray/validate")
def tray_validate(body: TrayBody):
    # Dynamic combo ids (dyn_a__b) are virtual — validate their parts, not
    # the virtual id itself (it is not a menu item and must not 404).
    for raw in body.tray_ids:
        if raw.startswith("dyn_"):
            parts = raw[4:].split("__")
            if len(parts) != 2 or not all(store.get(p) for p in parts):
                raise HTTPException(404, f"Unknown combo '{raw}'")
        elif not store.get(raw):
            raise HTTPException(404, f"Unknown item '{raw}'")
    expanded: list[MenuItem] = []
    for raw in body.tray_ids:
        if raw.startswith("dyn_"):
            try:
                _, rest = raw.split("dyn_", 1)
                a, b = rest.split("__", 1)
                for pid in (a, b):
                    it = store.get(pid)
                    if it:
                        expanded.append(it)
            except ValueError:
                pass
        else:
            it = store.get(raw)
            if it:
                expanded.append(it)
    total = round(sum(i.price for i in expanded), 2)
    queues = qmod.current_queues()
    eff = [effective_prep_time(i, queues) for i in expanded]
    eta = max(eff, default=0)
    cp = _apply_coupon(total, body.coupon_code)
    payable = cp["payable"]
    if (cp["coupon"] == "FIRSTORDER" and not cp["coupon_error"]
            and body.session_id):
        _, mem_v = _session(body.session_id)
        if "FIRSTORDER" in (mem_v.get("coupons_used") or []):
            cp = {"coupon": None, "discount": 0.0, "payable": round(total, 2),
                  "coupon_error": "FIRSTORDER was already used on this account — full total applies."}
            payable = cp["payable"]
    # Budget check on the payable amount when a valid coupon is applied,
    # otherwise on the raw total (identical when no coupon is sent).
    check_amt = payable if cp["coupon"] and not cp["coupon_error"] else total
    over = body.budget is not None and check_amt > body.budget
    off = [i.name for i in expanded if not i.availability]
    return {
        "count": len(expanded), "total": total, "budget": body.budget,
        "over_budget": over, "over_by": round(check_amt - body.budget, 2) if over else 0.0,
        "eta_minutes": eta, "queue_minutes": queues,
        "unavailable": off,
        "coupon": cp["coupon"], "discount": cp["discount"], "payable": payable,
        "coupon_error": cp["coupon_error"],
        "coupons_available": sorted(COUPONS.keys()),
        "warning": (f"Over budget by Rs {check_amt - body.budget:.0f}. Remove an item or say 'something cheaper'."
                    if over else None),
    }


@app.post("/tray/suggest")
def tray_suggest(body: SuggestBody):
    """Complete-my-meal: best sides that fit the tray's REMAINING budget."""
    if body.budget is None:
        raise HTTPException(400, "Set a budget first (e.g. 'my budget is Rs 100').")
    expanded = [store.get(i) for i in _expand_tray(body.tray_ids)]
    expanded = [i for i in expanded if i]
    spent = round(sum(i.price for i in expanded), 2)
    remaining = round(body.budget - spent, 2)
    if remaining <= 0:
        return {"spent": spent, "budget": body.budget, "remaining": remaining,
                "suggestions": [], "note": "Tray already fills the budget."}
    prefs = body.prefs.model_copy(update={"budget": remaining})
    pool = [i for i in store.live()
            if not i.is_combo
            and i.category.value in ("beverage", "snack", "dessert")
            and i.price <= remaining + 1e-9]
    # hard dietary/allergen safety + serving + spice; time checked with queues
    queues = qmod.current_queues()
    pool = [i for i in pool if passes_hard_filters(i, prefs, None, queues)]
    ranked = rank(pool, prefs, None)[:3]
    rmap = rating_stats()
    out = []
    for it, sc, br in ranked:
        card = item_card(it, prefs, None, sc, br, ratings=rmap)
        left = round(remaining - it.price, 2)
        card["explanation"] = (f"{it.name} (Rs {it.price:.0f}) fits your remaining "
                               f"Rs {remaining:.0f} — leaves Rs {left:.0f} to spare.")
        out.append(card)
    apply_ai_phrasing(out)
    return {"spent": spent, "budget": body.budget, "remaining": remaining,
            "suggestions": out,
            "note": f"Rs {remaining:.0f} left in your tray budget." if out else
                    "Nothing safe fits the remaining budget — try raising it slightly."}


@app.post("/order")
def place_order(body: OrderBody):
    if not body.tray_ids:
        raise HTTPException(400, "Tray is empty — add a dish first.")
    v = tray_validate(TrayBody(tray_ids=body.tray_ids, budget=body.budget,
                               coupon_code=body.coupon_code))
    if v["unavailable"]:
        raise HTTPException(400, f"Cannot order sold-out items: {', '.join(v['unavailable'])}")
    # FIRSTORDER is one-per-user: reuse proceeds at full price, never blocks.
    coupon_note = ""
    mem_coupons: Optional[dict] = None
    if body.session_id:
        _, mem_c = _session(body.session_id)
        mem_coupons = mem_c
        used = mem_c.get("coupons_used") or []
        if v["coupon"] == "FIRSTORDER" and "FIRSTORDER" in used:
            v = dict(v, coupon=None, discount=0.0, payable=v["total"],
                     coupon_error="FIRSTORDER was already used on this account — full total applies.")
            coupon_note = " (FIRSTORDER already used — paid full total)"
    token = _mint_token()
    expanded_items = [store.get(i) for i in _expand_tray(body.tray_ids)]
    expanded_items = [i for i in expanded_items if i]
    counter, counter_label = _counter_for_tray(expanded_items)
    row = {"token": token, "tray": body.tray_ids, "total": v["total"],
           "payable": v["payable"], "coupon": v["coupon"], "discount": v["discount"],
           "counter": counter, "counter_label": counter_label,
           "budget": body.budget, "eta": v["eta_minutes"], "at": datetime.now().isoformat(),
           "session_id": body.session_id or ""}
    _append_json(ORDERS_PATH, row)
    try:
        db.log_order(row)
    except Exception:
        pass
    # Memory: remember every ordered item (dynamic combos expand to parts).
    try:
        if body.session_id:
            mem_o = mem_coupons if mem_coupons is not None else _session(body.session_id)[1]
            flat: list[str] = []
            for raw in body.tray_ids:
                if raw.startswith("dyn_"):
                    flat.extend(raw[4:].split("__"))
                else:
                    flat.append(raw)
            memory_store.record_order(mem_o, [f for f in flat if store.get(f)])
            if v["coupon"] == "FIRSTORDER":
                used_list = mem_o.setdefault("coupons_used", [])
                if "FIRSTORDER" not in used_list:
                    used_list.append("FIRSTORDER")
                # Abuse guard: coupon history stays bounded.
                del used_list[:-10]
            memory_store.save(body.session_id, mem_o)
    except Exception:
        pass
    return {"token": token, "total": v["total"], "eta_minutes": v["eta_minutes"],
            "payable": v["payable"], "discount": v["discount"], "coupon": v["coupon"],
            "counter": counter, "counter_label": counter_label,
            "coupon_error": v.get("coupon_error"),
            "message": f"Order confirmed! Token {token}, ready in ~{v['eta_minutes']} min. "
                       + (f"Pay Rs {v['payable']:.0f} with {v['coupon']} (saved Rs {v['discount']:.0f})."
                          if v["discount"] else f"Total Rs {v['total']:.0f}.")
                       + coupon_note}


@app.post("/feedback")
def feedback(body: FeedbackBody):
    it = store.get(body.item_id)
    if not it:
        raise HTTPException(404, f"Unknown item '{body.item_id}'")
    # Abuse guard: same session voting the same way twice must not farm
    # popularity (spam +1 to 100). The vote is still logged as an audit
    # trail, but the global nudge applies once per direction. Changing your
    # mind (like -> dislike) still counts.
    deduped = False
    if body.session_id and body.rating != 0:
        try:
            _, mem_v = _session(body.session_id)
            prev = (mem_v.get("likes") or {}).get(body.item_id, 0)
            if (prev > 0 and body.rating > 0) or (prev < 0 and body.rating < 0):
                deduped = True
        except Exception:
            deduped = False
    _append_json(FEEDBACK_PATH, {
        "item_id": body.item_id, "rating": body.rating, "comment": body.comment,
        "budget": body.budget, "mood": body.mood, "at": datetime.now().isoformat(),
        "session_id": body.session_id or "",
    })
    try:
        db.log_feedback({"item_id": body.item_id, "rating": body.rating,
                         "comment": body.comment, "budget": body.budget,
                         "mood": body.mood})
    except Exception:
        pass
    # Log improves popularity scores: small nudge, clamped 0-100.
    # Skipped for same-direction repeat votes (see dedupe guard above).
    try:
        items = store.all()
        if not deduped:
            if body.rating > 0:
                it.popularity_score = min(100, it.popularity_score + 1)
            elif body.rating < 0:
                it.popularity_score = max(0, it.popularity_score - 1)
        store.save()
    except Exception:
        pass
    # Memory: likes/dislikes steer YOUR future ranking immediately.
    try:
        if body.session_id:
            _, mem_f = _session(body.session_id)
            memory_store.record_feedback(mem_f, body.item_id, body.rating)
            memory_store.save(body.session_id, mem_f)
    except Exception:
        pass
    return {"ok": True, "item_id": body.item_id, "new_popularity": it.popularity_score,
            "deduped": deduped}


# ---------- admin ----------

@app.patch("/admin/items/{item_id}/availability")
def admin_availability(item_id: str, body: AvailabilityBody):
    try:
        it = store.set_availability(item_id, body.available)
    except KeyError:
        raise HTTPException(404, f"Unknown item '{item_id}'")
    try:
        if db.is_configured():
            db.upsert_menu([it])
    except Exception:
        pass
    return {"ok": True, "id": it.id, "availability": it.availability}


@app.patch("/admin/items/{item_id}/price")
def admin_price(item_id: str, body: PriceBody):
    try:
        it = store.update_price(item_id, body.price)
    except KeyError:
        raise HTTPException(404, f"Unknown item '{item_id}'")
    try:
        if db.is_configured():
            db.upsert_menu([it])
    except Exception:
        pass
    return {"ok": True, "id": it.id, "price": it.price}


@app.post("/admin/items")
def admin_add(data: dict):
    try:
        it = store.add_item(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        if db.is_configured():
            db.upsert_menu([it])
    except Exception:
        pass
    return {"ok": True, "id": it.id}


@app.get("/admin/analytics")
def admin_analytics():
    orders = _read_json_list(ORDERS_PATH)
    feedbacks = _read_json_list(FEEDBACK_PATH)
    counts: dict[str, int] = {}
    for o in orders:
        for tid in _expand_tray(o.get("tray", [])):
            counts[tid] = counts.get(tid, 0) + 1
    for f in feedbacks:
        if f.get("rating", 0) > 0:
            counts[f["item_id"]] = counts.get(f["item_id"], 0) + 1
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    top_named = [{"id": k, "name": (store.get(k).name if store.get(k) else k), "count": v} for k, v in top]
    stats = _budget_stats()
    # Extended real-world KPIs (all additive — existing keys untouched).
    revenue = round(sum(_money(o) for o in orders), 2)
    avg_order_value = round(revenue / len(orders), 2) if orders else None
    by_hour: dict[str, int] = {}
    for o in orders:
        try:
            h = datetime.fromisoformat(o.get("at", "")).hour
            by_hour[str(h)] = by_hour.get(str(h), 0) + 1
        except Exception:
            continue
    cat_split: dict[str, int] = {}
    for o in orders:
        for tid in _expand_tray(o.get("tray", [])):
            it = store.get(tid)
            if it:
                c = it.category.value
                cat_split[c] = cat_split.get(c, 0) + 1
    order_totals = [_money(o) for o in orders]
    sold_out = [{"id": i.id, "name": i.name} for i in store.all() if not i.availability]
    # Revenue per day, last 7 days (oldest first) — drives the admin chart.
    rev_day: dict[str, dict[str, Any]] = {}
    for i in range(6, -1, -1):
        d = (datetime.now().date() - timedelta(days=i)).isoformat()
        rev_day[d] = {"date": d, "total": 0.0, "count": 0}
    for o in orders:
        try:
            day = datetime.fromisoformat(o.get("at", "")).date().isoformat()
        except Exception:
            continue
        if day in rev_day:
            rev_day[day]["total"] = round(rev_day[day]["total"] + _money(o), 2)
            rev_day[day]["count"] += 1
    _fb_budgets = [r.get("budget") for r in feedbacks
                   if isinstance(r.get("budget"), (int, float))]
    return {"top_items": top_named, "orders": len(orders), **stats,
            "live_items": len(store.live()), "total_items": len(store.all()),
            "revenue": revenue, "avg_order_value": avg_order_value,
            "min_budget": min(_fb_budgets) if _fb_budgets else None,
            "max_budget": max(_fb_budgets) if _fb_budgets else None,
            "orders_by_hour": by_hour, "category_split": cat_split,
            "revenue_by_day": list(rev_day.values()),
            "sold_out_count": len(sold_out), "sold_out_items": sold_out[:10]}


@app.patch("/admin/queue")
def admin_set_queue(body: QueueBody):
    try:
        qs = qmod.set_override(body.counter, body.minutes)
    except KeyError:
        raise HTTPException(404, f"Unknown counter '{body.counter}'")
    return {"ok": True, "queues": qs}


@app.delete("/admin/queue")
def admin_clear_queue():
    return {"ok": True, "queues": qmod.clear_overrides()}


# ---------- user real-world routes (all additive) ----------

@app.get("/orders")
def list_orders(session_id: str = "", limit: int = Query(default=10, ge=1, le=50)):
    """My Orders: recent trays for this session, newest first, with live status."""
    if not session_id:
        return {"orders": [], "count": 0}
    mine = _session_orders(session_id)[:limit]
    out = []
    for o in mine:
        st = _order_status(o.get("token", ""))
        out.append({
            "token": o.get("token"), "tray": o.get("tray", []),
            "items": st["items"] if st else [], "total": o.get("total"),
            "payable": o.get("payable", o.get("total")),
            "coupon": o.get("coupon"), "eta": o.get("eta"),
            "at": o.get("at"), "state": st["state"] if st else "UNKNOWN",
            "counter": o.get("counter"), "counter_label": o.get("counter_label"),
        })
    return {"orders": out, "count": len(out)}


@app.delete("/order/{token}")
def cancel_order(token: str):
    return _cancel_order_row(token.upper())


@app.get("/favorites")
def get_favorites(session_id: str = ""):
    sid, mem = _session(session_id or None)
    favs = [f for f in (mem.get("favorites") or []) if store.get(f)]
    rmap = rating_stats()
    return {"favorites": favs, "session_id": sid,
            "items": [item_card(store.get(f), UserPreferences(), None, ratings=rmap) for f in favs]}


@app.post("/favorites")
def toggle_favorite(body: FavoriteBody):
    if not store.get(body.item_id):
        raise HTTPException(404, f"Unknown item '{body.item_id}'")
    sid, mem = _session(body.session_id)
    on = memory_store.toggle_favorite(mem, body.item_id)
    memory_store.save(sid, mem)
    return {"ok": True, "session_id": sid, "favorited": on,
            "favorites": mem.get("favorites", [])}


@app.get("/profile")
def get_profile(session_id: str = ""):
    sid, mem = _session(session_id or None)
    return {"profile": memory_store.get_profile(mem), "session_id": sid}


@app.post("/profile")
def save_profile(body: ProfileBody):
    sid, mem = _session(body.session_id)
    patch = {k: v for k, v in body.model_dump().items()
             if k != "session_id" and v is not None}
    # Validate allergies against the known enum; drop unknowns silently.
    if "allergies" in patch:
        from backend.models import Allergen as _Alg
        clean = []
        for a in patch["allergies"] or []:
            try:
                _Alg(a)
                clean.append(a)
            except Exception:
                continue
        patch["allergies"] = clean
    prof = memory_store.save_profile(mem, patch)
    memory_store.save(sid, mem)
    return {"ok": True, "session_id": sid, "profile": prof}


@app.get("/feedback/{item_id}")
def item_reviews(item_id: str, limit: int = Query(default=10, ge=1, le=30)):
    it = store.get(item_id)
    if not it:
        raise HTTPException(404, f"Unknown item '{item_id}'")
    rows = [r for r in _read_json_list(FEEDBACK_PATH) if r.get("item_id") == item_id]
    likes = sum(1 for r in rows if (r.get("rating") or 0) > 0)
    dislikes = sum(1 for r in rows if (r.get("rating") or 0) < 0)
    comments = [{"comment": r.get("comment"), "rating": r.get("rating"), "at": r.get("at")}
                for r in sorted(rows, key=lambda r: r.get("at", ""), reverse=True)
                if r.get("comment")][:limit]
    return {"item_id": item_id, "name": it.name, "likes": likes,
            "dislikes": dislikes, "review_count": len(rows), "comments": comments}


@app.post("/bill/split")
def bill_split(body: BillSplitBody):
    expanded = [store.get(i) for i in _expand_tray(body.tray_ids)]
    expanded = [i for i in expanded if i]
    if not expanded:
        raise HTTPException(400, "Tray is empty.")
    total = round(sum(i.price for i in expanded), 2)
    cp = _apply_coupon(total, body.coupon_code)
    per = round(cp["payable"] / body.people, 2)
    return {"total": total, "discount": cp["discount"], "payable": cp["payable"],
            "coupon": cp["coupon"], "coupon_error": cp["coupon_error"],
            "people": body.people, "per_person": per,
            "breakdown": [{"id": i.id, "name": i.name, "price": i.price} for i in expanded]}


@app.get("/trending")
def trending(limit: int = Query(default=5, ge=1, le=12)):
    items = _trending_items(limit)
    return {"count": len(items), "items": items}


@app.get("/specials")
def daily_specials():
    """Today's specials: deterministic daily rotation (stable all day, changes daily)."""
    import hashlib
    day = datetime.now().date().isoformat()
    live = store.live() or store.all()
    rmap = rating_stats()

    def day_score(it) -> float:
        h = int(hashlib.md5(f"{day}:{it.id}".encode()).hexdigest()[:8], 16) % 20
        likes = rmap.get(it.id, {}).get("likes", 0) - rmap.get(it.id, {}).get("dislikes", 0)
        return it.popularity_score + likes * 2 + h

    picks = sorted(live, key=day_score, reverse=True)[:3]
    out = []
    for it in picks:
        c = item_card(it, UserPreferences(), None, ratings=rmap)
        c["explanation"] = (f"Today's special: {it.name} (Rs {it.price:.0f}) — "
                            "hand-picked campus favorite, only highlighted today!")
        out.append(c)
    return {"date": day, "count": len(out), "items": out}


@app.get("/spending")
def spending(session_id: str = ""):
    if not session_id:
        return {"today_total": 0.0, "week_total": 0.0, "today_count": 0,
                "order_count": 0, "by_day": []}
    return _spending_for(session_id)


@app.get("/coupons")
def list_coupons():
    return {"coupons": [{"code": k, "percent_off": int(v * 100)} for k, v in COUPONS.items()]}


# ---------- admin real-world routes (all additive) ----------

@app.get("/admin/orders")
def admin_orders(q: str = "", limit: int = Query(default=50, ge=1, le=200)):
    rows = sorted(_read_json_list(ORDERS_PATH), key=lambda r: r.get("at", ""), reverse=True)
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in str(r.get("token", "")).lower()
                or ql in str(r.get("session_id", "")).lower()]
    out = []
    for o in rows[:limit]:
        st = _order_status(o.get("token", ""))
        out.append({"token": o.get("token"), "tray": o.get("tray", []),
                    "items": st["items"] if st else [],
                    "total": o.get("total"), "payable": o.get("payable", o.get("total")),
                    "coupon": o.get("coupon"), "eta": o.get("eta"), "at": o.get("at"),
                    "session_id": o.get("session_id", ""),
                    "state": st["state"] if st else "UNKNOWN",
                    "counter": o.get("counter"), "counter_label": o.get("counter_label")})
    return {"count": len(out), "orders": out}


@app.patch("/admin/orders/{token}")
def admin_order_status(token: str, body: OrderStatusBody):
    want = str(body.status or "").upper()
    if want not in ("READY", "COMPLETED", "CANCELLED"):
        raise HTTPException(400, "status must be READY | COMPLETED | CANCELLED")
    rows = _read_json_list(ORDERS_PATH)
    idx = next((i for i in range(len(rows) - 1, -1, -1)
                if str(rows[i].get("token", "")).upper() == token.upper()), None)
    if idx is None:
        raise HTTPException(404, f"No order '{token}'")
    rows[idx]["status_override"] = want
    _write_json_atomic(ORDERS_PATH, rows)
    return {"ok": True, "token": rows[idx]["token"], "state": want}


@app.get("/admin/feedback")
def admin_feedback(limit: int = Query(default=50, ge=1, le=200)):
    rows = sorted(_read_json_list(FEEDBACK_PATH), key=lambda r: r.get("at", ""), reverse=True)
    out = []
    for r in rows[:limit]:
        it = store.get(r.get("item_id", ""))
        out.append({**r, "item_name": it.name if it else r.get("item_id")})
    return {"count": len(out), "feedback": out}


@app.post("/admin/items/bulk-availability")
def admin_bulk_availability(body: BulkAvailabilityBody):
    n = store.bulk_availability(body.ids, body.available)
    return {"ok": True, "updated": n, "available": body.available}


@app.post("/admin/items/mark-all-live")
def admin_mark_all_live():
    n = store.mark_all_live()
    return {"ok": True, "restored": n}


@app.patch("/admin/items/{item_id}")
def admin_edit_item(item_id: str, data: dict):
    try:
        it = store.update_item(item_id, data)
    except KeyError:
        raise HTTPException(404, f"Unknown item '{item_id}'")
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        if db.is_configured():
            db.upsert_menu([it])
    except Exception:
        pass
    return {"ok": True, "id": it.id, "price": it.price,
            "prep_time_minutes": it.prep_time_minutes,
            "popularity_score": it.popularity_score, "availability": it.availability,
            "calories": it.calories, "protein_g": it.protein_g,
            "carbs_g": it.carbs_g, "sugar_g": it.sugar_g, "fiber_g": it.fiber_g}


@app.get("/admin/export")
def admin_export(kind: str = "menu"):
    import csv
    import io
    buf = io.StringIO()
    if kind == "orders":
        w = csv.writer(buf)
        w.writerow(["token", "at", "items", "total", "payable", "coupon",
                    "eta", "session_id", "state"])
        for o in _read_json_list(ORDERS_PATH):
            st = _order_status(o.get("token", ""))
            w.writerow([o.get("token"), o.get("at"), "|".join(o.get("tray", [])),
                        o.get("total"), o.get("payable", o.get("total")),
                        o.get("coupon") or "", o.get("eta"),
                        o.get("session_id", ""), st["state"] if st else ""])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=orders.csv"})
    w = csv.writer(buf)
    w.writerow(["id", "name", "price", "category", "cuisine", "availability",
                "prep_time", "calories", "protein_g", "popularity",
                "carbs_g", "sugar_g", "fiber_g"])
    for it in store.all():
        w.writerow([it.id, it.name, it.price, it.category.value, it.cuisine.value,
                    int(it.availability), it.prep_time_minutes, it.calories,
                    it.protein_g, it.popularity_score,
                    it.carbs_g, it.sugar_g, it.fiber_g])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=menu.csv"})


@app.get("/admin/alerts")
def admin_alerts():
    sold_out = [{"id": i.id, "name": i.name, "price": i.price}
                for i in store.all() if not i.availability]
    queues = qmod.current_queues()
    long_q = [{"counter": n, "label": qmod.COUNTERS[n]["label"], "wait_minutes": m}
              for n, m in queues.items() if m >= 8]
    agg: dict[str, dict[str, int]] = {}
    for r in _read_json_list(FEEDBACK_PATH):
        cell = agg.setdefault(r.get("item_id", ""), {"likes": 0, "dislikes": 0})
        if (r.get("rating") or 0) > 0:
            cell["likes"] += 1
        elif (r.get("rating") or 0) < 0:
            cell["dislikes"] += 1
    disliked = [{"id": k, "name": (store.get(k).name if store.get(k) else k),
                 "dislikes": v["dislikes"], "likes": v["likes"]}
                for k, v in agg.items()
                if v["dislikes"] >= 2 and v["dislikes"] > v["likes"]]
    disliked.sort(key=lambda d: d["dislikes"], reverse=True)
    return {"sold_out": sold_out, "sold_out_count": len(sold_out),
            "long_queues": long_q, "disliked": disliked[:10]}
