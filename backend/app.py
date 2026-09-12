"""CampusBite FastAPI backend — REST + deterministic recommendation + chat orchestration."""
from __future__ import annotations

import json
import random
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend import db_supabase as db
from backend import queue as qmod
from backend.llm import (batch_phrase, merge_llm_patch, openrouter_available,
                         parse_prefs_with_llm)
from backend.memory import MemoryStore, boost_singles
from backend.models import MenuItem, UserPreferences
from backend.nlu import (apply_refinement, clarifying_questions, detect_intent, nonsense_reply,
                         parse_meal, parse_one_shot, smalltalk_reply)
from backend.recommender import (cross_contamination_warning, effective_prep_time,
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
    sid = session_id or uuid.uuid4().hex[:16]
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
    if elapsed >= eta:
        state, detail = "READY", "Ready for pickup — show your token at the counter."
    else:
        state, detail = "PREPARING", f"Being prepared — ready in ~{eta - elapsed} min."
    return {"token": o.get("token"), "state": state, "detail": detail,
            "items": names, "total": o.get("total"), "eta_minutes": eta,
            "elapsed_minutes": elapsed}


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
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


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
    """One-model-call phrasing for a batch of cards. Returns model or rule-based."""
    texts = [c.get("explanation") or "" for c in cards]
    if not any(texts):
        return "rule-based"
    out, model = batch_phrase(texts)
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
    best = None
    for it in store.all():
        if it.name.lower() in t or it.id.replace("_", " ") in t:
            if best is None or len(it.name) > len(best.name):
                best = it
    return best


def greeting_for(meal: str) -> str:
    if meal == "breakfast":
        return "Good morning! Breakfast items are being served. Tell me your budget and craving to get started."
    if meal == "lunch":
        return "Good afternoon! Lunch service is on. Tell me your budget and craving to get started."
    return "Good evening! Dinner options are live. Tell me your budget and craving to get started."


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
    if prefs.cravings:
        bits.append(" + ".join(prefs.cravings[:2]))
    suffix = f" ({', '.join(bits)})" if bits else ""
    return f"Here are my top {n} picks for {meal}{suffix}:"


_ratings_cache: dict[str, Any] = {"key": None, "map": {}}


def rating_stats() -> dict[str, dict[str, int]]:
    """Aggregate feedback likes/dislikes per item (mtime-cached file read)."""
    try:
        mtime = FEEDBACK_PATH.stat().st_mtime if FEEDBACK_PATH.exists() else 0
    except Exception:
        mtime = 0
    if _ratings_cache["key"] == mtime:
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
    _ratings_cache.update({"key": mtime, "map": agg})
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


# ---------- schemas ----------

class RecommendBody(BaseModel):
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    meal: Optional[str] = None
    session_id: Optional[str] = None


class ChatBody(BaseModel):
    message: str
    prefs: UserPreferences = Field(default_factory=UserPreferences)
    meal_override: Optional[str] = None
    session_id: Optional[str] = None


class TrayBody(BaseModel):
    tray_ids: list[str] = Field(default_factory=list)
    budget: Optional[float] = None


class OrderBody(BaseModel):
    tray_ids: list[str] = Field(default_factory=list)
    budget: Optional[float] = None
    session_id: Optional[str] = None


class FeedbackBody(BaseModel):
    item_id: str
    rating: int = Field(..., ge=-1, le=1)
    comment: Optional[str] = None
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
):
    items = store.live() if available_only else store.all()
    out = []
    for it in items:
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
        if dietary and dietary not in [str(d).split(".")[-1] for d in it.dietary_tags]:
            # 'veg' browsing should also surface vegan/jain (they are veg-safe)
            tags = {str(d).split(".")[-1] for d in it.dietary_tags}
            if dietary == "veg" and not (tags & {"veg", "vegan", "jain"}):
                continue
            elif dietary != "veg":
                continue
        if q and q.lower() not in (it.name + " " + it.description).lower():
            continue
        out.append(it)
    rmap = rating_stats()
    if goal == "high_protein":
        out = sorted(out, key=lambda i: (-i.protein_g, i.price))
    elif goal == "low_calorie":
        out = sorted(out, key=lambda i: (i.calories, i.price))
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
    return out


@app.post("/chat")
def chat(body: ChatBody):
    text = (body.message or "").strip()
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
        hello = greeting_for(meal)
        if returning:
            hello += " Welcome back — I remember your usual picks."
        memory_store.save(sid, mem)
        return {
            "intent": intent, "ai": ai_label(), "reply": hello, "meal": meal,
            "session_id": sid,
            "prefs": body.prefs.model_dump(),
            "chips": ["Under Rs 50", "Rs 70, spicy veg, 10 mins", "Show combos", "Vegan", "In a hurry"],
            "singles": [], "combos": [],
        }

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
        items = sorted(items, key=lambda i: (i.price, -i.popularity_score))[:12]
        lines = [f"{i.name} — Rs {i.price:.0f} (~{i.prep_time_minutes} min)" for i in items]
        head = f"Here are {len(items)} options"
        if probe.budget is not None:
            head += f" under Rs {probe.budget:.0f}"
        browse_cards = [item_card(i, probe, meal) for i in items[:6]]
        browse_ai = apply_ai_phrasing(browse_cards)
        memory_store.record_chat(mem, probe)
        memory_store.save(sid, mem)
        return {
            "intent": intent, "ai": browse_ai, "reply": head + ":\n" + "\n".join(lines) if lines else
            "No matches for that browse — try raising the budget or clearing a filter.",
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
        payload.update({
            "intent": intent,
            "ai": payload.pop("ai_phrase", "rule-based"),
            "session_id": sid,
            "reply": note + " Here are the updated picks.",
            "chips": ["Something cheaper", "Less spicy", "More filling", "Quicker", "Show combos"],
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
                      f"Rs {float(st['total'] or 0):.0f} — {st['state']}. {st['detail']}"),
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
    # Memory: usual-budget fallback + personalization boosts, then record+save.
    mem_note = ""
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
    payload.update({
        "intent": "recommend",
        "ai": parse_used or payload.pop("ai_phrase", "rule-based"),
        "session_id": sid,
        "reply": (mem_note + head + follow).strip(),
        "chips": ["Something cheaper", "Less spicy", "More filling", "Quicker", "Show combos", "No onion/garlic"],
    })
    return payload


@app.post("/tray/validate")
def tray_validate(body: TrayBody):
    items = []
    for i in body.tray_ids:
        it = store.get(i)
        if not it:
            raise HTTPException(404, f"Unknown item '{i}'")
        items.append(it)
    # dynamic combo ids look like dyn_a__b
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
    over = body.budget is not None and total > body.budget
    off = [i.name for i in expanded if not i.availability]
    return {
        "count": len(expanded), "total": total, "budget": body.budget,
        "over_budget": over, "over_by": round(total - body.budget, 2) if over else 0.0,
        "eta_minutes": eta, "queue_minutes": queues,
        "unavailable": off,
        "warning": (f"Over budget by Rs {total - body.budget:.0f}. Remove an item or say 'something cheaper'."
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
    v = tray_validate(TrayBody(tray_ids=body.tray_ids, budget=body.budget))
    if v["unavailable"]:
        raise HTTPException(400, f"Cannot order sold-out items: {', '.join(v['unavailable'])}")
    token = f"CB-{random.randint(100, 999)}"
    row = {"token": token, "tray": body.tray_ids, "total": v["total"],
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
            _, mem_o = _session(body.session_id)
            flat: list[str] = []
            for raw in body.tray_ids:
                if raw.startswith("dyn_"):
                    flat.extend(raw[4:].split("__"))
                else:
                    flat.append(raw)
            memory_store.record_order(mem_o, [f for f in flat if store.get(f)])
            memory_store.save(body.session_id, mem_o)
    except Exception:
        pass
    return {"token": token, "total": v["total"], "eta_minutes": v["eta_minutes"],
            "message": f"Order confirmed! Token {token}, ready in ~{v['eta_minutes']} min. Total Rs {v['total']:.0f}."}


@app.post("/feedback")
def feedback(body: FeedbackBody):
    it = store.get(body.item_id)
    if not it:
        raise HTTPException(404, f"Unknown item '{body.item_id}'")
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
    try:
        items = store.all()
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
    return {"ok": True, "item_id": body.item_id, "new_popularity": it.popularity_score}


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
        for tid in o.get("tray", []):
            counts[tid] = counts.get(tid, 0) + 1
    for f in feedbacks:
        if f.get("rating", 0) > 0:
            counts[f["item_id"]] = counts.get(f["item_id"], 0) + 1
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    top_named = [{"id": k, "name": (store.get(k).name if store.get(k) else k), "count": v} for k, v in top]
    stats = _budget_stats()
    return {"top_items": top_named, "orders": len(orders), **stats,
            "live_items": len(store.live()), "total_items": len(store.all())}


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
