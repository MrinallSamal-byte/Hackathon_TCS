"""CampusBite deterministic recommendation engine.

Hard filters -> soft scoring -> top singles + combos -> explanations + alternatives.
The LLM layer may only phrase these outputs; it must never invent items.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from backend.models import MenuItem, UserPreferences
from backend.queue import counter_of

# ---- mood / taste normalisation ----

MOOD_ALIASES: dict[str, str] = {
    "happy": "celebratory", "celebrating": "celebratory", "celebration": "celebratory",
    "birthday": "celebratory", "party": "celebratory",
    "stressed": "comfort", "stress": "comfort", "sad": "comfort", "tired": "energizing",
    "sleepy": "energizing", "low energy": "energizing", "exhausted": "energizing",
    "homesick": "homesick", "homesickness": "homesick", "nostalgic": "homesick",
    "home": "homesick", "exam": "study_fuel", "exam-mode": "study_fuel", "study": "study_fuel",
    "studying": "study_fuel", "focus": "study_fuel", "hungry": "comfort",
    "very hungry": "comfort", "starving": "comfort", "light": "light",
    "indulgent": "indulgent", "craving": "indulgent", "treat": "indulgent",
    "energizing": "energizing", "comfort": "comfort", "celebratory": "celebratory",
    "study_fuel": "study_fuel",
}

HUNGER_TO_PORTION: dict[str, str] = {
    "light_bite": "light", "light": "light", "snack": "light", "small": "light",
    "medium": "medium", "moderate": "medium", "normal": "medium",
    "hungry": "heavy", "more filling": "heavy", "filling": "filling",
    "very_hungry": "filling", "starving": "filling", "very hungry": "filling",
}

CRAVING_TO_TASTE: dict[str, str] = {
    "spicy": "spicy", "masala": "spicy", "hot": "spicy", "mirchi": "spicy",
    "sweet": "sweet", "dessert": "sweet", "chocolate": "sweet", "mithai": "sweet",
    "cheesy": "cheesy", "cheese": "cheesy", "paneer": "savory",
    "tangy": "tangy", "sour": "tangy", "lemon": "tangy", "imli": "tangy",
    "savory": "savory", "salty": "savory", "namkeen": "savory",
    "refreshing": "refreshing", "cool": "refreshing", "juice": "refreshing", "cold": "refreshing",
    "comforting": "comforting", "comfort": "comforting", "warm": "comforting", "soup": "comforting",
    "soup": "comforting", "homely": "comforting",
}

MEAT_KEYWORDS = {"chicken", "mutton", "fish", "egg", "prawn", "seafood", "keema", "meat", "non-veg", "non veg"}

# Deep-fried / refined-carb flags for honest diabetic scoring (labels, not filters).
FRIED_KEYWORDS = {"fried", "samosa", "vada", "fries", "bhature", "pakora", "jalebi", "bajji"}
WHOLE_FRUIT_IDS = {"jain_fruit_bowl"}


def _has_added_sugar(item: MenuItem) -> bool:
    return any(w in " ".join(item.ingredients).lower()
               for w in ["sugar", "jaggery", "honey", "syrup", "chocolate", "ice cream"])


def diabetic_fit(item: MenuItem) -> bool:
    """Strict lower-sugar suitability (soft signal; NEVER a hard filter).

    Whole fruit is allowed despite natural sugars; deep-fried items, desserts
    and added-sugar drinks never qualify no matter how small the portion.
    """
    name_ing = (item.name + " " + " ".join(item.ingredients)).lower()
    if any(k in name_ing for k in FRIED_KEYWORDS):
        return False
    if item.category.value == "dessert" and item.id not in WHOLE_FRUIT_IDS:
        return False
    if (item.category.value == "beverage" and item.sugar_g > 5
            and _has_added_sugar(item)):
        return False
    return item.sugar_g <= 10 and item.carbs_g <= 45


def diabetic_score(item: MenuItem) -> tuple[float, str]:
    """Data-grounded diabetic signal. Returns (points, tier).

    Tiers: fit (genuinely lower-sugar) / watch (ok in small portions) / avoid.
    """
    if diabetic_fit(item):
        pts = 16.0 + min(6.0, item.fiber_g * 1.0 + item.protein_g * 0.3)
        return round(pts, 2), "fit"
    if item.category.value == "dessert" or item.sugar_g > 28:
        return -25.0, "avoid"
    if item.sugar_g > 15 or item.carbs_g > 60:
        return -10.0, "avoid"
    return 4.0, "watch"


# Period & menstrual cramp nutritional intelligence (soft signals; NEVER a hard filter):
# - Iron replenishment (spinach, lentils, oats, eggs)
# - Uterine relaxation & Magnesium (dark chocolate mousse, whole fruit)
# - Soothing pelvic warmth & hydration (hot tomato soup, khichdi, green tea, masala chai)
# - Anti-bloating & gut relief (masala chaas, sweet lime juice)
PERIOD_BOOST_MAP: dict[str, tuple[float, str]] = {
    "palak_roti": (24.0, "iron-rich spinach & whole wheat roti to replenish energy and ease cramps"),
    "jain_khichdi": (22.0, "warm, light, easy-to-digest comfort khichdi that soothes the gut without gas/bloating"),
    "combo_khichdi_chaas": (22.0, "warm comfort khichdi paired with anti-bloating digestive buttermilk"),
    "tomato_soup": (20.0, "warm soothing broth that aids pelvic relaxation and hydration"),
    "choco_mousse": (20.0, "rich in cocoa magnesium which eases uterine contractions and lifts PMS mood"),
    "dal_rice": (18.0, "warm, wholesome lentil comfort providing steady iron and easy digestion"),
    "chaas": (16.0, "probiotic buttermilk that reduces water retention and relieves menstrual bloating"),
    "oats_upma": (16.0, "gentle complex carbs and iron for steady energy without insulin spikes"),
    "egg_curry_rice": (15.0, "warm comforting protein with bioavailable iron"),
    "green_tea": (12.0, "soothing, warm antioxidant tea for gentle cramp relief"),
    "masala_chai": (12.0, "warm ginger and spices to ease cramps and nausea"),
    "jain_fruit_bowl": (12.0, "natural hydration and potassium to fight bloating"),
}

PERIOD_AVOID_IDS: set[str] = {
    "chole_bhature", "samosa", "jain_samosa", "vada_pav", "fries", "peri_fries",
    "combo_chole_chaas", "gulab_jamun", "jalebi", "combo_biryani_jamun",
    "oreo_shake", "cold_coffee", "chicken_biryani", "paneer_naan"
}


def period_comfort_score(item: MenuItem) -> tuple[float, str, str]:
    """Scores items for period & menstrual cramp comfort.
    Returns (points, tier, reason).
    Tiers: 'boost' (warm/iron/magnesium/anti-bloating), 'neutral', 'avoid' (fried/heavy sugar).
    """
    if item.id in PERIOD_BOOST_MAP:
        pts, reason = PERIOD_BOOST_MAP[item.id]
        return pts, "boost", reason

    name_ing = (item.name + " " + " ".join(item.ingredients)).lower()
    # Deep-fried foods trigger inflammatory prostaglandins which exacerbate cramps
    if any(k in name_ing for k in FRIED_KEYWORDS) or item.id in PERIOD_AVOID_IDS:
        return -25.0, "avoid", "deep-fried and heavy foods trigger prostaglandins, worsening menstrual cramps and bloating"

    # High refined sugar causes sharp glycemic crashes, intensifying fatigue and cramps
    if item.sugar_g >= 25 or (item.category.value == "dessert" and item.id != "choco_mousse" and item.id not in WHOLE_FRUIT_IDS):
        return -22.0, "avoid", "high refined sugar can cause glucose crashes that worsen cramps and fatigue"

    # Moderate comfort items (warm, mild)
    if item.category.value in ("soup", "main_course") and item.spice_level <= 1:
        return 8.0, "neutral", "mild, warm meal"

    return 3.0, "neutral", "balanced option"


# High-protein honesty tiers (soft signal; NEVER a hard filter).
PROTEIN_FIT_G = 15.0  # genuinely high-protein per serving
PROTEIN_MID_G = 8.0   # decent protein, shy of the bar


def protein_tier(item: MenuItem) -> str:
    """fit (>=15g) / mid (8-14g) / low (<8g). Only fit items may be
    presented as high-protein picks."""
    try:
        p = float(item.protein_g)
    except (TypeError, ValueError):
        return "low"
    if p >= PROTEIN_FIT_G:
        return "fit"
    if p >= PROTEIN_MID_G:
        return "mid"
    return "low"


SWEET_CRAVING_WORDS = {"sweet", "dessert", "chocolate", "mithai", "shake",
                       "ice cream", "jalebi", "brownie", "cake", "pastry",
                       "candy", "soda", "cola", "lassi", "halwa", "kheer",
                       "jamun", "rasgulla", "jaggery"}


def normalize_mood(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = raw.strip().lower()
    return MOOD_ALIASES.get(key, key if key in
        {"energizing", "comfort", "light", "indulgent", "study_fuel", "homesick", "celebratory"} else key)


def infer_meal_period(now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    h = now.hour + now.minute / 60.0
    if h < 11.5:
        return "breakfast"
    if h < 16.0:
        return "lunch"
    return "dinner"


def _has_onion_garlic(item: MenuItem) -> bool:
    return any("onion" in i.lower() or "garlic" in i.lower() for i in item.ingredients)


def passes_dietary(item: MenuItem, prefs: UserPreferences) -> bool:
    tags = set(item.dietary_tags)
    restr = {r.lower() for r in prefs.dietary_restrictions}

    if "veg" in restr or "vegetarian" in restr:
        if "non_veg" in tags or "egg" in tags:
            return False
    if "eggetarian" in restr:
        # Egg OK, meat blocked.
        if "non_veg" in tags:
            return False
    if "non_veg" in restr:
        # Explicit meat request: only true non-veg dishes (egg-only excluded).
        if "non_veg" not in tags:
            return False
    if "vegan" in restr:
        if "vegan" not in tags:
            return False
    if "jain" in restr:
        if "jain" not in tags:
            return False
        if _has_onion_garlic(item):
            return False
    if "gluten_free" in restr or "gluten-free" in restr:
        if "gluten_free" not in tags or "gluten" in set(item.allergens):
            return False
    if "dairy_free" in restr or "dairy-free" in restr:
        if "dairy_free" not in tags or "dairy" in set(item.allergens):
            return False
    if "halal" in restr:
        # Veg/vegan/jain/egg dishes are inherently fine; meat must be halal-tagged.
        if "non_veg" in tags and "halal" not in tags:
            return False
    if "egg_free" in restr or "egg-free" in restr or "eggless" in restr:
        if "egg" in set(item.allergens) or "egg" in tags:
            return False
        if any("egg" in i.lower() for i in item.ingredients):
            return False
    if prefs.no_onion_garlic:
        if _has_onion_garlic(item):
            return False
    # Allergen hard filter — never relaxed.
    user_all = {str(a).lower() for a in prefs.allergies}
    item_all = {str(a).lower() for a in item.allergens}
    # pydantic enums serialise as e.g. 'Allergen.peanuts'; normalise by suffix match
    def norm(s: str) -> str:
        return s.split(".")[-1].lower()
    if {norm(a) for a in item_all} & {norm(a) for a in user_all}:
        return False
    return True


def effective_prep_time(item: MenuItem, queue: Optional[dict] = None) -> int:
    """Prep + live counter queue (queue maps counter name -> extra minutes)."""
    extra = 0
    if queue:
        extra = int(queue.get(counter_of(item.category.value), 0))
    return item.prep_time_minutes + extra


def passes_hard_filters(item: MenuItem, prefs: UserPreferences, meal: Optional[str],
                        queue: Optional[dict] = None) -> bool:
    if not item.availability:
        return False
    if prefs.budget is not None and item.price > prefs.budget + 1e-9:
        return False
    if prefs.max_prep_time is not None and effective_prep_time(item, queue) > prefs.max_prep_time:
        return False
    if prefs.max_spice is not None and item.spice_level > prefs.max_spice:
        return False
    if prefs.cuisine and item.cuisine.value != prefs.cuisine:
        # combos with mixed cuisine still must match if user pinned a cuisine
        return False
    if prefs.avoid:
        # "without paneer" / "don't want maggi" — hard exclusion on
        # name + ingredients (substring, case-insensitive).
        hay = (item.name + " " + " ".join(item.ingredients)).lower()
        if any(a in hay for a in prefs.avoid):
            return False
    if meal and not prefs.combos_only:
        st = {s.value for s in item.serving_times}
        if meal not in st and "all_day" not in st:
            return False
    if meal and prefs.combos_only:
        pass  # combos serve all day or meal-matched; prebuilt combos carry their own windows
    if not passes_dietary(item, prefs):
        return False
    return True


def soft_score(item: MenuItem, prefs: UserPreferences, meal: Optional[str]) -> tuple[float, dict[str, float]]:
    parts: dict[str, float] = {}
    mood = normalize_mood(prefs.mood)
    parts["mood"] = 30.0 if (mood and mood in item.mood_tags) else 0.0

    cravings = [c.lower() for c in (prefs.cravings or [])]
    taste_hit = False
    for c in cravings:
        want = CRAVING_TO_TASTE.get(c, c)
        if want in item.taste_profile:
            taste_hit = True
            break
        # specific-dish or ingredient mention also counts
        if c and (c in item.name.lower() or any(c in ing.lower() for ing in item.ingredients)):
            taste_hit = True
            break
    parts["taste"] = 25.0 if taste_hit else 0.0
    parts["popularity"] = round(item.popularity_score / 100.0 * 15.0, 2)

    want_portion = HUNGER_TO_PORTION.get((prefs.hunger or "").lower())
    parts["portion"] = 10.0 if (want_portion and item.portion_size.value == want_portion) else 0.0

    if meal:
        st = {s.value for s in item.serving_times}
        if meal in st:
            parts["time_of_day"] = 10.0
        elif "all_day" in st:
            parts["time_of_day"] = 5.0
        else:
            parts["time_of_day"] = 0.0
    else:
        parts["time_of_day"] = 0.0

    if prefs.budget:
        parts["value"] = round(max(0.0, 1.0 - (item.price / prefs.budget)) * 5.0, 2)
    else:
        parts["value"] = 0.0

    # Nutrition goal (soft boost only — never a hard filter).
    parts["goal"] = 0.0
    goal = (prefs.goal or "").lower()
    if goal == "high_protein":
        parts["goal"] = 12.0 if item.protein_g >= 15 else (6.0 if item.protein_g >= 8 else 0.0)
        if protein_tier(item) == "low":
            # A 4g-protein sweet chai must not top a protein ranking on taste:
            # halve the craving bonus so protein-dense picks win. Weights for
            # everyone else are untouched (spec table still exact).
            parts["taste"] = round(parts["taste"] * 0.5, 2)
    elif goal == "low_calorie":
        parts["goal"] = 12.0 if item.calories <= 300 else (6.0 if item.calories <= 450 else 0.0)
        if item.calories > 450:
            parts["taste"] = round(parts["taste"] * 0.5, 2)
    elif goal == "diabetic":
        # Tier is re-derived in explain_item (never stored in score parts —
        # they must stay numeric for sum()).
        parts["goal"] = diabetic_score(item)[0]
    elif goal == "period_friendly":
        pts, tier, _ = period_comfort_score(item)
        parts["goal"] = pts
        if tier == "avoid":
            parts["taste"] = round(parts["taste"] * 0.3, 2)

    # Small cuisine nudge (not in spec points, folded into time slot to keep spec weights exact).
    total = sum(parts.values())
    return total, parts


def rank(items: list[MenuItem], prefs: UserPreferences, meal: Optional[str]) -> list[tuple[MenuItem, float, dict]]:
    scored = [(it, *soft_score(it, prefs, meal)) for it in items]
    scored.sort(key=lambda t: (t[1], t[0].popularity_score), reverse=True)
    return [(it, s, b) for it, s, b in scored]


def generate_dynamic_combos(
    mains: list[MenuItem], sides: list[MenuItem], prefs: UserPreferences, meal: Optional[str],
    queue: Optional[dict] = None,
) -> list[dict[str, Any]]:
    """Pair a main with a side/beverage under the total budget. Returns combo dicts."""
    combos: list[dict[str, Any]] = []
    if prefs.budget is None:
        return combos
    for m in mains[:12]:
        for s in sides[:12]:
            if m.id == s.id:
                continue
            total = m.price + s.price
            if total > prefs.budget + 1e-9:
                continue
            eta = max(effective_prep_time(m, queue), effective_prep_time(s, queue))
            if prefs.max_prep_time is not None and eta > prefs.max_prep_time:
                continue
            # both components must already pass dietary/allergen individually
            sm, _bm = soft_score(m, prefs, meal)
            ss2, _bs = soft_score(s, prefs, meal)
            score = (sm + ss2) / 2.0 + max(0.0, 1.0 - total / prefs.budget) * 5.0
            combos.append({
                "id": f"dyn_{m.id}__{s.id}",
                "name": f"{m.name} + {s.name}",
                "items": [m, s],
                "total_price": round(total, 2),
                "eta": eta,
                "score": round(score, 2),
                "is_dynamic": True,
            })
    combos.sort(key=lambda c: c["score"], reverse=True)
    return combos


def detect_conflict(prefs: UserPreferences) -> Optional[str]:
    restr = {r.lower() for r in prefs.dietary_restrictions}
    craves = " ".join(prefs.cravings or []).lower()
    strict_veg = bool({"vegan", "jain", "veg", "vegetarian", "eggetarian"} & restr)
    if strict_veg and any(k in craves for k in MEAT_KEYWORDS):
        if "vegan" in restr:
            which = "vegan"
        elif "jain" in restr:
            which = "jain"
        elif "eggetarian" in restr:
            which = "eggetarian"
        else:
            which = "vegetarian"
        return (
            f"Quick flag: you asked for {which} options but also craved "
            f"'{', '.join(prefs.cravings)}'. I'll show the best {which} matches — "
            "meat/egg items are filtered out by your dietary rule."
        )
    if (prefs.goal or "").lower() == "high_protein":
        if any(k in craves for k in SWEET_CRAVING_WORDS):
            return (
                "Quick flag: sweet treats are rarely high-protein — I've ranked "
                "protein first while keeping things you'll enjoy."
            )
    if (prefs.goal or "").lower() == "diabetic":
        if any(k in craves for k in SWEET_CRAVING_WORDS):
            return (
                "Quick flag: heavy sweets can spike blood sugar with diabetes — "
                "I'm showing the lowest-sugar options that still satisfy the craving. "
                "This isn't medical advice; when in doubt, check with your doctor."
            )
    if (prefs.goal or "").lower() == "period_friendly":
        if any(k in craves for k in ["chole", "bhature", "samosa", "fried", "fries", "vada", "jalebi", "jamun", "biryani"]):
            return (
                "Quick flag: deep-fried and high-sugar treats can trigger prostaglandins and worsen cramps and bloating. "
                "I've ranked warm, iron-rich comfort options first to help you feel better."
            )
    return None


def cross_contamination_warning(item: MenuItem, prefs: UserPreferences) -> Optional[str]:
    user_all = {str(a).split('.')[-1].lower() for a in prefs.allergies}
    if not user_all:
        return None
    # Shared-fryer / shared-counter caution for street-food snacks.
    if item.cuisine.value == "street_food" and item.category.value == "snack":
        return "Made at a shared street-food counter — ask staff about cross-contact if highly sensitive."
    return None


def explain_item(item: MenuItem, prefs: UserPreferences, meal: Optional[str],
                 score_parts: Optional[dict] = None, pair: Optional[MenuItem] = None) -> str:
    bits: list[str] = []
    bits.append(f"{item.name} (Rs {item.price:.0f}, ~{item.prep_time_minutes} min)")
    if prefs.budget is not None:
        left = prefs.budget - item.price
        bits.append(f"fits your Rs {prefs.budget:.0f} budget (Rs {left:.0f} to spare)")
    diet_bits = []
    r = {d.lower() for d in prefs.dietary_restrictions}
    if "vegan" in r:
        diet_bits.append("fully vegan")
    elif "jain" in r:
        diet_bits.append("Jain (no onion/garlic)")
    elif "veg" in r or "vegetarian" in r:
        diet_bits.append("fully vegetarian")
    if "gluten_free" in r or "gluten-free" in r:
        diet_bits.append("gluten-free")
    if prefs.allergies:
        diet_bits.append("allergen-safe for you")
    if diet_bits:
        bits.append(", ".join(diet_bits))
    mood = normalize_mood(prefs.mood)
    if mood and mood in item.mood_tags:
        bits.append(f"its {', '.join(item.taste_profile)} profile matches your '{prefs.mood}' mood")
    elif prefs.cravings:
        bits.append(f"covers your craving for {', '.join(prefs.cravings)} ({', '.join(item.taste_profile)})")
    goal = (prefs.goal or "").lower()
    if goal == "high_protein":
        # Honest tiers only — a 4g chai is never a "high-protein pick".
        tier = protein_tier(item)
        if tier == "fit":
            bits.append(f"packs {item.protein_g}g protein for your gym goal")
        elif tier == "mid":
            bits.append(f"{item.protein_g}g protein — decent, though shy of the 15g high-protein bar")
    elif goal == "low_calorie" and item.calories <= 450:
        bits.append(f"just {item.calories} kcal, fits your light-diet goal")
    elif goal == "diabetic":
        # Honest tiers only — never call a fried/sugary item "diabetic-friendly".
        _pts, tier = diabetic_score(item)
        if tier == "fit":
            bits.append(f"lower-sugar pick ({item.sugar_g}g sugar, {item.carbs_g}g carbs) for your sugar goal")
        elif tier == "watch":
            bits.append(f"moderate on sugar ({item.sugar_g}g sugar, {item.carbs_g}g carbs) — keep the portion small")
        else:
            bits.append(f"high in sugar/carbs ({item.sugar_g}g sugar, {item.carbs_g}g carbs) — best avoided for your sugar goal")
    elif goal == "period_friendly":
        _pts, tier, reason = period_comfort_score(item)
        if tier == "boost":
            bits.append(f"period comfort: {reason}")
        elif tier == "avoid":
            bits.append(f"caution for cramps: {reason}")
        else:
            bits.append("mild, gentle meal that is easy on cramps")
    if pair is not None:
        total = item.price + pair.price
        left = (prefs.budget - total) if prefs.budget is not None else None
        tail = f"Pair with {pair.name} (Rs {pair.price:.0f}) -> total Rs {total:.0f}"
        if left is not None:
            tail += f", leaving Rs {left:.0f} to spare."
        else:
            tail += "."
        bits.append(tail)
    return " — ".join(bits[:2]) + (". " + " ".join(b + "." if not b.endswith(".") else b for b in bits[2:]) if len(bits) > 2 else ".")


def substitutes_for(target: MenuItem, pool: list[MenuItem], prefs: UserPreferences,
                    meal: Optional[str], n: int = 3) -> list[MenuItem]:
    cands = [i for i in pool if i.availability and i.id != target.id and passes_dietary(i, prefs)]
    if prefs.avoid:
        cands = [i for i in cands
                 if not any(a in (i.name + " " + " ".join(i.ingredients)).lower()
                            for a in prefs.avoid)]
    if prefs.budget is not None:
        cands = [i for i in cands if i.price <= prefs.budget]
    def closeness(i: MenuItem) -> float:
        s = 0.0
        if i.category == target.category:
            s += 3
        if i.cuisine == target.cuisine:
            s += 2
        s += len(set(i.taste_profile) & set(target.taste_profile)) * 1.5
        s += len(set(i.mood_tags) & set(target.mood_tags))
        s -= abs(i.price - target.price) / 50.0
        s += i.popularity_score / 200.0
        return s
    cands.sort(key=closeness, reverse=True)
    return cands[:n]


def recommend(
    all_items: list[MenuItem],
    prefs: UserPreferences,
    meal: Optional[str] = None,
    top_singles: int = 3,
    top_combos: int = 2,
    rank_adjust: Optional[Any] = None,
    queue: Optional[dict] = None,
) -> dict[str, Any]:
    """Full deterministic pipeline. Never relaxes dietary/allergen filters.

    rank_adjust (optional): callable applied to the FULL ranked singles list
    (item, score, breakdown tuples) before top-N slicing — used for
    memory personalization so boosted items can enter the top 3.
    queue (optional): {counter: extra_minutes} live queues; prep checks and
    ETAs use prep + queue. None = plain prep times (deterministic).
    """
    meal = meal or prefs.meal or infer_meal_period()
    relaxed: list[str] = []

    def run(p: UserPreferences, m: Optional[str]):
        singles_pool = [i for i in all_items if not i.is_combo and passes_hard_filters(i, p, m, queue)]
        prebuilt = []
        for i in all_items:
            if not i.is_combo or not i.availability:
                continue
            if p.avoid:
                hay = (i.name + " " + " ".join(i.ingredients)).lower()
                if any(a in hay for a in p.avoid):
                    continue
            if p.budget is not None and i.price > p.budget + 1e-9:
                continue
            if p.max_prep_time is not None and effective_prep_time(i, queue) > p.max_prep_time:
                continue
            if p.cuisine and i.cuisine.value != p.cuisine:
                continue
            if m:
                st = {s.value for s in i.serving_times}
                if m not in st and "all_day" not in st:
                    continue
            if not passes_dietary(i, p):
                continue
            prebuilt.append(i)
        return singles_pool, prebuilt

    singles_pool, prebuilt = run(prefs, meal)

    # Progressive relaxation (soft constraints only).
    if not singles_pool and meal:
        relaxed.append(f"No matches for '{meal}' service — showing all-day options too.")
        singles_pool, prebuilt = run(prefs, None)
    if not singles_pool and prefs.max_prep_time is not None:
        relaxed.append(f"Nothing ready in {prefs.max_prep_time} min — relaxed to {prefs.max_prep_time + 10} min.")
        relaxed_prefs = prefs.model_copy(update={"max_prep_time": prefs.max_prep_time + 10})
        singles_pool, prebuilt = run(relaxed_prefs, meal if not relaxed else None)
        prefs = relaxed_prefs
    if not singles_pool and prefs.max_spice is not None:
        relaxed.append("Relaxed the spice cap to find matches.")
        relaxed_prefs = prefs.model_copy(update={"max_spice": None})
        singles_pool, prebuilt = run(relaxed_prefs, None)
        prefs = relaxed_prefs
    if not singles_pool and prefs.cuisine:
        relaxed.append(f"No {prefs.cuisine} matches — showing other cuisines.")
        relaxed_prefs = prefs.model_copy(update={"cuisine": None})
        singles_pool, prebuilt = run(relaxed_prefs, None)
        prefs = relaxed_prefs

    # Budget-below-cheapest path.
    cheapest_note = None
    live = sorted([i for i in all_items if i.availability and passes_dietary(i, prefs)],
                  key=lambda i: i.price)
    if prefs.budget is not None and live and prefs.budget < live[0].price:
        cheapest_note = (
            f"Your Rs {prefs.budget:.0f} budget is below our cheapest safe item "
            f"({live[0].name} at Rs {live[0].price:.0f}). Here are the closest options — "
            "top up a little or pick one to stretch to."
        )
        ranked = rank([i for i in live[:6] if not i.is_combo][:6], prefs, meal)
        singles = ranked[:top_singles]
        return {
            "meal": meal, "singles": singles, "combos": [], "dynamic_combos": [],
            "relaxed": relaxed, "cheapest_note": cheapest_note,
            "cheapest": live[:3], "conflict": detect_conflict(prefs), "prefs": prefs,
        }

    ranked_singles = rank(singles_pool, prefs, meal)
    if rank_adjust is not None:
        ranked_singles = rank_adjust(ranked_singles)
    singles = ranked_singles[:top_singles]
    if prefs.combos_only:
        singles = []  # user asked for combos only — keep singles out of the way

    # Combos: prebuilt (scored) + dynamic pairs.
    ranked_pre = rank(prebuilt, prefs, meal)
    mains = [i for i, _, _ in ranked_singles if i.category.value in ("main_course", "breakfast")] or \
            [i for i, _, _ in ranked_singles]
    side_pool = [i for i in all_items if not i.is_combo and passes_hard_filters(i, prefs, meal, queue)
                 and i.category.value in ("beverage", "snack", "dessert")]
    sides = side_pool or [i for i, _, _ in ranked_singles]
    # dietary already enforced inside passes_hard_filters
    dynamic = generate_dynamic_combos(mains, sides, prefs, meal, queue)[:4]

    combos_out: list[dict[str, Any]] = []
    for it, sc, br in ranked_pre[:top_combos]:
        combos_out.append({"item": it, "score": sc, "breakdown": br, "is_dynamic": False,
                           "total_price": it.price, "eta": effective_prep_time(it, queue)})
    # Fill remaining combo slots with dynamic pairs.
    for d in dynamic:
        if len(combos_out) >= top_combos:
            break
        combos_out.append({"items": d["items"], "name": d["name"], "score": d["score"],
                           "is_dynamic": True, "total_price": d["total_price"], "eta": d["eta"]})

    if not singles and not combos_out and live and not prefs.combos_only:
        relaxed.append("No exact matches — showing closest safe options instead.")
        fallback = rank([i for i in live if not i.is_combo][:10], prefs, meal)[:top_singles]
        singles = fallback

    # Honest goal note: when the user asked for high-protein but nothing shown
    # clears the 15g bar (e.g. tight budget), say so plainly instead of
    # headlining 4g chai as a protein pick.
    goal_note = None
    if (prefs.goal or "").lower() == "high_protein":
        shown_protein: list[float] = [i.protein_g for i, _, _ in singles]
        for c in combos_out:
            if c.get("is_dynamic"):
                shown_protein.append(sum(i.protein_g for i in c["items"]))
            elif c.get("item") is not None:
                shown_protein.append(c["item"].protein_g)
        if shown_protein and max(shown_protein) < PROTEIN_FIT_G:
            budget_txt = f"Rs {prefs.budget:.0f}" if prefs.budget is not None else "this budget"
            goal_note = (f"Heads up: nothing truly high-protein (15g+) fits {budget_txt} — "
                         "showing the highest-protein options under budget.")
            # Note: the sweet-craving nuance travels via detect_conflict, so it
            # is deliberately not repeated here.

    return {
        "meal": meal, "singles": singles, "combos": combos_out, "dynamic_raw": dynamic,
        "relaxed": relaxed, "cheapest_note": cheapest_note, "goal_note": goal_note,
        "cheapest": [], "conflict": detect_conflict(prefs), "prefs": prefs,
    }
