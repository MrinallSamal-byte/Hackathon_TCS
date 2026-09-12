import React, { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { api } from '../api.js';
import { RecommendationCard } from './RecommendationCard.jsx';
import { EmptyState, SkeletonCard } from './bits.jsx';

const CATS = ['', 'breakfast', 'main_course', 'snack', 'beverage', 'dessert', 'combo'];
const CUISINES = ['', 'south_indian', 'north_indian', 'chinese', 'continental', 'street_food'];
const DIETS = ['', 'veg', 'vegan', 'jain', 'gluten_free', 'halal'];
const SORTS = [
  ['popular', 'MOST LIKED'],
  ['price_asc', 'PRICE: LOW TO HIGH'],
  ['price_desc', 'PRICE: HIGH TO LOW'],
  ['fastest', 'FASTEST FIRST'],
  ['protein', 'MOST PROTEIN'],
  ['lightest', 'LIGHTEST (KCAL)'],
];

const pretty = (v) => v === '' ? 'ALL' : v.replace(/_/g, ' ').toUpperCase();

function sortItems(items, sort) {
  const a = [...items];
  switch (sort) {
    case 'price_asc': return a.sort((x, y) => x.price - y.price);
    case 'price_desc': return a.sort((x, y) => y.price - x.price);
    case 'fastest': return a.sort((x, y) => x.prep_time_minutes - y.prep_time_minutes);
    case 'protein': return a.sort((x, y) => (y.protein_g || 0) - (x.protein_g || 0));
    case 'lightest': return a.sort((x, y) => x.calories - y.calories);
    default: return a.sort((x, y) => (y.likes - y.dislikes) - (x.likes - x.dislikes) || y.popularity_score - x.popularity_score);
  }
}

export function MenuBrowser({ onAdd, onFeedback, onAlternatives, notify }) {
  const [items, setItems] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [f, setF] = useState({ category: '', cuisine: '', dietary: '', sort: 'popular', q: '' });
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    let live = true;
    setLoading(true);
    api.menu({
      category: f.category || undefined,
      cuisine: f.cuisine || undefined,
      dietary: f.dietary || undefined,
      q: f.q || undefined,
      available_only: true,
    })
      .then((r) => { if (live) { setItems(sortItems(r.items || [], f.sort)); setTotalCount(r.count ?? (r.items || []).length); } })
      .catch(() => notify && notify('MENU LOAD FAILED'))
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.category, f.cuisine, f.dietary, f.q]);

  const shown = sortItems(items, f.sort);

  const drop = (label, value, opts, onC) => (
    <label className="micro-label" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {label}
      <select
        aria-label={label} value={value} onChange={(e) => onC(e.target.value)}
        style={{ background: 'var(--surface)', color: 'var(--text-1)', border: '1px solid var(--hairline)', borderRadius: 'var(--r-input)', padding: '10px', fontFamily: 'var(--font-data)', fontSize: 12, minHeight: 44 }}
      >
        {opts.map(([v, l]) => <option key={l} value={v}>{l}</option>)}
      </select>
    </label>
  );

  return (
    <div>
      <div className="section-head">// BROWSE MENU — PICK DIRECTLY</div>
      <div className="menu-toolbar">
        <label className="micro-label" style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: '1 1 160px' }}>
          SEARCH
          <span style={{ display: 'flex', gap: 6, alignItems: 'center', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 'var(--r-input)', padding: '0 10px' }}>
            <Search size={16} strokeWidth={1.5} />
            <input
              aria-label="Search menu" placeholder="dosa, maggi, chai…"
              value={f.q} onChange={(e) => set('q', e.target.value)}
              style={{ flex: 1, background: 'transparent', border: 'none', color: 'var(--text-1)', padding: '12px 0', minHeight: 44 }}
            />
          </span>
        </label>
        {drop('CATEGORY', f.category, CATS.map((c) => [c, pretty(c)]), (v) => set('category', v))}
        {drop('CUISINE', f.cuisine, CUISINES.map((c) => [c, pretty(c)]), (v) => set('cuisine', v))}
        {drop('DIET', f.dietary, DIETS.map((d) => [d, pretty(d)]), (v) => set('dietary', v))}
        {drop('SORT BY', f.sort, SORTS, (v) => set('sort', v))}
      </div>
      <div className="micro-label mono" style={{ margin: '10px 0' }}>{totalCount} ITEMS LIVE{shown.length < totalCount ? ` · SHOWING ${shown.length}` : ''}</div>
      {loading && <><SkeletonCard /><SkeletonCard /></>}
      {!loading && shown.length === 0 && <EmptyState hint="No dishes match — clear a dropdown or the search." />}
      <div className="menu-grid">
        {!loading && shown.map((c) => (
          <RecommendationCard key={c.id} card={c} onAdd={onAdd} onFeedback={onFeedback} onAlternatives={onAlternatives} />
        ))}
      </div>
    </div>
  );
}
