"""Rule-based NLU — full fallback when no LLM API key is present.

Identical conversation flows in both modes. Parses one-shot preferences,
refinements, browsing, tray ops, and small talk.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Optional

from backend.models import Allergen, UserPreferences

# Hinglish -> English aliases, applied (word-boundary, multiword-first) before
# every parse step. Lets students type like they speak on campus.
HINGLISH: list[tuple[str, str]] = [
    ("bahut bhukh", "very hungry"), ("bahut bhook", "very hungry"),
    ("zyada bhukh", "very hungry"), ("ghar ka", "homely"),
    ("phir se", "again"), ("bina pyaaz", "no onion"), ("bina lehsun", "no garlic"),
    ("kam teekha", "less spicy"), ("zyada teekha", "extra spicy"),
    ("thoda teekha", "medium spice"), ("garma garam", "warm"),
    ("chhoti bhookh", "light bite"), ("choti bhookh", "light bite"),
    ("heavy khana", "very hungry"), ("nashta", "breakfast"),
    ("chai nashta", "breakfast combo"), ("pocket friendly", "cheap"),
    ("post workout", "high protein"), ("gym diet", "high protein"),
    ("bhukh", "hungry"), ("bhook", "hungry"), ("bhukha", "hungry"),
    ("jaldi", "hurry"), ("teekha", "spicy"), ("tikha", "spicy"),
    ("meetha", "sweet"), ("mitha", "sweet"), ("sasta", "cheap"), ("saste", "cheap"),
    ("thanda", "cold"), ("garam", "warm"), ("halka", "light"),
    ("shakahari", "veg"), ("anda", "egg"), ("pyaaz", "onion"), ("lehsun", "garlic"),
    ("bina", "no"), ("kam", "less"), ("zyada", "extra"),
    ("subah", "morning"), ("dopahar", "afternoon"), ("raat", "night"), ("shaam", "evening"),
    ("dikhao", "show"), ("batao", "suggest"), ("bata", "suggest"), ("chahiye", "want"),
    ("alergy", "allergy"), ("alergi", "allergy"), ("vegiterian", "vegetarian"),
    ("diabetis", "diabetes"), ("diabities", "diabetes"),
    ("diabetise", "diabetes"), ("diabatise", "diabetes"), ("diebetes", "diabetes"),
    ("periads", "periods"), ("periad", "period"), ("priods", "periods"), ("priod", "period"),
    ("perids", "periods"), ("perid", "period"), ("mensuration", "menstruation"),
    ("mensurations", "menstruation"), ("mc", "period"),
    # Common food-word typos (campus typing, no autocorrect in chat).
    ("chiken", "chicken"), ("panner", "paneer"), ("biriyani", "biryani"),
    ("momo", "momos"), ("nonveg", "non veg"),
    ("kuch", ""), ("mujhe", "i"), ("hai", "is"), ("kya", "what"), ("aur", "and"),
]

_HINGLISH_RES = [(re.compile(r"\b" + re.escape(a) + r"\b"), b) for a, b in HINGLISH]


def normalize_hinglish(text: str) -> str:
    t = f" {text.lower()} "
    for rx, rep in _HINGLISH_RES:
        t = rx.sub(f" {rep} " if rep else " ", t)
    return " ".join(t.split())


RUPEE = r"(?:₹|rs\.?|inr|rupees?|rupaye|rupya|rupaiye)"

# ---------- low-level parsers ----------

def parse_budget(text: str) -> Optional[float]:
    t = text.lower()
    m = re.search(r"between\s+(\d+)\s+and\s+(\d+)", t)
    if m:
        return float(max(int(m.group(1)), int(m.group(2))))
    # Indian "80/-" notation.
    m = re.search(r"(\d+)\s*/-", t)
    if m:
        return float(m.group(1))
    m = re.search(rf"(?:under|below)\s*{RUPEE}?\s*(\d+)", t)
    if m:
        return float(m.group(1))
    m = re.search(rf"{RUPEE}\s*(\d+)\s*(?:max|max budget|budget|only|limit)?", t)
    if m:
        # avoid matching stray numbers like "20 mins" — require rupee marker or budget word nearby
        return float(m.group(1))
    m = re.search(rf"(\d+)\s*{RUPEE}", t)
    if m:
        return float(m.group(1))
    # "100 budget" / "100 rs budget" / "100 max budget"
    m = re.search(r"(\d+)\s*(?:rs\.?|inr|rupees?)?\s*budget", t)
    if m:
        return float(m.group(1))
    # "i have 100" / "got 100" / "have 100 to spend" (not matching 20 mins)
    m = re.search(r"(?:have|got|with)\s+(?:a\s+)?(?:budget\s+of\s+)?(?:rs\.?|inr|₹)?\s*(\d+)(?!\s*(?:mins?|minutes?|sec|hours?|items?|peoples?|friends?|persons?))", t)
    if m:
        return float(m.group(1))
    m = re.search(r"budget(?: of)?\s*(?:is\s*)?(\d+)", t)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+)\s*(?:bucks|rupees?)\s*(?:max|only|budget)?", t)
    if m:
        return float(m.group(1))
    m = re.search(r"(?:max|within|around|upto|up to)\s+(?:rs\.?|inr|₹)?\s*(\d+)(?!\s*(?:mins?|minutes?))", t)
    if m:
        return float(m.group(1))
    # Spelled-out numbers ("eighty rupees", "under fifty", "one hundred twenty").
    m = re.search(rf"({_WORD_RUN})\s*(?:{RUPEE}|bucks|rupees?)", t)
    if m:
        w = _words_to_number(m.group(1))
        if w is not None:
            return w
    m = re.search(rf"(?:under|below|budget(?: of)?|max|within|around|upto|up to)\s*(?:is\s+)?(?:{RUPEE})?\s*({_WORD_RUN})", t)
    if m:
        w = _words_to_number(m.group(1))
        if w is not None:
            return w
    return None


_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
         "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORD_RUN = r"[a-z]+(?:[\s-]+[a-z]+){0,4}"


def _words_to_number(run: str) -> Optional[float]:
    """'eighty' -> 80, 'one hundred twenty' -> 120. None when no number words."""
    toks = [w for w in re.split(r"[\s-]+", run.lower()) if w and w != "and"]
    if not toks or any(w not in _ONES and w not in _TENS
                       and w not in ("hundred", "thousand") for w in toks):
        return None
    total, cur = 0, 0
    for w in toks:
        if w in _ONES:
            cur += _ONES[w]
        elif w in _TENS:
            cur += _TENS[w]
        elif w == "hundred":
            cur = (cur or 1) * 100
        elif w == "thousand":
            total += (cur or 1) * 1000
            cur = 0
    total += cur
    return float(total) if 0 < total <= 100000 else None


def parse_time(text: str) -> Optional[int]:
    text = normalize_hinglish(text)
    t = text.lower()
    if any(k in t for k in ["in a hurry", "hurry", "asap", "quick", "fast", "rush", "hurry up"]):
        return 5
    m = re.search(r"(\d+)\s*(?:mins?|minutes?)", t)
    if m:
        # A bare "10 mins" is unambiguously a time (budgets use Rs/budget
        # words, never "mins"). Cap at 60 so stray large numbers don't leak.
        v = int(m.group(1))
        if v <= 60:
            return v
    # Bare number with a time cue ("ready in 10", "dinner in 15"). Capped at
    # 60 so budget-like numbers never leak into prep time.
    m = re.search(r"(?:ready\s+)?in\s+(\d+)(?!\s*(?:rs\.?|inr|₹|bucks|rupees?|items?|peoples?|friends?|persons?))", t)
    if m and int(m.group(1)) <= 60:
        return int(m.group(1))
    m = re.search(r"got\s+(\d+)", t)
    if m:
        return int(m.group(1))
    return None


MOOD_WORDS = {
    "happy": "happy", "stressed": "stressed", "stress": "stressed", "tired": "tired",
    "homesick": "homesick", "home sick": "homesick", "nostalgic": "homesick",
    "celebrat": "celebrating", "party": "celebrating", "birthday": "celebrating",
    "exam": "exam-mode", "study": "exam-mode", "focus": "exam-mode",
    "very hungry": "very hungry", "starving": "very hungry", "hungry": "hungry",
    "period": "comfort", "cramp": "comfort", "menstruat": "comfort", "pms": "comfort",
}

def parse_mood(text: str) -> Optional[str]:
    t = normalize_hinglish(text).lower()
    for k, v in MOOD_WORDS.items():
        if k in t:
            return v
    return None


def parse_dietary_allergy(text: str) -> tuple[list[str], list[str], bool]:
    t = normalize_hinglish(text).lower()
    diet: list[str] = []
    if re.search(r"\beggetarian\b|\beggiterian\b", t):
        # Vegetarian + egg OK, meat blocked (handled in passes_dietary).
        diet.append("eggetarian")
    if re.search(r"non[\s\-_]?veg|nonveg", t):
        # Explicit "non veg" — but a vegan/jain/veg claim alongside wins
        # (keeps the vegan+craving-chicken conflict path intact).
        if not re.search(r"\bvegan\b|\bjain\b|\bvegetarian\b|pure veg", t):
            diet.append("non_veg")
    if not diet and re.search(r"\bvegan\b", t):
        diet.append("vegan")
    elif re.search(r"\bjain\b", t):
        diet.append("jain")
    elif re.search(r"vegetarian|\bveg\b|veggie|pure veg", t):
        # "non-veg"/"non veg" must not trigger veg
        if "non" not in t.split("veg")[0][-6:]:
            diet.append("veg")
    if re.search(r"egg[\s-]?free|eggless|no egg", t):
        diet.append("egg_free")
    if re.search(r"\bhalal\b", t):
        diet.append("halal")
    if re.search(r"gluten[\s-]?free", t):
        diet.append("gluten_free")
    if re.search(r"dairy[\s-]?free|lactose[\s-]?free", t):
        diet.append("dairy_free")

    allergies: list[str] = []
    # A food word alone ("i want paneer", "wheat roti", "still want ...")
    # is a craving — NOT an allergy. Only treat it as an allergy when the
    # user gives an allergy context (allerg/intoler/sensitiv/reaction or
    # can't-have phrasing). All matches use word boundaries so "til" never
    # fires on "still"/"until" and "soy" never fires inside other words.
    allergy_ctx = bool(re.search(
        r"allerg|intoler|sensitiv|reaction|can'?t\s+(have|eat)|cannot\s+(have|eat)"
        r"|not\s+allowed|avoid\s+.*allerg|no\s+.*allerg", t))
    mapping = {"peanut": "peanuts", "groundnut": "peanuts", "tree nut": "tree_nuts",
               "tree nuts": "tree_nuts",
               "almond": "tree_nuts", "cashew": "tree_nuts", "walnut": "tree_nuts",
               "pista": "tree_nuts", "pistachio": "tree_nuts",
               "dairy": "dairy", "milk": "dairy", "lactose": "dairy",
               "paneer": "dairy", "curd": "dairy", "dahi": "dairy",
               "ghee": "dairy", "malai": "dairy", "khoya": "dairy",
               "cheese": "dairy", "butter": "dairy", "cream": "dairy",
               "gluten": "gluten", "wheat": "gluten", "maida": "gluten", "atta": "gluten",
               "soy": "soy", "soya": "soy", "egg": "egg", "eggs": "egg",
               "seafood": "seafood", "fish": "seafood", "prawn": "seafood", "shrimp": "seafood",
               "sesame": "sesame", "til": "sesame"}
    for k, v in mapping.items():
        # Word-boundary match (multiword keys allow flexible whitespace).
        pat = r"\b" + r"\s+".join(re.escape(p) for p in k.split()) + r"\b"
        if not re.search(pat, t):
            continue
        if v in allergies:
            continue
        # "egg-free diet" is a restriction, not an allergy — but treat egg mention
        # with allergy words as allergy.
        if v == "egg" and ("free" in t or "eggless" in t) and "allerg" not in t:
            continue
        if v == "egg" and not re.search(r"\beggs?\b", t):
            # "eggetarian" contains "egg" but EATS egg — never an allergy.
            continue
        if v in ("dairy", "gluten") and "free" in t and "allerg" not in t:
            # "dairy-free" already captured as diet; skip allergy unless explicit
            if "allerg" not in t and "intoler" not in t:
                continue
        # Gate: without an allergy context this is just a food mention.
        if not allergy_ctx:
            continue
        allergies.append(v)
    # Generic "nut allergy" (no peanut/tree-nut word) covers both families.
    if not allergies and re.search(r"\bnuts?\b", t) and allergy_ctx:
        allergies.extend(["peanuts", "tree_nuts"])
    if re.search(r"allerg", t):
        # bare "allergy" with food word already handled; keep list as-is
        pass
    no_og = bool(re.search(r"no\s+onion|no\s+garlic|without onion|without garlic|no onion", t))
    return diet, allergies, no_og


CRAVING_WORDS = ["spicy", "sweet", "cheesy", "cheese", "tangy", "savory", "savoury",
                 "refreshing", "comfort", "comforting", "warm", "soup", "light",
                 "chocolate", "dosa", "biryani", "maggi", "momos", "noodles",
                 "coffee", "chai", "paneer", "chicken", "mutton", "egg", "fries", "brownie",
                 "lassi", "juice", "ice cream", "jalebi", "samosa", "masala",
                 "burger", "sandwich", "pasta", "thali", "chaat", "vada", "pav",
                 "uttapam", "shake", "donut", "kheer", "rasmalai", "bhaji", "kulche",
                 "puri", "omelette"]

def parse_cravings(text: str) -> list[str]:
    t = normalize_hinglish(text).lower()
    found = []
    for w in CRAVING_WORDS:
        pat = r"\b" + r"\s+".join(re.escape(p) for p in w.split()) + r"\b"
        if re.search(pat, t) and w not in found:
            if w == "egg" and "eggetarian" in t:
                continue  # the diet word, not a craving
            found.append(w)
    return found


def parse_hunger(text: str) -> Optional[str]:
    t = normalize_hinglish(text).lower()
    if any(k in t for k in ["very hungry", "starving", "really hungry", "super hungry"]):
        return "very_hungry"
    if re.search(r"\bhungry\b", t):
        return "hungry"
    if any(k in t for k in ["light bite", "light snack", "small bite", "just a bite"]):
        return "light_bite"
    # Bare "light" (e.g. "something light") means a light bite. The old guard
    # `and "light" not in ...` was inverted and never fired.
    if re.search(r"\blight\b", t):
        return "light_bite"
    return None


def parse_meal(text: str) -> Optional[str]:
    t = normalize_hinglish(text).lower()
    if "breakfast" in t or "morning" in t:
        return "breakfast"
    if "lunch" in t or "afternoon" in t:
        return "lunch"
    if "dinner" in t or "night" in t or "evening" in t:
        return "dinner"
    return None


def parse_cuisine(text: str) -> Optional[str]:
    t = text.lower().replace("-", "_").replace(" ", "_")
    for c in ["south_indian", "north_indian", "chinese", "continental", "street_food"]:
        if c in t or c.replace("_", " ") in text.lower():
            return c
    if "south" in t:
        return "south_indian"
    if "north" in t:
        return "north_indian"
    if "chinese" in t:
        return "chinese"
    if "continental" in t:
        return "continental"
    if "street" in t:
        return "street_food"
    return None


def parse_spice_cap(text: str) -> Optional[int]:
    t = normalize_hinglish(text).lower()
    if any(k in t for k in ["less spicy", "not spicy", "no spicy", "mild", "no spice"]):
        return 1
    if "medium spice" in t:
        return 2
    if "extra spicy" in t or "very spicy" in t:
        return 3
    return None


def detect_intent(text: str) -> str:
    text = normalize_hinglish(text)
    t = text.strip().lower()
    if not t or len(t) < 2:
        return "nonsense"
    if re.match(r"^(hi+|hey|hello|helo|hii+|yo|namaste|namaskar|ram ram|good (morning|afternoon|evening))\b", t):
        return "greeting"
    if re.search(r"\b(thanks|thank you|shukriya|dhanyavad)\b", t):
        return "thanks"
    if "order" not in t and "token" not in t and \
            any(k in t for k in ["bye", "exit", "quit", "done", "that's all", "tata"]):
        return "exit"
    if re.search(r"\b(repeat|reorder|again)\b", t) or "last order" in t or "same order" in t:
        # ...unless it's a QUESTION about the past ("what did I order?")
        if re.search(r"\b(what|which|when|show|tell|list)\b", t) and \
                re.search(r"\b(order|ate|eaten|eat|meal|had)\b", t):
            return "orders"
        return "reorder"
    # New real-world intents (checked before generic status/order so plurals route right).
    if re.search(r"cancel.*(cb-\d+|order)|cancel my order|cancel order", t):
        return "cancel_order"
    if re.search(r"\b(my orders|order history|past orders|recent orders|my bills|my receipts|my last meal|past meals)\b", t):
        return "orders"
    if re.search(r"\bwhat did i (order|eat|have)|what have i (ordered|eaten|had)\b", t):
        return "orders"
    if re.search(r"\b(favorit\w*|favourit\w*|wishlist|saved|my saves)\b", t):
        return "favorites"
    if re.search(r"(how much.*spend|my spending|today.*spent|week.*spent|spent today|total spent|my expenses)", t):
        return "spending"
    if re.search(r"\b(trending|most popular|bestsellers?|best sellers?|what('| i)?s popular|top dishes|most loved)\b", t):
        return "trending"
    if re.search(r"\b(coupon|coupons|discount|promo|offer|student10|festive15|firstorder)\b", t):
        return "coupon"
    if re.search(r"\b(my profile|my diet|my defaults|dietary profile|save.*(diet|profile|default)|set.*default)\b", t):
        return "profile"
    if re.search(r"\b(split.*bill|split.*tray|per person|share.*bill)\b", t):
        return "split"
    if re.search(r"\b(surprise(\s+me)?|feeling lucky|pick for me|choose for me)\b", t):
        return "surprise"
    if re.search(r"\b(specials?|deal of the day|today'?s (special|deal|offer)|today.*special)\b", t):
        return "special"
    if re.search(r"cb-\d+", t) or "my order" in t or "where" in t and "order" in t \
            or "track" in t or ("status" in t and "order" in t) \
            or ("ready" in t and ("order" in t or "token" in t or "cb-" in t
                                 or "pickup" in t or re.search(r"\b(my|food|meal|tray)\b", t))):
        return "status"
    if "complete my meal" in t or "fill my tray" in t or "with remaining" in t:
        return "suggest"
    if any(k in t for k in ["order", "checkout", "confirm", "place order", "token"]):
        return "order"
    if any(k in t for k in ["add to tray", "add ", "tray", "my tray"]):
        return "tray"
    if re.search("[\U0001F44D\U0001F44E]|feedback|rating|thumbs|review|liked|disliked", t):
        return "feedback"
    if any(k in t for k in ["what do you have", "show all", "show me", "menu", "list", "under ₹", "under rs", "options under"]):
        # browsing vs recommending: browsing asks for a list, not personalised pick
        if any(k in t for k in ["what do you have", "show all", "list", "menu"]):
            return "browse"
    if any(k in t for k in ["cheaper", "less spicy", "more filling", "quicker", "faster",
                            "different", "something else", "another", "combos only",
                            "no onion", "no garlic", "change budget", "my budget is now"]):
        return "refine"
    if any(k in t for k in ["who are you", "weather", "cricket", "movie", "joke", "python",
                            "capital of", "meaning of life", "tell me about"]):
        return "smalltalk"
    if parse_goal(t) is not None:
        return "recommend"
    if re.search(r"(₹|rs|budget|hungry|veg|vegan|jain|eggetarian|nonveg|spicy|sweet|mins?|hurry|mood|combo|snack|breakfast|lunch|dinner|allergy|cheesy|light|refreshing|comfort|chai|coffee|dosa|biryani|biriyani|maggi|momo|noodles|paneer|panner|chicken|chiken|mutton|egg|fries|soup|juice|lassi|eat|food|meal|thali|plate|protein|gym|diet|calorie|healthy|surprise|trending|popular|bestseller|best|special|diab[ea]t|sugar|keto|carb|cheap|sasta|teekha|bhukh|bhook|khana|thirsty|without|don'?t want|\bavoid\b|burger|sandwich|pasta|chaat|vada|uttapam|shake|donut|kheer|rasmalai|bhaji|kulche|puri|omelette|thali|pav|badam|orange|banana)", t):
        return "recommend"
    # Anything with a parseable budget/time/goal is a food request even without keywords.
    if parse_budget(t) is not None or parse_time(t) is not None or parse_goal(t) is not None:
        return "recommend"
    if len(t.split()) <= 3:
        # Short + unrecognized (e.g. "xyz123", "ok", "hmm") -> graceful redirect.
        return "nonsense"
    return "smalltalk"


def apply_refinement(text: str, prefs: UserPreferences, menu_names: Optional[list[str]] = None) -> tuple[UserPreferences, str]:
    """Mutate prefs per refinement command. Returns (new_prefs, note)."""
    t = text.lower()
    p = prefs.model_copy(deep=True)
    notes = []
    budget = parse_budget(text)
    if budget is not None and ("change" in t or "now" in t or "budget" in t or "cheaper" in t):
        p.budget = budget
        notes.append(f"Budget updated to Rs {budget:.0f}.")
    elif "cheaper" in t or "lower budget" in t or "reduce" in t:
        if p.budget is not None:
            p.budget = max(10.0, round(p.budget * 0.7, 0))
            notes.append(f"Lowered budget to Rs {p.budget:.0f}.")
        else:
            p.budget = 60.0
            notes.append("Set budget to Rs 60.")
    if "less spicy" in t or "mild" in t:
        p.max_spice = 1
        notes.append("Capped spice at mild (level 1).")
    if "more filling" in t or "heavier" in t or "very hungry" in t:
        p.hunger = "very_hungry"
        notes.append("Prioritising filling portions.")
    if "lighter" in t or "light " in t:
        p.hunger = "light_bite"
        notes.append("Prioritising light bites.")
    if "quicker" in t or "faster" in t or "hurry" in t:
        p.max_prep_time = 5 if p.max_prep_time is None else min(p.max_prep_time, 5)
        notes.append("Limited to 5-min items.")
    m = re.search(r"(\d+)\s*mins?", t)
    if m and ("got" in t or "have" in t or "only" in t or "within" in t):
        p.max_prep_time = int(m.group(1))
        notes.append(f"Time limit set to {m.group(1)} min.")
    if "no onion" in t or "no garlic" in t or "no onions" in t:
        p.no_onion_garlic = True
        notes.append("Excluding onion/garlic.")
    if "combos only" in t or t.strip() == "combos" or "show combos" in t:
        p.combos_only = True
        notes.append("Showing combos only.")
    if "singles" in t or "single items" in t:
        p.combos_only = False
    cuis = parse_cuisine(text)
    if cuis and "different" in t:
        p.cuisine = None
        notes.append("Cleared cuisine filter — trying others.")
    elif cuis:
        p.cuisine = cuis
        notes.append(f"Switched to {cuis.replace('_', ' ')}.")
    elif "different cuisine" in t:
        # rotate: clear cuisine so engine explores
        p.cuisine = None
        notes.append("Trying a different cuisine.")
    goal = parse_goal(text)
    if goal:
        p.goal = goal
        if goal == "diabetic":
            notes.append("Prioritising diabetic-friendly, sugar-free options.")
        elif goal == "high_protein":
            notes.append("Prioritising high-protein options.")
        elif goal == "low_calorie":
            notes.append("Prioritising low-calorie options.")
        elif goal == "period_friendly":
            notes.append("Prioritising period-comfort, iron-rich, and cramp-soothing options.")
    if not notes:
        notes.append("Shuffling to different picks with the same constraints.")
    return p, " ".join(notes)


def parse_goal(text: str) -> Optional[str]:
    """Nutrition goal: high_protein (gym/protein), low_calorie (diet/light eating), diabetic (sugar-free/low GI), or period_friendly (menstrual comfort/cramps)."""
    t = normalize_hinglish(text).lower()
    if re.search(r"\b(period|periods|periads|perids|priods|menstruat\w*|cramps?|dysmenorrhea|pms|monthly cycle)\b", t):
        return "period_friendly"
    if re.search(r"\bdiab\w*|\bsugar\b|sugar free|sugar-free|low sugar|no sugar|sugar patient|low carb|keto|sugar problem|high sugar", t):
        return "diabetic"
    if any(k in t for k in ["high protein", "high-protein", "protein rich", "gym", "muscle",
                            "bodybuild", "workout meal"]):
        return "high_protein"
    if re.search(r"\bprotein\b|\bprotien\b|\bproten\b", t):
        return "high_protein"
    if any(k in t for k in ["low cal", "low-cal", "low calorie", "weight loss", "lose weight",
                            "diet food", "on a diet", "healthy", "light diet"]):
        return "low_calorie"
    if re.search(r"\bon diet\b|\bdieting\b", t):
        return "low_calorie"
    return None


def parse_health_conditions(text: str) -> list[str]:
    """Explicit health conditions the user states about THEMSELVES.

    Only conditions the engine can act on are returned (elsewhere we must
    never pretend to manage a condition we don't model).
    """
    t = normalize_hinglish(text).lower()
    out: list[str] = []
    if (re.search(r"\bi (have|am|suffer from)\b.{0,30}\bdiab\w*", t)
            or re.search(r"\bsugar patient\b|\bmy sugar\b.*\b(high|problem)\b", t)):
        out.append("diabetes")
    if (re.search(r"\bi (have|got|am on|suffer from)\b.{0,30}\b(periods?|periads?|perids?|priods?|cramps?|menstruat\w*|pms)\b", t)
            or re.search(r"\b(my periods?|period cramps?|menstrual cramps?|on my period)\b", t)):
        out.append("periods")
    return out


# Words handled by dedicated diet/allergy flags — never double-count as avoid.
_AVOID_SKIP = {"onion", "garlic", "sugar", "egg", "veg", "vegan", "jain",
               "gluten", "dairy", "halal", "oil", "salt", "spicy", "spice"}


def parse_avoid(text: str) -> list[str]:
    """Food words the user wants EXCLUDED ("without paneer", "no cheese",
    "don't want maggi"). Capped, de-duped, diet words filtered out."""
    t = normalize_hinglish(text).lower()
    found: list[str] = []
    patterns = [
        r"\bwithout\s+([a-z][a-z ]{1,24}?)(?:,| and |\.|$)",
        r"\bdon'?t want\s+([a-z][a-z ]{1,24}?)(?:,| and |\.|$)",
        r"\bavoid\s+([a-z][a-z ]{1,24}?)(?:,| and |\.|$)",
        r"\bno\s+([a-z]{2,24})\b",
    ]
    for rx in patterns:
        for m in re.finditer(rx, t):
            chunk = m.group(1).strip()
            # keep the head noun phrase (max 2 words: "paneer", "leafy greens")
            words = [w for w in chunk.split() if w not in
                     {"any", "with", "the", "a", "an", "please", "food", "items", "dish"}]
            words = words[:2]
            if not words:
                continue
            term = " ".join(words)
            if term in _AVOID_SKIP or len(term) < 2:
                continue
            if term not in found:
                found.append(term)
            if len(found) >= 4:
                return found
    return found


def parse_one_shot(text: str, base: Optional[UserPreferences] = None) -> UserPreferences:
    text = normalize_hinglish(text)
    p = (base.model_copy(deep=True) if base else UserPreferences())
    budget = parse_budget(text)
    if budget is not None:
        p.budget = budget
    elif re.search(r"\b(cheap|sasta|budget)\b", text.lower()) and p.budget is None:
        p.budget = 60.0  # "something cheap" with no number -> sensible student default
    tm = parse_time(text)
    if tm is not None:
        p.max_prep_time = tm
    mood = parse_mood(text)
    if mood:
        p.mood = mood
    diet, allergies, no_og = parse_dietary_allergy(text)
    for d in diet:
        if d not in p.dietary_restrictions:
            p.dietary_restrictions.append(d)
    for a in allergies:
        try:
            enum_val = Allergen(a)
        except ValueError:
            continue
        if enum_val not in p.allergies:
            p.allergies.append(enum_val)
    if no_og:
        p.no_onion_garlic = True
    cravings = parse_cravings(text)
    for c in cravings:
        if c not in p.cravings:
            p.cravings.append(c)
    for a in parse_avoid(text):
        if a not in p.avoid:
            p.avoid.append(a)
    hunger = parse_hunger(text)
    if hunger:
        p.hunger = hunger
    meal = parse_meal(text)
    if meal:
        p.meal = meal
    cuis = parse_cuisine(text)
    # only set cuisine if explicitly a cuisine request, not via "different"
    if cuis and "cuisine" in text.lower() or cuis and any(k in text.lower() for k in ["south", "north", "chinese", "continental", "street"]):
        p.cuisine = cuis
    spice = parse_spice_cap(text)
    if spice is not None:
        p.max_spice = spice
    goal = parse_goal(text)
    if goal:
        p.goal = goal
        if goal == "period_friendly" and not p.mood:
            p.mood = "comfort"
    if "combo" in text.lower():
        short = len(text.split()) <= 3
        p.combos_only = "only" in text.lower() or "combos only" in text.lower() or short
    return p


def clarifying_questions(prefs: UserPreferences) -> list[str]:
    """Max 1-2 questions, then recommend — never interrogate."""
    qs = []
    if prefs.budget is None:
        qs.append("What's your budget? (e.g. under Rs 80)")
    # Only ask ONE more: time or diet if both missing and no cravings at all
    if prefs.max_prep_time is None and not prefs.cravings and len(qs) < 2:
        qs.append("How much time do you have? (e.g. 10 mins, or 'in a hurry')")
    return qs[:2]


def smalltalk_reply() -> str:
    return ("I'm your CampusBite food buddy — I only know the live canteen menu, "
            "but I can find you something tasty within budget. Tell me your budget "
            "and craving (e.g. 'Rs 70, spicy veg, 10 mins'), or try 'Show combos under Rs 100'.")


def nonsense_reply() -> str:
    return ("Hmm, I didn't catch that. I can help with food: share a budget like "
            "'under Rs 80', a craving like 'spicy' or 'sweet', and time like '10 mins'. "
            "Or tap a quick chip to start.")
