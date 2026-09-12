# CampusBite — ASCII Wireframes

## Mobile (< 1024px): single column, tray as bottom sheet, filters as drawer

```
+--------------------------------------------------+
| [*] campusbite      MENU v1.0 — 48 ITEMS LIVE    |
|                         [CHAT] [ADMIN] [THEME]   |
+--------------------------------------------------+
| Good afternoon! Lunch service is on.  12:41 PM   |
| Tell me your budget and craving...               |
|                                    Hi! Rs 70,    |
|                              spicy veg  12:42 PM |
| // RECOMMENDED                                   |
| +----------------------------------------------+ |
| | Masala Maggi              ₹40.00             | |
| | [VEG]  8 MIN · 380 KCAL · MEDIUM            | |
| | [VEG] [SPICE: F F .]                        | |
| | WHY THIS v            [UP][DN]  ( ADD + )   | |
| +----------------------------------------------+ |
| +----------------------------------------------+ |
| | Maggi + Chai Study Pack   ₹50.00            | |
| | [VEG]  8 MIN · COMBO                        | |
| +----------------------------------------------+ |
| ( Under Rs 50 ) ( Less spicy ) ( Show combos )   |
+--------------------------------------------------+
| [FILTERS] [APPLY FILTERS] [CLEAR TRAY]           |
+--------------------------------------------------+
| BUDGET ₹50 / ₹70  [===========-------]           |
| [ TRAY ₹50 · 2 ITEMS · ORDER ]  <- bottom sheet  |
+--------------------------------------------------+
| [ Try: Rs 70, spicy veg, 10 mins    ] [ SEND ]   |
+--------------------------------------------------+
```

## Desktop (>= 1024px): centered chat (640px) + fixed 320px right rail

```
+----------------------------------------------------------------------------------+
| [*] campusbite        MENU v1.0 — 48 ITEMS LIVE · 12:41 PM      [CHAT][ADMIN][TH] |
+-------------------------------+--------------------------------------------------+
| CHAT (max 640px, centered)    | RAIL (320px, fixed)                            |
|                               | // YOUR TRAY                                   |
|  bot bubble ...               | BUDGET ₹50 / ₹70                               |
|  user bubble ...              | [==================----]                        |
|  // RECOMMENDED               |  Maggi ............ ₹40.00                     |
|  [ card ] [ card ]            |  Chai ............. ₹15.00                     |
|  (chips)(chips)               | TOTAL ............. ₹55.00                     |
|  [FILTERS][APPLY][CLEAR]      | ETA 8 MIN · PARALLEL PREP                      |
|  [ Filters drawer expands ]   | [CLEAR] [CONFIRM ORDER]                        |
|                               | // FILTERS                                     |
|                               | CATEGORY [........]                            |
|                               | MAX PRICE [ slider ]                           |
+-------------------------------+--------------------------------------------------+
| ADMIN (full table >= 1024px, stacked rows on mobile)                             |
| ITEM              PRICE(num, right)   STATUS (sq + LIVE/OFF)   STOCK (toggle)    |
+----------------------------------------------------------------------------------+
```

## Component file structure

```
frontend/src/
  main.jsx, App.jsx, api.js
  styles/tokens.css        # design tokens (spec 7.3, verbatim)
  styles/app.css           # all component styles (solid strokes only)
  components/
    chat.jsx               # ChatWindow, MessageBubble, TypingBubble, QuickChipRow
    RecommendationCard.jsx # RecommendationCard + Spice
    panels.jsx             # BudgetMeter, TrayPanel, FilterDrawer
    bits.jsx               # Badge, Toggle, Toast, SkeletonCard, EmptyState, DietMarker
    AdminPanel.jsx         # Admin table + analytics + add-item
```
