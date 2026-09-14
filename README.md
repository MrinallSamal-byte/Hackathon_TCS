# CampusBite — AI Conversational Canteen Recommender

An AI-powered chat assistant that helps college students decide what to eat.
It collects budget, time, mood, dietary needs and cravings in natural language
(including Hinglish and common typos like "diabetise"), filters the live
canteen menu through a deterministic engine, recommends single items **and**
budget-safe combos with data-grounded explanations, remembers each user across
visits — including health conditions like diabetes, so next time it
automatically picks lower-sugar options and gently redirects ("since you're
managing diabetes, Gulab Jamun isn't a great pick — here are better options")
when you crave something counter to your own health — and learns from every
thumbs-up, order and chat turn. Cards show peer ratings plus real
protein/carbs/sugar/fiber numbers, gym/diet/diabetic goals re-rank by data
(not keywords), live counter queues keep ETAs honest, orders can be tracked
live by token and repeated in one tap, student coupons cut the bill, and any
leftover tray budget gets filled with the best sides.

> Hybrid AI contract: the **deterministic engine** does all filtering, scoring,
> budget math and availability checks. The **LLM** (OpenRouter free-tier chain)
> only rephrases explanations and gap-fills ambiguous preferences — it can never
> invent items, prices or availability. With no API key (or exhausted quota) the
> identical rule-based flows run, so the app never breaks.

---

## Table of contents

1. [Tech stack](#1-tech-stack)
2. [System architecture](#2-system-architecture)
3. [Request lifecycle](#3-request-lifecycle-chat)
4. [Recommendation engine](#4-recommendation-engine-deterministic-core)
5. [Memory and learning](#5-memory-and-learning-remembers-every-user)
6. [Data model](#6-data-model)
7. [AI layer](#7-ai-layer-openrouter)
8. [Project structure](#8-project-structure)
9. [Setup and run](#9-setup-and-run)
10. [Supabase database setup](#10-supabase-database-setup)
11. [Supabase MCP setup for opencode (repeat steps)](#11-supabase-mcp-setup-for-opencode-repeat-steps)
12. [API reference](#12-api-reference)
13. [Conversation flows and NLU](#13-conversation-flows-and-nlu)
14. [UI design system](#14-ui-design-system)
15. [Testing](#15-testing)
16. [Configuration reference](#16-configuration-reference-env-vars)
17. [Troubleshooting](#17-troubleshooting)
18. [Roadmap](#18-roadmap)
19. [Seven new user-benefit features](#19-seven-new-user-benefit-features)
20. [Acceptance checklists](#20-acceptance-checklists)
21. [Health-aware recommendations](#21-health-aware-recommendations-diabetes--counter-to-self)
22. [Database: what lives where](#22-database-what-lives-where)
23. [AI verification (prove it works)](#23-ai-verification-prove-it-works)
24. [Responsive design matrix](#24-responsive-design-matrix)

---

## 1. Tech stack

### Backend

| Layer                | Technology                         | Why it was chosen                                                        |
|----------------------|------------------------------------|--------------------------------------------------------------------------|
| API framework        | **FastAPI** (Python 3.10+)         | Typed endpoints, auto validation via Pydantic, TestClient for tests      |
| Schemas              | **Pydantic v2**                    | Single source of truth for menu + preference validation (incl. Jain rule)|
| Recommendation core  | Pure Python (`recommender.py`)     | Zero-dependency, fully deterministic, unit-testable scoring              |
| NLU fallback         | Rule/keyword parser (`nlu.py`)     | Works offline with identical flows; regex budgets, moods, diets, times   |
| LLM provider         | **OpenRouter** via `httpx`         | One key, many free models, fallback chain, JSON mode, no extra SDK       |
| Primary database     | **Supabase Postgres** (optional)   | Managed Postgres + PostgREST + RLS; `menu_items`, `feedback_log`, `order_history`, `chat_memory` |
| Local database       | **JSON files** in `data/`          | Zero-setup default; mirror + fallback when Supabase is unset/offline     |
| Server               | **Uvicorn**                        | ASGI server with `--reload` for development                              |
| Tests                | **pytest** + FastAPI TestClient    | 56 offline-safe tests; `CAMPUSBITE_OFFLINE=1` kills network in tests     |

### Frontend

| Layer                | Technology                         | Why it was chosen                                                        |
|----------------------|------------------------------------|--------------------------------------------------------------------------|
| Framework            | **React 18 + Vite**                | Fast dev/build; component model fits cards, tray, admin                  |
| Icons                | **lucide-react** (stroke 1.5)      | Single continuous-stroke icon set; monochrome-safe; no emoji in UI       |
| Styling              | Plain CSS + CSS custom properties  | Design tokens in `tokens.css`, no hardcoded values, light-theme toggle   |
| Fonts                | **Space Grotesk** (UI) + **IBM Plex Mono** (data) | Geometric sans for text; tabular mono for prices/times/labels |
| State                | React hooks + `localStorage`       | Session id persisted client-side; prefs/tray in component state          |
| API client           | `fetch` wrapper (`src/api.js`)     | Tiny typed wrapper over the FastAPI REST endpoints                       |

### AI models (OpenRouter free tier, in chain order)

| # | Model ID                              | Role in chain / observed behaviour                              |
|---|---------------------------------------|-----------------------------------------------------------------|
| 1 | `nvidia/nemotron-3-super-120b-a12b:free` | Primary: fast, answers directly; can narrate thought → strict prompts |
| 2 | `poolside/laguna-xs-2.1:free`         | Backup reasoning model; called with reasoning off + big token budget |
| 3 | `thinkingmachines/inkling:free`       | 403 outside agentic harnesses today; kept, fails fast (~0.3 s)  |
| 4 | `thinkingmachines/inkling-small:free` | Same as above                                                   |

Override with `OPENROUTER_MODELS="a,b,c"`. Free-tier daily quota applies
(OpenRouter `free-models-per-day` 429s); every failure degrades to templates.

### Design language

"Nothing-style monochrome minimalism" (dot-matrix explicitly banned):
pure-black surfaces, 1px hairline borders, single red accent with five
permitted uses, solid-stroke geometry only. Full spec in §14.

---

## 2. System architecture

```
                              +-------------------+
                              |  React 18 + Vite  |
                              |  chat, tray,      |
                              |  filters, admin   |
                              +---------+---------+
                                        |  REST/JSON (fetch)
                                        v
  +------------------+      +---------------------+      +------------------+
  |  OpenRouter      |      |  FastAPI (app.py)   |      |  Supabase        |
  |  free-model      |<---->|  chat orchestration |<---->|  Postgres        |
  |  chain (phrasing |  AI  |  tray/order/        |  DB  |  menu, feedback, |
  |  + parse assist) |      |  feedback/admin     |      |  orders, memory  |
  +------------------+      +----------+----------+      +------------------+
                                       |
                    +------------------+------------------+
                    |                  |                  |
            +-------v-------+  +-------v-------+  +-------v-------+
            | NLU (nlu.py)  |  | Engine        |  | Memory        |
            | regex/keyword |  | (recommender) |  | (memory.py)   |
            | intent+slots  |  | hard filters, |  | session prefs,|
            | 1-2 questions |  | soft scoring, |  | likes, orders,|
            | max, then act |  | combos, Alt   |  | usual budget  |
            +---------------+  +-------+-------+  +-------+-------+
                                       |                  |
                              +--------v------------------v--------+
                              |  JSON files (data/)               |
                              |  menu_data.json = seed of truth   |
                              |  memory.json / feedback / orders  |
                              |  mirror + offline fallback        |
                              +-----------------------------------+
```

Key principles:

- **Engine authority.** `recommender.recommend()` is the only code that selects
  items. The LLM receives template text to rephrase and returns validated
  preference patches — never item ids.
- **JSON-first, Postgres when present.** Every DB write is dual-write
  (local file always, Supabase best-effort). Every DB read falls back to files.
  The app runs with zero credentials.
- **Memory on every turn.** Each `/chat`, `/feedback` and `/order` call loads
  the session memory, uses it (boosts, usual budget), records the interaction,
  and saves it back to both stores.

---

## 3. Request lifecycle (chat)

```
User: "Rs 70, spicy veg, 10 mins"
  |
  v
POST /chat { message, prefs, session_id }
  |
  +--> load memory(session_id) ............ Supabase chat_memory -> JSON mirror
  +--> detect_intent ...................... greeting | recommend | refine |
  |                                          browse | sold_out | smalltalk ...
  +--> parse_one_shot ..................... budget/time/mood/diet/craving/...
  +--> [nothing parsed?] LLM gap-fill ..... validated patch, rules win ties
  +--> [budget missing?] usual-budget ..... median of past budgets + note
  +--> recommend() ........................ hard filters -> scoring -> top 3+2
  +--> memory boosts ...................... likes +8, ordered +3, disliked -25,
  |                                          cuisine affinity +3 (re-sorts)
  +--> batch_phrase() ..................... ONE model call for all explanations
  +--> record + save memory ............... prefs/budgets/moods/chats -> DB+JSON
  |
  v
{ reply, singles[3], combos[2], prefs, chips, ai, session_id }
```

AI cost per chat turn: **max 2 model calls** (1 optional parse gap-fill +
1 batched phrasing). All other turns are pure local compute.

---

## 4. Recommendation engine (deterministic core)

### Step 1 — hard filters (ALL must pass; dietary/allergen NEVER relax)

```
availability == true
price <= budget (combos: summed total <= budget)
dietary tags safe ......... veg blocks non_veg+egg | vegan needs tag |
                            jain needs tag + no onion/garlic in ingredients |
                            gluten/dairy-free need tag + allergen absence |
                            halal: meat must carry tag | egg-free enforced |
                            optional no-onion/garlic flag
allergens ................. intersection(user allergies, item allergens) == empty
prep_time <= time limit
serving_times ............. contains current meal period OR all_day
spice <= cap, cuisine == pin (if set)
```

### Step 2 — soft scoring (weights are the spec, exactly)

| Signal              | Points | How                                        |
|---------------------|--------|--------------------------------------------|
| Mood tag match      | +30    | normalized mood in `mood_tags`             |
| Taste/craving match | +25    | craving→taste map or name/ingredient hit   |
| Popularity          | +15    | `popularity/100 * 15` (scaled)             |
| Portion fits hunger | +10    | light/medium/heavy/filling mapping         |
| Time-of-day fit     | +10    | exact meal +10, `all_day` +5               |
| Price efficiency    | +5     | `(1 - price/budget) * 5`                   |
| Nutrition goal      | +12    | `high_protein`: ≥15g protein; `low_calorie`: ≤300 kcal (soft only) |
| Memory (personal)   | +8/+3/−25/+3 | likes / ordered / disliked / cuisine affinity |

Output: **top 3 singles + top 2 combos** (prebuilt combos scored the same way
plus dynamic main+side/beverage pairs; ETA = max component prep time).

### Step 3 — explanations (templated, optionally AI-rephrased)

> "Masala Dosa (Rs 60, ~10 min) — fits your Rs 80 budget, fully vegetarian,
> and its warm, comforting profile matches your 'homesick' mood. Pair with
> filter coffee (Rs 15) → total Rs 75, leaving Rs 5 to spare."

Every number is read from the item + prefs objects. The LLM may reword; the
batch validator rejects length mismatches and empty strings.

### Step 4 — alternative strategies (decision tree)

```
item named but sold out .... 2-3 substitutes, same category/taste, all filters pass
over budget ................ cheaper swaps or rebuilt combo + new total
zero matches ............... relax meal -> time(+10m) -> spice -> cuisine (NEVER diet),
                             each relaxation stated in the reply
budget < cheapest .......... kind note + 2-3 cheapest safe items
vegan + "chicken" .......... gentle conflict flag + best vegan matches
```

---

## 5. Memory and learning (remembers every user)

### What is stored per `session_id`

```jsonc
{
  "session_id": "a1b2c3...",
  "prefs":   { "budget": 80, "dietary_restrictions": ["veg"], "...": "..." },
  "budgets": [70, 80, 90],        // last 20, for the usual-budget fallback
  "moods":   ["stressed", ...],   // last 20, for trends + tone
  "orders":  { "maggi": 3 },      // item_id -> times ordered
  "likes":   { "samosa": 1, "fries": -1 },  // from feedback
  "chats":   12,
  "favorites": ["maggi", ...],    // hearts, max 50
  "profile": {                    // explicit + auto-saved defaults (§21)
    "goal": "diabetic", "dietary_restrictions": ["veg"],
    "allergies": ["peanuts"], "budget": 80, "weekly_budget": 400,
    "health_conditions": ["diabetes"]
  },
  "health_conditions": ["diabetes"],  // auto-saved from "i have diabetise"
  "health_warned": { "gulab_jamun": 1 },  // warned-once autonomy map
  "updated_at": "2026-09-12T..."
}
```

### Updated on EVERY interaction

| Endpoint / intent            | Memory write                                     |
|------------------------------|--------------------------------------------------|
| `/chat` recommend / refine   | prefs snapshot, budget, mood, chat count         |
| `/chat` any food message     | **auto-persist stated diet/allergy/goal/condition to profile** (§21) |
| `/chat` browse / sold_out    | prefs snapshot, chat count                       |
| `/chat` greeting / exit      | touch timestamp (welcome-back detection)         |
| `/chat` health redirect      | `health_warned[item] += 1` (warn once, then autonomy) |
| `/feedback` ±1               | like/dislike entry (steers next ranking at once) |
| `/order`                     | per-item order counts (dynamic combos expanded)  |
| `/favorites` toggle          | favorites list (max 50)                          |
| `/profile` save              | explicit defaults incl. weekly budget, conditions |
| Global (all users)           | popularity ±1 per feedback (clamped 0–100)       |

Storage: Supabase `chat_memory` (`session_id` PK, `data` jsonb) when
`SUPABASE_URL` + key are set, **plus** `data/memory.json` mirror — reads try
Supabase first, writes go to both, failures are silent. The frontend keeps the
id in `localStorage` (`cb_session`) and sends it with chat/feedback/order; the
backend mints one when missing and always returns it.

### How memory improves picks

1. **Usual budget** — median of past budgets (needs ≥2) fills a missing budget:
   *"Using your usual Rs 80 budget."*
2. **Health first** — a stated condition (`"i have diabetise"`) is saved to the
   profile + DB at once; next visit the reply opens *"Keeping your diabetes in
   mind."* and every ranking uses the diabetic goal without being asked (§21).
3. **Likes first** — liked items get +8 and jump the ranking (proven in tests).
4. **Dislikes buried** — −25 demotion, still orderable if explicitly asked.
5. **Familiarity** — ordered-before +3 (capped), favourite cuisine +3 affinity.
6. **Welcome-back** — greeting acknowledges returning users.

Hard filters are untouched by all of the above: memory re-ranks, never
un-filters.

---

## 6. Data model

Menu item (53 seeded; full schema in `backend/models.py`):

```
id, name, description, price (Rs), category, cuisine,
ingredients[], allergens[8], dietary_tags[8],
availability + available_until, prep_time_minutes (2-25),
calories, protein_g, carbs_g, sugar_g, fiber_g (seeded estimates, admin-editable),
portion_size, spice_level (0-3),
taste_profile[7], mood_tags[7], serving_times[4],
popularity_score (0-100), is_combo, combo_items[]
```

Entity relationships (Postgres tables mirror the JSON files):

```
menu_items 1----< feedback_log      (item_id FK, rating +-1, comment, budget, mood, session_id)
menu_items 1----< order_history     (token UNIQUE-ish, tray text[], total, payable, coupon,
                                     discount, counter(+label), status_override, budget, eta,
                                     session_id)
sessions   1----1 chat_memory       (session_id PK, data jsonb: prefs/budgets/moods/
                                     orders/likes/favorites/profile{goal,diet,allergies,
                                     budget,weekly_budget,health_conditions}/
                                     health_conditions/health_warned/chats)
```

Full per-table breakdown (JSON file ↔ Postgres table ↔ what must never be
lost) lives in §22. Seeded menu facts: 53 items · 6 combos · 5 unavailable (sold-out path) ·
₹15–175 · 2–22 min · all 6 categories × 5 cuisines · Jain items verified
onion/garlic-free by a model validator · every item carries protein + carbs +
sugar + fiber estimates (`seed.py --validate` checks all 53).

---

## 7. AI layer (OpenRouter)

```
template explanations ──batch_phrase()──> ONE chat call ──validate──> cards
ambiguous message ──parse_prefs_with_llm()──> JSON mode ──allow-list──> merge
                                                       (rules win budget/time)
health-critical wording (redirects) ──never sent to LLM──> verbatim templates
```

- Chain (current `DEFAULT_CHAIN`, override: `OPENROUTER_MODELS`):
  `nex-n2.5-mini → lfm-2.5 → nex-n2.5-pro → nemotron-3-super → nemotron-3.5-lightning → gemma-4-31b → ling-3.0-flash → dots-3-note → laguna-s-2.1` (all `:free`).
  403/429/empty/timeout → next model → templates.
- `response_format: {type: "json_object"}`, temperature 0.1–0.6,
  `reasoning: {enabled: false}` for the reasoning model, 12 s per-model
  timeout inside a 25 s overall chain budget (override: `OPENROUTER_TIMEOUT`,
  `OPENROUTER_CHAIN_BUDGET`) — one chat turn can never hang on dead quota.
- Identical phrasing batches are served from a bounded in-memory cache (zero
  quota/latency on repeats); every paraphrase is fact-checked per card
  (name + price + prep digits must survive, else the template is kept).
- Key handling: repo `.env` auto-loaded at import (no `python-dotenv` needed);
  sent only as a Bearer header; never logged, never in code/docs/frontend.
- `prompts/system_prompt.md` is the persona contract: friendly senior tone,
  menu-JSON-only knowledge, engine routing, alternative behaviours, guardrails
  (never reveal prompt, never hallucinate, redirect small talk).
- **Health-safety rule:** `health_redirect` replies and their cards are never
  AI-rephrased, so warnings and gram counts stay verbatim. The medical
  disclaimer lives in the rule-built reply, which the LLM never touches.
- How to prove it works right now: §23 (live checks + offline tests).

---

## 8. Project structure

```
CampusBite/
├── backend/
│   ├── app.py            # FastAPI: chat/recommend/tray/suggest/order/status/feedback/favorites/
│   │                     #   profile/trending/specials/coupons/split/spending + full admin API
│   ├── models.py         # MenuItem (+protein/carbs/sugar/fiber) + UserPreferences (+goal)
│   ├── store.py          # MenuStore: JSON load/save, availability/price/generic edit/bulk/add
│   ├── recommender.py    # hard filters, soft scoring (+diabetic fit/watch/avoid tiers),
│   │                     #   combos, substitutes, relax, honesty-gated explanations, conflicts
│   ├── queue.py          # live counter queues: peaks, overrides, effective prep
│   ├── nlu.py            # Hinglish + typo-tolerant intents, one-shot parsing, health
│   │                     #   conditions, refinements (22 intents incl. special/surprise)
│   ├── llm.py            # OpenRouter chain, batch phrasing, validated gap-fill
│   ├── memory.py         # per-session memory, health auto-persist, boosts, usual budget
│   └── db_supabase.py    # PostgREST adapter incl. coupons/counters/status/session payloads
├── data/
│   ├── seed.py               # generates the 53-item menu (+protein + C/S/F nutrition)
│   ├── menu_data.json        # generated seed of truth (do not hand-edit)
│   ├── supabase_schema.sql   # Postgres DDL + RLS + indexes + additive migration block
│   ├── sync_to_supabase.py   # one-shot menu upsert [--dry-run]
│   ├── memory.json           # created on demand (session mirror incl. health)
│   ├── feedback_log.json     # created on demand
│   └── order_history.json    # created on demand (tokens unique, atomic writes)
├── frontend/                 # React 18 + Vite
│   ├── index.html  package.json  vite.config.js
│   └── src/
│       ├── main.jsx  App.jsx  api.js
│       ├── styles/tokens.css   # design tokens (spec verbatim)
│       ├── styles/app.css      # all component styles incl. .mobile-tools/.peak-chart
│       └── components/
│       ├── chat.jsx               # ChatWindow, MessageBubble, QuickChipRow
│       ├── MenuBrowser.jsx        # MENU: search(debounced)+filters+sorts(9)+allergens+specials
│       ├── RecommendationCard.jsx # cards + favorites + reviews + DETAILS modal
│       ├── panels.jsx             # BudgetMeter, TrayPanel (+coupon/split), FilterDrawer
│       ├── bits.jsx               # Badge, Toggle, Toast, Skeleton, Empty, DietMarker
│       ├── UserPanels.jsx         # tracker/orders/profile/spending/veg-toggle/specials
│       └── AdminPanel.jsx         # stock, prices, prep, queues, orders, inbox, alerts,
│                                  #   revenue, peak chart, export, duplicate dish
├── prompts/system_prompt.md  # chatbot persona contract
├── tests/                    # 121 offline tests (see §15)
├── transcripts/              # 5 sample conversations (01–05)
├── docs_WIREFRAME.md         # ASCII mobile/desktop wireframes + component map
├── requirements.txt  README.md  .env (gitignored)
```

---

## 9. Setup and run

Prerequisites: Python 3.10+, Node 18+.

```bash
# backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python data/seed.py --validate
.venv/bin/python data/seed_demo.py   # optional: realistic demo orders/reviews
                                     # (4 demo users, 7 days) so charts, inbox,
                                     # trending + spending look alive. Idempotent;
                                     # --force to reseed. Never touches the menu.
.venv/bin/python -m uvicorn backend.app:app --reload --port 8000
# docs: http://localhost:8000/docs

# frontend (new terminal)
cd frontend && npm install && npm run dev
# open http://localhost:5173  (API proxied to :8000; override with VITE_API_URL)

# tests
.venv/bin/python -m pytest tests/ -q
```

AI key: put `OPENROUTER_API_KEY=` in repo `.env` (already gitignored; the
backend loads it automatically). Without it everything still works rule-based.

---

## 10. Supabase database setup

```bash
# 1. Create a project at https://supabase.com (free tier is enough).
# 2. Open SQL editor, paste + run data/supabase_schema.sql
#    (creates menu_items, feedback_log, order_history, chat_memory
#     with RLS policies and partial/GIN indexes).
# 3. Seed the menu:
.venv/bin/python data/sync_to_supabase.py --dry-run   # preview first row
.venv/bin/python data/sync_to_supabase.py             # upsert all 53 items
# 4. Enable in the backend (.env):
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_SERVICE_KEY=<service-role key>   # server-side; anon key also works for reads
# 5. Restart uvicorn — startup loads the menu from Postgres; feedback, orders
#    and session memory dual-write there from then on (JSON stays as fallback).
```

---

## 11. Supabase MCP setup for opencode (repeat steps)

Do this in **your own terminal** (mine cannot click through the browser OAuth):

**Step 1 — add the MCP config.** It is already in place at
`~/.config/opencode/opencode.jsonc` (existing fields preserved):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": [],
  "mcp": {
    "supabase": {
      "type": "remote",
      "url": "https://mcp.supabase.com/mcp?project_ref=lqfltoxbxmfxbzhntyga&features=docs%2Caccount%2Cdatabase%2Cdebugging%2Cdevelopment%2Cfunctions%2Cbranching",
      "enabled": true
    }
  }
}
```

Verify it parses:

```bash
python3 -c "import json; print(json.load(open('$HOME/.config/opencode/opencode.jsonc')).keys())"
```

**Step 2 — authenticate** (opens your browser; approve the Supabase OAuth):

```bash
opencode mcp auth supabase
```

**Step 3 — restart opencode** (config loads once at startup; MCP tools appear
after restart). Optional agent skills:

```bash
npx skills add supabase/agent-skills
```

If auth hangs, check you are on a machine with a browser, then retry step 2.
Docs: https://opencode.ai/docs.

---

## 12. API reference

Base `http://localhost:8000`. All POST bodies are JSON.

| Method | Path | Body / query | Returns |
|--------|------|--------------|---------|
| GET | `/health` | — | ok, item/live counts, time |
| GET | `/menu` | `category, cuisine, max_price, dietary, max_spice, max_prep, available_only, q (name+desc+ingredients), goal, exclude (allergens csv), min_protein, max_calories, max_carbs, max_sugar` | count + cards (goal sorts: protein desc / calories asc / sugar+carbs asc) |
| GET | `/menu/{id}` | — | card (+ `sold_out_note` + `alternatives` when OFF) |
| GET | `/queue` | — | per-counter live wait minutes |
| GET | `/trending` | `limit` | top cards by likes + popularity |
| GET | `/specials` | — | deterministic daily 3 (stable all day, rotates daily) |
| GET | `/coupons` | — | active codes + % off |
| GET | `/order/{token}` | — | PREPARING/READY/COMPLETED/CANCELLED + items, payable, counter, elapsed |
| DELETE | `/order/{token}` | — | cancel a PREPARING order (400 once READY) |
| GET | `/orders` | `session_id, limit` | my history, newest first, with live states |
| POST | `/recommend` | `{preferences, meal?, session_id?}` | singles[3], combos[2], relaxed, conflict, cheapest path, ai, session, `health_note` when diabetic |
| POST | `/chat` | `{message (≤2000 chars), prefs?, meal_override?, session_id?}` | reply + cards + chips + prefs + ai + session (22 intents) |
| POST | `/tray/validate` | `{tray_ids, budget?, coupon_code?}` | total, discount, payable, over_budget, ETA (max prep **+ live queues**), `coupons_available` |
| POST | `/tray/suggest` | `{tray_ids, budget, prefs?}` | spent/remaining + up to 3 sides fitting the leftover (400 without budget) |
| POST | `/bill/split` | `{tray_ids, people, coupon_code?}` | total, payable, per_person + breakdown |
| POST | `/order` | `{tray_ids, budget?, session_id?, coupon_code?}` | unique `CB-###` token, total, payable, counter + label |
| POST | `/feedback` | `{item_id, rating ±1, comment? (≤500), budget?, mood?, session_id?}` | ok + new popularity + `deduped` flag (also logs to memory) |
| GET | `/feedback/{item_id}` | `limit` | likes/dislikes + recent comments |
| GET/POST | `/favorites` | `session_id` / `{item_id, session_id}` | toggle + list (max 50, memory-backed) |
| GET/POST | `/profile` | `session_id` / full patch | dietary defaults, goal, budgets, health conditions |
| GET | `/spending` | `session_id` | today + 7-day totals and counts + `by_day` (per-day totals for the chart) |
| PATCH | `/admin/items/{id}/availability` | `{available}` | updated flag (syncs to Supabase) |
| PATCH | `/admin/queue` | `{counter, minutes}` | set live queue override |
| DELETE | `/admin/queue` | — | clear all queue overrides |
| PATCH | `/admin/items/{id}/price` | `{price}` | updated price (syncs) |
| PATCH | `/admin/items/{id}` | `{price?, prep_time_minutes?, popularity_score?, calories?, protein_g?, carbs_g?, sugar_g?, fiber_g?, availability?, ...}` | updated item (validated, syncs) |
| POST | `/admin/items` | full item JSON | created id (syncs; 400 on bad taste/mood/tags) |
| POST | `/admin/items/bulk-availability` | `{ids[], available}` | updated count |
| POST | `/admin/items/mark-all-live` | — | restored count |
| GET | `/admin/orders` | `q?, limit?` | recent orders with live states (token/session search) |
| PATCH | `/admin/orders/{token}` | `{status: READY\|COMPLETED\|CANCELLED}` | override (drives user status) |
| GET | `/admin/feedback` | `limit?` | newest-first inbox with item names |
| GET | `/admin/alerts` | — | sold-outs, 8m+ queues, disliked dishes |
| GET | `/admin/export` | `kind=menu\|orders` | CSV download |
| GET | `/admin/analytics` | — | top items, orders, revenue, AOV, avg/min/max budget, mood histogram, orders-by-hour, category split, sold-out list |

Examples:

```bash
curl -s localhost:8000/health
curl -s "localhost:8000/menu?max_price=50&dietary=veg" | head -c 300
curl -s "localhost:8000/menu?max_sugar=5" | head -c 200
curl -s http://localhost:8000/specials | head -c 200
curl -s -X POST localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"I have Rs 70, want something spicy and veg, got 15 mins"}'
curl -s -X POST localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"i have diabetise","session_id":"demo-health"}'
curl -s -X POST localhost:8000/tray/validate \
  -H 'Content-Type: application/json' \
  -d '{"tray_ids":["maggi","masala_chai"],"budget":60,"coupon_code":"STUDENT10"}'
curl -s -X POST localhost:8000/order \
  -H 'Content-Type: application/json' \
  -d '{"tray_ids":["maggi","masala_chai"],"budget":60,"session_id":"demo1"}'
```

Tray math: total = Σ prices (dynamic `dyn_a__b` ids expand to parts);
ETA = max prep (parallel cooking); over-budget warns with the exact excess.

---

## 13. Conversation flows and NLU

22 intents (rule-based, typo-tolerant, Hinglish-normalized before every
parse — `diabetise→diabetes`, `protien→protein`, `alergy→allergy`,
`vegiterian→vegetarian`):

- **Greeting** — time-aware (breakfast/lunch/dinner); returning sessions get a
  welcome-back line from memory.
- **One-shot** — `"I have Rs 70, want something spicy and veg, got 15 mins"`
  parses budget + diet + craving + time at once and recommends immediately.
  Budget forms: `under 80`, `Rs 100 max`, `between 50 and 150`. Time:
  `in a hurry` → ≤5 min, `got 20 mins` → ≤20.
- **Guided** — max 1–2 clarifying questions, then recommend anyway.
- **Health-first** — `"i have diabetise"` persists diabetes to profile + DB and
  answers with lower-sugar picks + medical disclaimer (§21). Stated diets and
  allergies are remembered the same way.
- **Health redirect** — diabetic asks for Gulab Jamun by name → caring
  redirect with gram counts + fit-tier alternatives (warned once; insisting a
  second time respects autonomy with honest labels).
- **Special / Surprise** — `"today's special"` (deterministic daily 3),
  `"surprise me"` (one diet-safe random pick).
- **Orders / Tracking / Cancel / Spending / Favorites / Coupons / Profile /
  Split** — `"my orders"`, `"where is my order CB-123?"`, `"cancel my order"`,
  `"how much did I spend?"`, `"my favorites"`, `"any coupon?"`,
  `"my profile"`, `"split the bill"`.
- **Cards** — price/prep/veg badge/diet pills/allergen flags/calories/protein/
  sugar + expandable WHY THIS, DETAILS modal, reviews, favorites heart.
- **Refinements** — cheaper · less spicy · more filling · quicker · no
  onion/garlic · combos only · different cuisine · high-protein · something
  else → constraint update + re-run + change note (chips adapt to your goal).
- **Sold-out** — apology + 2–3 closest available substitutes.
- **Browse** — `"What do you have under Rs 50?"`, `"Show all veg snacks"` →
  available-only list, ranked by your goal when one is set (protein/sugar).
- **Order** — tray + budget meter + coupons, over-budget warning, unique token
  + ETA + pickup counter + payable-with-coupon message.
- **Feedback** — thumbs per card (+optional comment with ± vote) → popularity
  nudge (global) + like/dislike (personal, immediate).
- **Off-topic/nonsense** — polite redirect, never hallucinates menu facts.

---

## 14. UI design system

Home + three views share one tray: **HOME** (hero, craving launch), **CHAT**
(assistant + recommendations + mobile tools), **MENU** (direct picking:
debounced search + CATEGORY / CUISINE / DIET / SORT BY over nine sort orders —
most liked, price low/high, fastest, most protein, lightest, lowest sugar,
lowest carbs, highest fiber — allergen-avoid chips, specials + trending
strips, favorites filter, instant ADD + DETAILS modal on every card),
**ADMIN** (alerts, revenue, peak-hours chart, stock, prices, prep times,
queues, live orders, feedback inbox, export, duplicate dish).
Responsive — rail-only tools (tracker, orders, profile, coupons) are mirrored
inline on mobile, tray sheet carries its own coupon box:

| Screen | Layout |
|--------|--------|
| ≤600px phones | two-row header (all tabs fit), single column, tray bottom sheet (dismissible, coupon box), mobile tools under chat, 16px inputs (no iOS zoom), wrapped toasts |
| 700–1023px tablets | two-column MENU grid, single-column chat + mobile tools, stacked admin rows, mobile cards replace admin table <768px |
| ≥1024px laptop/desktop | 640px chat + 320px sticky rail, full admin table, layout capped at 1180px for ultrawide, peak chart full width |
| Short landscape (≤540px height) | compressed header/bubbles, full-width composer retained |
| Everywhere | `100dvh` mobile-browser heights, ≥44px targets, `prefers-reduced-motion` honored, peak chart scrolls horizontally instead of crushing |
Nothing-style monochrome, dot-matrix banned: Space Grotesk UI + IBM Plex Mono
data (tabular figures); lucide-react 1.5-stroke icons only, zero emoji;
`--bg #000` / `--surface #0D0D0D` / `--hairline #2A2A2A` / red reserved for
non-veg marker, SOLD-OUT, over-budget, destructive actions, one header accent.
Veg = white square+circle, non-veg = red square+triangle (≥16px + mono label).
Chat: white user bubbles right, `--surface-2` bot bubbles left, solid-dot
typing pulse labeled RECOMMENDING. Budget meter: 3px hairline track, white fill
(red + `OVER BUDGET +₹n` when exceeded). Cards enter fade+8px staggered 40ms;
`prefers-reduced-motion` disables transforms; focus-visible white 1px/2px
offset; ≥44px targets; `aria-live` chat log. Mobile: single column + tray
bottom sheet; ≥1024px: 640px chat + 320px rail. Light theme via
`.theme-light`. ASCII wireframes: `docs_WIREFRAME.md`.

---

## 15. Testing

```bash
.venv/bin/python -m pytest tests/ -q     # 140 tests, ~3 s, fully offline
```

| File | Covers |
|------|--------|
| `test_recommender.py` (11) | schema/counts, hard filters, allergen never-relaxed, Jain onion/garlic, vegan, scoring weights, combo math+ETA, availability toggle, Rs-5 path, vegan×chicken conflict, substitutes |
| `test_nlu.py` (7) | budget/time formats, one-shot, refinements, intents, ≤2 questions |
| `test_api.py` (6) | health/menu (+category/cuisine filters), budget respect, tray warn + order token, mid-order budget change, admin round-trip, feedback logging |
| `test_conversations.py` (10) | the 10 scripted spec conversations end-to-end |
| `test_llm.py` (10) | patch validation, merge precedence, chain fallback, offline mode, batch-phrase accept/reject |
| `test_features7.py` (24) | ratings, Hinglish, goals, queues, reorder, status, suggest + AI-response bugfix regressions |
| `test_db_supabase.py` (4) | unconfigured no-ops, row round-trip, chunked upsert, sync dry-run |
| `test_memory.py` (8) | usual budget, affinity, boost math, recorders, JSON round-trip, offline Supabase, cross-turn memory, like-boost |
| `test_top20.py` (21) | orders/cancel/favorites/profile/coupons/reviews/counter/split/trending/spending/admin-orders/status/analytics/inbox/bulk/edit/export/alerts/restock + 7 chat intents |
| `test_bugfix.py` (20) | dyn-combo ordering, unique tokens, null-money rows, prep range, profile `max_spice=0`, session echo, bad-taste rejection, specials determinism, allergen exclusion, weekly budget, surprise/special intents, diabetic honesty (tiers, disclaimer, redirect, autonomy, conflict flag), nutrition filters, admin nutrition edit, export columns, Supabase payload fields |
| `test_ai_robust.py` (9) | phrase cache hits, price/prep fact-check fallback, chain budget + early stop, spaceless dish match, diabatise alias, spaceless health-redirect end to end |
| `test_guards_gaps.py` (10) | vote dedupe, chat/comment/session-id caps, memory-map bounds, reorder flow, avoid exclusions, diabetic greeting, spending/admin daily-shape |

`tests/conftest.py` forces `CAMPUSBITE_OFFLINE=1` so the suite never touches
the network. Sample transcripts: `transcripts/01–05` (happy, budget,
sold-out, dietary, refinement).

---

## 16. Configuration reference (env vars)

| Var | Required | Default | Effect |
|-----|----------|---------|--------|
| `OPENROUTER_API_KEY` | No | — | Enables AI phrasing + parse gap-fill (auto-loaded from `.env`) |
| `OPENROUTER_MODELS` | No | nemotron, laguna, inkling, inkling-small (`:free`) | Chain order, first success wins |
| `OPENROUTER_TIMEOUT` | No | 12 (s) | Per-model HTTP timeout in the chain |
| `OPENROUTER_CHAIN_BUDGET` | No | 25 (s) | Overall deadline: no new model tried after it lapses |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | No | — | Legacy direct phrasing path |
| `ANTHROPIC_API_KEY` | No | — | Counted by `llm_available()` |
| `CAMPUSBITE_OFFLINE` | No | — | `=1` forces rule-based mode (tests set this) |
| `SUPABASE_URL` | No | — | Enables Postgres menu/memory/dual-write |
| `SUPABASE_SERVICE_KEY` | No | falls back to anon | Server-side writes (bypasses RLS) |
| `SUPABASE_ANON_KEY` | No | — | Reads when no service key |
| `VITE_API_URL` | No | `http://localhost:8000` | Frontend → backend base URL |

Secrets live only in `.env` (gitignored). Nothing secret is in code, docs,
logs or the frontend bundle.

---

## 17. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: pydantic` | Use the venv: `.venv/bin/python …` after `pip install -r requirements.txt` |
| Frontend `Backend unreachable` toast | Start uvicorn on :8000; set `VITE_API_URL` if remote |
| AI never engages (always rule-based) | Check `.env` key + unset `CAMPUSBITE_OFFLINE`; free-tier 429s fall back silently until daily reset |
| Supabase writes silently skipped | Set `SUPABASE_URL` + key, restart uvicorn; test with `sync_to_supabase.py --dry-run` |
| `opencode mcp auth` hangs | Needs a local browser; run it on your machine, approve OAuth, restart opencode |
| Menu edits vanished | `seed.py --validate` rewrites `menu_data.json`; admin edits persist otherwise |
| Tests hit network | `conftest.py` already forces offline; never set a live key expectation in tests |

---

## 18. Roadmap

- UPI/payment sandbox + live order tracking over websockets.
- Canteen rush-hour ETA multiplier from order volume.
- Per-user embeddings for taste similarity (kept explainable via tags).
- Tighter Supabase RLS (session → `auth.uid()` binding) for production.
- PWA install + push when token order is ready.

---

## 19. Seven new user-benefit features

1. **Ratings on cards.** Feedback is aggregated per item (`likes`/`dislikes`
   on every card payload) and shown as "N LIKED BY STUDENTS" with a thumbs icon.
   Same signal also feeds the admin analytics top-items list.
2. **Hinglish NLU.** ~45 aliases (`sasta→cheap`, `teekha→spicy`,
   `jaldi→hurry`, `bhukh→hunger`, `rupaye→rs`, `bina pyaaz→no onion`…)
   normalize every message before parsing, so `"sasta teekha khana 50 rupaye
   me, jaldi"` parses to budget 50 + spicy + 5 min. "Something cheap" with no
   number defaults to a Rs 60 student budget.
3. **Reorder in one tap.** Order/feedback rows carry `session_id`; `"repeat
   last order"` returns that tray as cards with a rebuild total, flags anything
   that went sold out since, and the UI's **ADD ALL** button drops it in the
   tray at once.
4. **Order status lookup.** `"where is my order CB-123?"` (or plain `"is my
   order ready?"` for the session's latest) reports PREPARING with remaining
   minutes vs READY FOR PICKUP from elapsed/ETA math. Also `GET /order/{token}`.
5. **Nutrition goals.** New `protein_g` per item (seeded estimates) +
   `goal: high_protein | low_calorie` preference (parsed from "gym", "protein",
   "diet", "low cal"…). Soft +12 re-rank, goal sentence in explanations,
   protein shown on cards (`12G PROTEIN`), `GET /menu?goal=` sorting, and a UI
   filter (HIGH-PROTEIN / LOW-CALORIE).
6. **Live queue waits.** `backend/queue.py` models 3 counters (Main/Snacks/
   Beverages) with rush-hour peaks + admin overrides. The engine filters and
   computes ETAs on prep + queue, replies note heavy counters, tray/order ETAs
   include queues, and the admin panel edits them live (`GET /queue`,
   `PATCH/DELETE /admin/queue`). Off-peak queues are zero (deterministic).
7. **Complete-my-meal.** `POST /tray/suggest {tray_ids, budget, prefs?}`
    ranks sides fitting the *remaining* budget (diet/allergen-safe) and returns
    "leaves Rs Y" cards; UI has COMPLETE MY MEAL buttons (rail + chat) and a
    suggestion section, plus a `"complete my meal"` chat intent that points at it.

Later batches (all covered in §§12–14, 21–24 and `test_top20.py` /
`test_bugfix.py`): order history + cancel + live tracking, favorites,
dietary profiles, student coupons, item reviews, pickup counters, bill split,
trending + daily specials, spending tracker + weekly limits, veg-only mode,
allergen-avoid filters, nutrition filters/sorts, full admin ops (live orders,
status overrides, feedback inbox, alerts, revenue + peak-hours analytics, CSV
export, bulk stock, duplicate dish), unique order tokens, atomic log writes,
and the health-aware engine of §21.

## 20. Acceptance checklists

Functional — all hold (see §15 for the proving tests):

- [x] Every recommendation respects budget, dietary, allergen, time, availability
- [x] Combos generated and priced within budget (ETA = max prep)
- [x] Every recommendation carries a data-grounded explanation
- [x] Unavailable/over-budget always trigger alternatives
- [x] One-shot preference parsing works
- [x] Refinement commands re-filter correctly
- [x] Memory personalizes (usual budget, likes, affinity) without relaxing filters
- [x] Runs end-to-end from §9
- [x] Abuse guards hold: same-direction repeat votes don't farm popularity
  (`deduped` flag), FIRSTORDER is one-per-user (reuse pays full total, never
  blocks), chat/comment/session-id lengths are capped, per-session memory maps
  (likes, orders, warnings, coupons) stay bounded

UI (spec 7.12):

- [x] Grep `dotted|dashed|NDot|DotMatrix|pixel|LCD` in frontend CSS/fonts/assets → zero matches
- [x] No emoji in UI; Lucide continuous-stroke icons only
- [x] Red restricted to the five permitted uses
- [x] Prices/times/labels in IBM Plex Mono tabular figures
- [x] Sold-out / over-budget / empty / loading / error states styled
- [x] Mobile + desktop layouts; AA contrast; focus rings; reduced-motion honored

Health answers (see §21, proven in `test_bugfix.py`):

- [x] Typo'd conditions (`diabetise`) still resolve to the diabetic goal
- [x] Diabetic top picks are all low-sugar; no fried/syrupy item is ever
  labeled friendly (tiers derived from per-item sugar/carbs numbers)
- [x] Every diabetic answer carries the medical disclaimer
- [x] Named sugary dish → caring redirect once, autonomy on insistence
- [x] Conditions persist to profile + DB and apply silently next visit

---

## 21. Health-aware recommendations (diabetes + counter-to-self)

Saying `"i have diabetise"` (typo tolerated) does three things at once:
`parse_goal` → `diabetic`, `parse_health_conditions` → `["diabetes"]`, and
`record_health` writes both into `profile` **and** the DB mirror, replying
*"Noted — I'll remember your diabetes for next time."* Next visit, even a
plain `"something under Rs 60"` is answered with *"Keeping your diabetes in
mind."* plus lower-sugar picks — no re-stating needed. Stated diets and
allergies persist the same way (diet replaces, allergies union); the Profile
panel shows and lets you remove saved health notes.

```
User: "i have diabetise"
  |
  v
fresh parse (no base) ──> goal=diabetic, conditions=[diabetes]
  |── record_health() ──> profile.goal=diabetic, health_conditions=[diabetes]
  |                        (memory.json + Supabase chat_memory.data, §22)
  v
recommend() with diabetic tiers ──> fit items float up, sweets sink
  |
  v
reply: "Noted — I'll remember your diabetes for next time. Here are my
        top picks (diabetic-friendly): … Note: I'm a canteen recommender,
        not a doctor — …"   + goal-aware chips
```

**Tiers** (`recommender.diabetic_fit` / `diabetic_score`, per-item numbers):

```
sugar<=10g AND carbs<=45g AND not fried AND not dessert ----> FIT (+16..22)
   (whole fruit allowed; added-sugar drinks with sugar>5g excluded)
dessert (non-fruit) OR sugar>28g ----------------------------> AVOID (-25)
sugar>15g OR carbs>60g --------------------------------------> AVOID (-10)
everything else ---------------------------------------------> WATCH (+4, "keep the portion small")
```

Explanations are tier-gated: only FIT items say *"lower-sugar pick (Xg
sugar, Yg carbs)"*; WATCH says *"keep the portion small"*; AVOID says
*"best avoided for your sugar goal"*. A fried samosa can therefore never be
called diabetic-friendly again.

**Counter-to-self** — diabetic asks for Gulab Jamun by name:

```
named item + goal==diabetic + not diabetic_fit(item)
  |
  +-- warned before? --NO--> mark warned, reply:
  |     "Since you're managing diabetes, Gulab Jamun (32g sugar, 42g carbs)
  |      isn't a great pick — it can spike blood sugar. Here are closer
  |      options you'll still enjoy: Green Tea, Peanut Masala, …"
  |     (alternatives = substitutes filtered to fit/watch, fit first;
  |      wording stays verbatim — never AI-rephrased)
  |
  +-- warned before? -YES--> normal recommend (your choice is respected;
                                honest tier labels still apply)
```

Sweet *cravings* (`"i want something sweet"`) get the same care via
`detect_conflict`: *"heavy sweets can spike blood sugar with diabetes — I'm
showing the lowest-sugar options…"* while still ranking by the tiers.

---

## 22. Database: what lives where

Two stores, one contract: **every write hits the local JSON file always and
Supabase best-effort**; every read prefers Supabase and falls back to files.
The app runs fully offline with zero credentials.

```
                        +---------------------+
                        |  FastAPI (app.py)   |
                        +----------+----------+
                                   |  dual-write (JSON always, Supabase best-effort)
                 +-----------------+------------------+
                 |                                    |
        +--------v--------+                  +--------v--------+
        |  data/*.json    |                  |  Supabase       |
        |  (source of     |  --sync_to_-->   |  Postgres       |
        |   truth offline)|  --upsert-->     |  (§10 setup)    |
        +-----------------+                  +-----------------+
```

| Data | JSON file | Postgres table | Key fields that MUST be kept |
|------|-----------|----------------|------------------------------|
| Menu | `menu_data.json` (from `seed.py`) | `menu_items` | id, price, availability, prep, calories, **protein/carbs/sugar/fiber**, tags, combos |
| Session memory | `memory.json` (`{sid: {...}}`) | `chat_memory.data` (jsonb) | prefs, budgets, moods, orders, likes, **favorites, profile{goal,diet,allergies,budgets,health_conditions}, health_conditions, health_warned**, chats |
| Orders | `order_history.json` (append; **atomic** tmp+replace writes; **unique** tokens) | `order_history` | token, tray, total, **payable, coupon, discount, counter(+label), status_override**, budget, eta, **session_id** |
| Feedback | `feedback_log.json` (append) | `feedback_log` | item_id, rating, comment, budget, mood, **session_id** |

Keeping Postgres in sync after pulling new code:

```bash
# 1. Re-run the schema (idempotent — old DBs gain ONLY the missing columns):
#    paste data/supabase_schema.sql into the Supabase SQL editor.
#    The migration block at the bottom adds protein/carbs/sugar/fiber,
#    payable/coupon/discount/counter(+label)/status_override/session_id.
# 2. Re-seed the menu (carries the nutrition estimates):
.venv/bin/python data/sync_to_supabase.py --dry-run
.venv/bin/python data/sync_to_supabase.py
```

`db_supabase.log_order` / `log_feedback` send the full new payloads (proven
in `test_bugfix.py::test_supabase_payloads_carry_new_fields`); unknown
columns can never break local flows because Supabase failures are silent and
JSON stays authoritative.

---

## 23. AI verification (prove it works)

The hybrid contract (§7) is enforced in code, not vibes:

| Claim | Where it's enforced | How to verify live |
|-------|---------------------|--------------------|
| Engine picks items, never the LLM | `recommender.recommend()` is the only selector; LLM receives template text, returns phrasing | `POST /chat` twice (key set vs `CAMPUSBITE_OFFLINE=1`): same item ids, different wording |
| No hallucinated prices/availability | `batch_phrase` prompt forbids new facts; validator rejects length mismatch/empties | `test_llm.py` (10): accept/reject paths |
| Rules beat AI on conflicts | `merge_llm_patch`: budget/time only fill gaps; validated allow-lists drop unknown enums | `test_llm.py`: merge precedence |
| Works with no key / dead quota | `openrouter_available()` gate; every failure → templates | unset key or exhaust free-tier 429s → `ai: "rule-based"`, identical flows (observed live: picks still respected budget + high-protein goal) |
| Ambiguous messages get smarter | `parse_prefs_with_llm` JSON-mode gap-fill (max 2 calls/turn) | send `"something for the gym, not much money"` with key live → goal + default budget parsed |
| Health wording can't be softened | `health_redirect` cards skip `batch_phrase`; disclaimer lives in rule-built replies | `intent == "health_redirect"` cards always carry template text |

Live probes you can run right now (backend on `:8000`):

```bash
# 1. AI on (key + quota): explanations rephrased, ai = model id
curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"Rs 80 high protein lunch","session_id":"aiprobe"}'
# 2. Same call offline: identical items, ai = "rule-based"
CAMPUSBITE_OFFLINE=1 curl -s -X POST localhost:8000/chat ...
# 3. Diabetic honesty probe (must show disclaimer + sugar<=10g top singles):
curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"i have diabetise","session_id":"healthprobe"}'
```

---

## 24. Responsive design matrix

Mobile-first CSS (`app.css`); the sticky `.rail` sidebar only exists
≥1024px, so every rail-only tool is **mirrored inline on small screens**
(`.mobile-tools`: veg toggle, live tracker, orders, profile) and the mobile
tray sheet carries its **own coupon box**.

```
 360px phone                  768px tablet                 1440px desktop
+------------+              +------------+              +----------------------+
| nav (2-row)|              | nav (full) |              | nav (full, capped)   |
+------------+              +------------+              +-----------+----------+
| chat       |              | chat       |              | chat 640  | rail 320 |
| cards      |              | cards      |              | cards     | tray     |
| chips      |              | chips      |              | chips     | tracker  |
| [tools]    |              | [tools]    |              | composer  | orders   |
| composer   |              | composer   |              |           | profile  |
+------------+              +------------+              +-----------+----------+
| tray sheet |  (coupon,    | tray sheet |              | (sheet hidden ≥1024) |
| dismissible|   dismiss)   |            |              |                      |
+------------+              +------------+              +----------------------+
MENU: 1-col   MENU: 2-col (≥680px)      ADMIN: table (≥768px) else mobile cards
```

| Screen | Verified behaviour |
|--------|--------------------|
| 360×640 phones | single column; tray bottom sheet with coupon + dismiss; mobile tools under chat; 16px inputs (no iOS zoom); peak chart scrolls horizontally (`.peak-chart`) instead of crushing |
| 768×1024 tablets | 2-col menu grid; chat single column + tools; admin mobile cards (<768px table swap) |
| 1024–1440 laptop/desktop | 640px chat + 320px sticky scrollable rail; full admin table; layout capped at 1180px |
| Short landscape ≤540px height | compressed header/bubbles, composer retained |
| Everywhere | `100dvh` heights, ≥44px targets, `prefers-reduced-motion`, focus rings, `aria-live` chat, dialog semantics on modals |
