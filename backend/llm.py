"""CampusBite AI layer — OpenRouter (free-tier chain) with rule-based fallback.

Architecture (unchanged contract):
- The DETERMINISTIC engine (recommender.py) always picks items from the real
  menu data. The LLM never invents items, prices, or availability.
- The LLM does: (1) warm rephrasing of template explanations,
  (2) gap-filling preference extraction on ambiguous messages.
- Every LLM output is validated; unknown enums/ids are dropped and the
  rule-based result always wins on conflicts. Without any API key the
  identical template/rule flows run.

Live probe notes (Sep 2026, free tier):
- nvidia/nemotron-3-super-120b-a12b:free .... answers fast; can narrate its
  thinking, so prompts demand direct output + JSON mode for parsing.
- poolside/laguna-xs-2.1:free ................ reasoning model; may return
  empty content when starved of tokens -> generous max_tokens, reasoning off.
- thinkingmachines/inkling:free + inkling-small:free -> HTTP 403 outside
  agentic harnesses; kept in the chain (fail fast ~0.3s) in case access opens.
Chain order below tries working models first for latency; override with
OPENROUTER_MODELS="model-a,model-b".
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

# ---------- env ----------

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_CHAIN = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "poolside/laguna-xs-2.1:free",
    "thinkingmachines/inkling:free",
    "thinkingmachines/inkling-small:free",
]

# Strict allow-lists for anything the LLM may return.
VALID_MOODS = {"energizing", "comfort", "light", "indulgent", "study_fuel",
               "homesick", "celebratory", "happy", "stressed", "tired",
               "celebrating", "exam-mode", "hungry", "very hungry"}
VALID_DIET = {"veg", "vegetarian", "vegan", "jain", "egg_free",
              "halal", "gluten_free", "dairy_free"}
VALID_ALLERGY = {"peanuts", "tree_nuts", "dairy", "gluten",
                 "soy", "egg", "seafood", "sesame"}
VALID_HUNGER = {"light_bite", "light", "medium", "hungry",
                "very_hungry", "very hungry"}
VALID_GOAL = {"high_protein", "low_calorie"}
VALID_MEAL = {"breakfast", "lunch", "dinner"}
VALID_CUISINE = {"south_indian", "north_indian", "chinese",
                 "continental", "street_food"}


def ensure_env() -> None:
    """Minimal .env loader (no dependency): fills missing vars from repo .env."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip()
    except Exception:
        pass


ensure_env()


def get_model_chain() -> list[str]:
    raw = os.getenv("OPENROUTER_MODELS", "")
    if raw.strip():
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(DEFAULT_CHAIN)


def openrouter_available() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY"))


def llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
                or openrouter_available())


# ---------- transport ----------

def _post_openrouter(model: str, messages: list[dict], max_tokens: int,
                     temperature: float, json_mode: bool) -> Optional[str]:
    """Single OpenRouter call. Returns message content or None on any failure."""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        import httpx
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        # Don't burn the token budget on hidden reasoning traces.
        payload["reasoning"] = {"enabled": False, "exclude": True}
        r = httpx.post(
            _OPENROUTER_URL, timeout=30,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": "http://localhost:8000",
                     "X-Title": "CampusBite"},
            json=payload,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        content = (choices[0].get("message") or {}).get("content")
        if not content or not str(content).strip():
            return None
        return str(content).strip()
    except Exception:
        return None


def complete(messages: list[dict], max_tokens: int = 220,
             temperature: float = 0.5,
             json_mode: bool = False) -> tuple[Optional[str], str]:
    """Try each model in the chain. Returns (text_or_None, model_used_or_rule)."""
    if os.getenv("CAMPUSBITE_OFFLINE") == "1":
        return None, "rule-based"
    if not openrouter_available():
        return None, "rule-based"
    for model in get_model_chain():
        out = _post_openrouter(model, messages, max_tokens, temperature, json_mode)
        if out:
            return out, model.split("/")[-1]
    return None, "rule-based"


# ---------- feature 1: warm phrasing (batched: ONE call per recommendation) ----------

_PHRASE_SYSTEM = (
    "You are CampusBite, a friendly college-canteen assistant. "
    "Rephrase each food recommendation text warmly and concisely "
    "(1-2 sentences each). Rules: keep EVERY fact identical (names, Rs prices, "
    "minutes, dietary words); never add or invent items, prices, or "
    "availability; reply with ONLY a JSON array of strings in the same order, "
    "no preamble, no thinking out loud."
)


def batch_phrase(texts: list[str]) -> tuple[list[str], str]:
    """Phrase N explanations in a single model call. Returns (texts, model).
    Any failure (quota, mismatch, empty) returns the originals + rule-based."""
    if not texts or not openrouter_available():
        return texts, "rule-based"
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    out, model = complete(
        [{"role": "system", "content": _PHRASE_SYSTEM},
         {"role": "user", "content": f"Rephrase these {len(texts)} texts:\n{numbered}"}],
        max_tokens=min(1200, 150 * len(texts) + 100), temperature=0.6,
        json_mode=True)
    if not out:
        return texts, "rule-based"
    try:
        start, end = out.index("["), out.rindex("]")
        arr = json.loads(out[start:end + 1])
        if (isinstance(arr, list) and len(arr) == len(texts)
                and all(isinstance(s, str) and s.strip() for s in arr)):
            return [s.strip() for s in arr], model
    except (ValueError, json.JSONDecodeError):
        pass
    return texts, "rule-based"


def phrase_explanation(template_text: str) -> str:
    if openrouter_available():
        texts, _ = batch_phrase([template_text])
        if texts:
            return texts[0]
    legacy = phrase_with_llm(template_text)
    return legacy or template_text


def phrase_with_llm(prompt: str) -> Optional[str]:
    """Legacy OpenAI direct path (kept for OPENAI_API_KEY users)."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        import json as _json
        import urllib.request
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        body = _json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": _PHRASE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 220,
            "temperature": 0.6,
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body, headers={"Authorization": f"Bearer {key}",
                                "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = _json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


# ---------- feature 2: preference gap-filling ----------

_PARSE_SYSTEM = (
    "Extract canteen-order preferences from the student's message. "
    "Reply with ONLY a JSON object (no markdown, no commentary) using "
    "these optional keys: budget (number, rupees max), max_prep_time "
    "(number, minutes), mood (one of: happy, stressed, tired, homesick, "
    "celebrating, exam-mode, hungry, very hungry), dietary_restrictions "
    "(array, any of: veg, vegan, jain, egg_free, halal, gluten_free, "
    "dairy_free), allergies (array, any of: peanuts, tree_nuts, dairy, "
    "gluten, soy, egg, seafood, sesame), cravings (array of short food "
    "words), hunger (one of: light_bite, medium, hungry, very_hungry), "
    "meal (one of: breakfast, lunch, dinner), cuisine (one of: "
    "south_indian, north_indian, chinese, continental, street_food), "
    "max_spice (0-3), combos_only (boolean), no_onion_garlic (boolean), "
    "goal (one of: high_protein, low_calorie). "
    "Omit keys you are unsure about. Never invent menu items."
)


def _as_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip().lower() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip().lower()]
    return []


def validate_patch(patch: Any) -> dict[str, Any]:
    """Keep only known-good fields/values. Unknown -> dropped."""
    if not isinstance(patch, dict):
        return {}
    clean: dict[str, Any] = {}
    try:
        if patch.get("budget") is not None:
            b = float(patch["budget"])
            if 0 <= b <= 100000:
                clean["budget"] = b
    except (TypeError, ValueError):
        pass
    try:
        if patch.get("max_prep_time") is not None:
            t = int(float(patch["max_prep_time"]))
            if 0 < t <= 180:
                clean["max_prep_time"] = t
    except (TypeError, ValueError):
        pass
    mood = str(patch.get("mood", "")).strip().lower()
    if mood in VALID_MOODS:
        clean["mood"] = mood
    diet = [d for d in _as_list(patch.get("dietary_restrictions")) if d in VALID_DIET]
    if diet:
        clean["dietary_restrictions"] = diet
    allergy = [a for a in _as_list(patch.get("allergies")) if a in VALID_ALLERGY]
    if allergy:
        clean["allergies"] = allergy
    craves = [c for c in _as_list(patch.get("cravings")) if len(c) <= 30][:6]
    if craves:
        clean["cravings"] = craves
    hunger = str(patch.get("hunger", "")).strip().lower()
    if hunger in VALID_HUNGER:
        clean["hunger"] = hunger
    meal = str(patch.get("meal", "")).strip().lower()
    if meal in VALID_MEAL:
        clean["meal"] = meal
    cuisine = str(patch.get("cuisine", "")).strip().lower().replace(" ", "_").replace("-", "_")
    if cuisine in VALID_CUISINE:
        clean["cuisine"] = cuisine
    try:
        if patch.get("max_spice") is not None:
            s = int(patch["max_spice"])
            if 0 <= s <= 3:
                clean["max_spice"] = s
    except (TypeError, ValueError):
        pass
    if isinstance(patch.get("combos_only"), bool):
        clean["combos_only"] = patch["combos_only"]
    if isinstance(patch.get("no_onion_garlic"), bool):
        clean["no_onion_garlic"] = patch["no_onion_garlic"]
    goal = str(patch.get("goal", "")).strip().lower()
    if goal in VALID_GOAL:
        clean["goal"] = goal
    return clean


def _extract_json(text: str) -> Optional[dict]:
    try:
        start, end = text.index("{"), text.rindex("}")
        obj = json.loads(text[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except (ValueError, json.JSONDecodeError):
        return None


def parse_prefs_with_llm(message: str) -> tuple[dict[str, Any], str]:
    """LLM gap-fill pass. Returns (validated_patch, model_used). Empty if N/A."""
    if not openrouter_available() or not message.strip():
        return {}, "rule-based"
    out, model = complete(
        [{"role": "system", "content": _PARSE_SYSTEM},
         {"role": "user", "content": message[:800]}],
        max_tokens=300, temperature=0.1, json_mode=True)
    if not out:
        return {}, "rule-based"
    patch = validate_patch(_extract_json(out))
    return patch, model


def merge_llm_patch(base_prefs: Any, patch: dict[str, Any]) -> Any:
    """Rule-based base wins on direct conflicts for budget/time; LLM fills gaps
    and appends list values (dietary/allergies/cravings)."""
    if not patch:
        return base_prefs
    p = base_prefs.model_copy(deep=True)
    if patch.get("budget") is not None and p.budget is None:
        p.budget = patch["budget"]
    if patch.get("max_prep_time") is not None and p.max_prep_time is None:
        p.max_prep_time = patch["max_prep_time"]
    for key in ("mood", "hunger", "meal", "cuisine", "max_spice"):
        if patch.get(key) is not None and not getattr(p, key, None):
            setattr(p, key, patch[key])
    for key in ("dietary_restrictions", "cravings"):
        for v in patch.get(key, []):
            if v not in getattr(p, key):
                getattr(p, key).append(v)
    for a in patch.get("allergies", []):
        if a not in [str(x).split(".")[-1].lower() for x in p.allergies]:
            try:
                from backend.models import Allergen
                p.allergies.append(Allergen(a))
            except ValueError:
                pass
    if patch.get("combos_only") and not p.combos_only:
        p.combos_only = True
    if patch.get("no_onion_garlic"):
        p.no_onion_garlic = True
    if patch.get("goal") and not getattr(p, "goal", None):
        p.goal = patch["goal"]
    return p
