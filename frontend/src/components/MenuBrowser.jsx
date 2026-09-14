import React, { useEffect, useRef, useState } from 'react';
import { Search, X, Sparkles, Coffee, Utensils, Sandwich, Soup, Cake, Layers } from 'lucide-react';
import { api } from '../api.js';
import { RecommendationCard } from './RecommendationCard.jsx';
import { EmptyState, SkeletonCard } from './bits.jsx';

const CATEGORY_TABS = [
  { id: '', label: 'All Dishes', icon: Sparkles },
  { id: 'breakfast', label: 'Breakfast', icon: Coffee },
  { id: 'main_course', label: 'Main Meals', icon: Utensils },
  { id: 'snack', label: 'Snacks', icon: Sandwich },
  { id: 'beverage', label: 'Beverages', icon: Soup },
  { id: 'dessert', label: 'Desserts', icon: Cake },
  { id: 'combo', label: 'Combos', icon: Layers },
];

const CUISINES = ['', 'south_indian', 'north_indian', 'chinese', 'continental', 'street_food'];
const DIETS = ['', 'veg', 'vegan', 'jain', 'gluten_free', 'halal'];
const SORTS = [
  ['popular', '⭐ MOST POPULAR'],
  ['price_asc', '💵 PRICE: LOW TO HIGH'],
  ['price_desc', '💎 PRICE: HIGH TO LOW'],
  ['fastest', '⚡ FASTEST PREP'],
  ['protein', '💪 HIGH PROTEIN'],
  ['lightest', '🥗 LOWEST KCAL'],
  ['lowsugar', '🍬 LOWEST SUGAR'],
  ['lowcarb', '🌾 LOWEST CARBS'],
  ['fiber', '🌿 HIGHEST FIBER'],
];

const pretty = (v) => v === '' ? 'ALL' : v.replace(/_/g, ' ').toUpperCase();

function sortItems(items, sort) {
  const a = [...items];
  const n = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
  switch (sort) {
    case 'price_asc': return a.sort((x, y) => n(x.price) - n(y.price));
    case 'price_desc': return a.sort((x, y) => n(y.price) - n(x.price));
    case 'fastest': return a.sort((x, y) => n(x.prep_time_minutes) - n(y.prep_time_minutes));
    case 'protein': return a.sort((x, y) => n(y.protein_g) - n(x.protein_g));
    case 'lightest': return a.sort((x, y) => n(x.calories) - n(y.calories));
    case 'lowsugar': return a.sort((x, y) => n(x.sugar_g) - n(y.sugar_g) || n(x.calories) - n(y.calories));
    case 'lowcarb': return a.sort((x, y) => n(x.carbs_g) - n(y.carbs_g) || n(x.calories) - n(y.calories));
    case 'fiber': return a.sort((x, y) => n(y.fiber_g) - n(x.fiber_g) || n(x.calories) - n(y.calories));
    default: return a.sort((x, y) => (n(y.likes) - n(y.dislikes)) - (n(x.likes) - n(x.dislikes)) || n(y.popularity_score) - n(x.popularity_score));
  }
}

export function MenuBrowser({ onAdd, onFeedback, onAlternatives, notify, favorites, onFavorite, favOnly, onToggleFavOnly, lockedDietary }) {
  const [items, setItems] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [trending, setTrending] = useState([]);
  const [specials, setSpecials] = useState([]);
  const [excluded, setExcluded] = useState([]);
  const [f, setF] = useState({ category: '', cuisine: '', dietary: '', sort: 'popular', q: '' });
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const toggleExclude = (a) => setExcluded((prev) => prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]);
  const effDietary = lockedDietary || f.dietary;
  // Debounce search typing (350ms) + ignore out-of-order responses.
  const [debouncedQ, setDebouncedQ] = useState('');
  const seqRef = useRef(0);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(f.q), 350);
    return () => clearTimeout(t);
  }, [f.q]);

  useEffect(() => {
    const seq = ++seqRef.current;
    setLoading(true);
    api.menu({
      category: f.category || undefined,
      cuisine: f.cuisine || undefined,
      dietary: effDietary || undefined,
      exclude: excluded.length ? excluded.join(',') : undefined,
      q: debouncedQ || undefined,
      available_only: true,
    })
      .then((r) => { if (seq === seqRef.current) { setItems(sortItems(r.items || [], f.sort)); setTotalCount(r.count ?? (r.items || []).length); } })
      .catch(() => { if (seq === seqRef.current) notify && notify('MENU LOAD FAILED'); })
      .finally(() => { if (seq === seqRef.current) setLoading(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.category, f.cuisine, f.dietary, lockedDietary, excluded.join(','), debouncedQ]);

  const shown = sortItems(items, f.sort);
  const favSet = new Set(favorites || []);
  const visible = favOnly ? shown.filter((c) => favSet.has(c.id)) : shown;

  useEffect(() => {
    let live = true;
    api.trending(5).then((r) => { if (live) setTrending(r.items || []); }).catch(() => {});
    api.specials().then((r) => { if (live) setSpecials(r.items || []); }).catch(() => {});
    return () => { live = false; };
  }, []);

  const drop = (label, value, opts, onC, disabled) => (
    <label className="micro-label" style={{ display: 'flex', flexDirection: 'column', gap: 4, opacity: disabled ? 0.6 : 1 }}>
      {label}{disabled ? ' (VEG-ONLY)' : ''}
      <select
        aria-label={label} value={value} disabled={disabled} onChange={(e) => onC(e.target.value)}
        style={{
          background: 'var(--surface)', color: 'var(--text-1)',
          border: '1px solid var(--hairline)', borderRadius: 'var(--r-input)',
          padding: '10px 14px', fontFamily: 'var(--font-data)', fontSize: 12, minHeight: 44,
          boxShadow: 'var(--shadow-card)'
        }}
      >
        {opts.map(([v, l]) => <option key={String(v)} value={v}>{l}</option>)}
      </select>
    </label>
  );

  return (
    <div>
      <div className="section-head">Live Canteen Menu — Direct Discovery</div>

      {specials.length > 0 && (
        <div className="chip-row" role="group" aria-label="Today's specials" style={{ marginBottom: 10 }}>
          <span className="micro-label" style={{ alignSelf: 'center', color: 'var(--brand)' }}>TODAY'S SPECIAL:</span>
          {specials.map((t) => (
            <button key={t.id} className="chip" title={`${t.name} — Rs ${t.price}`} onClick={() => onAdd(t)}>
              {t.name} · ₹{Number(t.price).toFixed(0)}
            </button>
          ))}
        </div>
      )}

      {trending.length > 0 && (
        <div className="chip-row" role="group" aria-label="Trending dishes" style={{ marginBottom: 10 }}>
          <span className="micro-label" style={{ alignSelf: 'center' }}>TRENDING:</span>
          {trending.map((t) => (
            <button key={t.id} className="chip" title={`${t.name} — Rs ${t.price}`} onClick={() => onAdd(t)}>
              {t.name} · ₹{Number(t.price).toFixed(0)}
            </button>
          ))}
        </div>
      )}

      {/* Horizontal Category Pill Bar */}
      <div className="category-bar">
        {CATEGORY_TABS.map((cat) => {
          const Icon = cat.icon;
          const active = f.category === cat.id;
          return (
            <button
              key={cat.id}
              type="button"
              className={`cat-pill${active ? ' active' : ''}`}
              onClick={() => set('category', cat.id)}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <Icon size={14} /> {cat.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Toolbar: Search + Dropdowns */}
      <div className="menu-toolbar">
        <label className="micro-label" style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: '1 1 200px' }}>
          SEARCH DISHES
          <span style={{
            display: 'flex', gap: 8, alignItems: 'center',
            background: 'var(--surface)', border: '1px solid var(--hairline)',
            borderRadius: 'var(--r-input)', padding: '0 14px', boxShadow: 'var(--shadow-card)'
          }}>
            <Search size={16} color="var(--brand)" />
            <input
              aria-label="Search menu" placeholder="Search Maggi, Dosa, Chai..."
              value={f.q} onChange={(e) => set('q', e.target.value)}
              style={{ flex: 1, background: 'transparent', border: 'none', color: 'var(--text-1)', padding: '12px 0', minHeight: 44, outline: 'none' }}
            />
            {f.q && (
              <button type="button" aria-label="Clear search" onClick={() => set('q', '')} style={{ background: 'none', color: 'var(--text-2)', padding: 4 }}>
                <X size={16} />
              </button>
            )}
          </span>
        </label>
        {drop('CUISINE', f.cuisine, CUISINES.map((c) => [c, pretty(c)]), (v) => set('cuisine', v))}
        {drop('DIET', effDietary, DIETS.map((d) => [d, pretty(d)]), (v) => set('dietary', v), !!lockedDietary)}
        {drop('SORT BY', f.sort, SORTS, (v) => set('sort', v))}
        {onToggleFavOnly && (
          <label className="micro-label" style={{ display: 'flex', flexDirection: 'column', gap: 4, justifyContent: 'flex-end' }}>
            SAVED
            <button
              type="button" onClick={() => onToggleFavOnly(!favOnly)}
              aria-pressed={!!favOnly}
              style={{
                background: favOnly ? 'var(--brand-soft)' : 'var(--surface)', color: favOnly ? 'var(--brand)' : 'var(--text-1)',
                border: '1px solid var(--hairline)', borderRadius: 'var(--r-input)',
                padding: '10px 14px', fontFamily: 'var(--font-data)', fontSize: 12, minHeight: 44,
              }}
            >
              {favOnly ? '♥ FAVORITES' : '♡ ALL DISHES'}
            </button>
          </label>
        )}
      </div>

      <div className="chip-row" role="group" aria-label="Exclude allergens" style={{ marginBottom: 4 }}>
        <span className="micro-label" style={{ alignSelf: 'center' }}>AVOID:</span>
        {['peanuts', 'tree_nuts', 'dairy', 'gluten', 'soy', 'egg', 'seafood', 'sesame'].map((a) => (
          <button
            key={a} type="button" aria-pressed={excluded.includes(a)}
            className={`cat-pill${excluded.includes(a) ? ' active' : ''}`}
            onClick={() => toggleExclude(a)}
            title={`Exclude ${a.replace('_', ' ')}`}
          >
            NO {a.replace('_', ' ').toUpperCase()}
          </button>
        ))}
        {excluded.length > 0 && (
          <button type="button" className="chip" onClick={() => setExcluded([])}>Clear</button>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '14px 0' }}>
        <div className="micro-label mono" style={{ color: 'var(--brand)', fontWeight: 700 }}>
          {totalCount} ITEMS IN LIVE KITCHEN {visible.length < totalCount ? `· SHOWING ${visible.length}` : ''}
        </div>
      </div>

      {loading && <><SkeletonCard /><SkeletonCard /></>}
      {!loading && visible.length === 0 && <EmptyState hint={favOnly ? 'No favorites saved yet — tap the heart on any dish.' : 'No dishes match your filters — try clearing a dropdown or search query.'} />}
      <div className="menu-grid">
        {!loading && visible.map((c) => (
          <RecommendationCard key={c.id} card={c} onAdd={onAdd} onFeedback={onFeedback} onAlternatives={onAlternatives}
            isFavorite={(favorites || []).includes(c.id)} onFavorite={onFavorite} />
        ))}
      </div>
    </div>
  );
}
