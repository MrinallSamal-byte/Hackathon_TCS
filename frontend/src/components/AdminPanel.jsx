import React, { useEffect, useState, useMemo, useRef } from 'react';
import {
  RefreshCw, Plus, Store, Clock, TrendingUp, ShoppingBag,
  CheckCircle2, AlertCircle, Search, Sparkles, Check, RotateCcw, Copy
} from 'lucide-react';
import { api } from '../api.js';
import { Toggle, DietMarker } from './bits.jsx';

export function AdminPanel({ notify }) {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [queues, setQueues] = useState([]);
  const [alerts, setAlerts] = useState(null);
  const [orders, setOrders] = useState([]);
  const [inbox, setInbox] = useState([]);
  const [orderQuery, setOrderQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [filterCat, setFilterCat] = useState('all'); // 'all' | 'live' | 'sold_out' | 'snack' | 'main_course' | 'beverage'
  const [editingPrices, setEditingPrices] = useState({});
  const [editingPrep, setEditingPrep] = useState({});
  // Debounce queue-slider persists (drag fires dozens of onChange/sec);
  // togglingRef serializes rapid stock double-taps.
  const queueTimers = useRef({});
  const togglingRef = useRef({});
  useEffect(() => () => { Object.values(queueTimers.current).forEach(clearTimeout); }, []);

  const [form, setForm] = useState({
    id: '',
    name: '',
    price: 50,
    category: 'snack',
    cuisine: 'north_indian',
    prep_time_minutes: 10,
    calories: 250,
    portion_size: 'medium',
    spice_level: 1,
    popularity_score: 80,
    dietary: 'veg'
  });

  const load = async () => {
    setLoading(true);
    try {
      const m = await api.menu({ available_only: false });
      setItems(m.items || []);
      try { setStats(await api.analytics()); } catch { setStats(null); }
      try { setQueues((await api.queues()).queues || []); } catch { /* ignore */ }
      try { setAlerts(await api.adminAlerts()); } catch { setAlerts(null); }
      try { setOrders((await api.adminOrders('', 30)).orders || []); } catch { /* ignore */ }
      try { setInbox((await api.adminFeedback(20)).feedback || []); } catch { /* ignore */ }
    } catch (e) {
      notify('Failed to load canteen data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (it) => {
    if (togglingRef.current[it.id]) return; // drop double-taps while a toggle is in flight
    togglingRef.current[it.id] = true;
    const nextState = !it.availability;
    setItems((prev) => prev.map((item) => item.id === it.id ? { ...item, availability: nextState } : item));
    try {
      await api.setAvailability(it.id, nextState);
      notify(`${it.name} → ${nextState ? 'LIVE IN KITCHEN' : 'MARKED SOLD OUT'}`);
    } catch (e) {
      notify(`Failed to update ${it.name}`);
      load();
    } finally {
      togglingRef.current[it.id] = false;
    }
  };

  const handlePriceChange = (id, val) => {
    setEditingPrices((prev) => ({ ...prev, [id]: val }));
  };

  const savePrice = async (it, priceVal) => {
    const val = Number(priceVal);
    if (!Number.isFinite(val) || val < 0) { notify(`Invalid price for ${it.name} — enter ₹0 or more`); return; }
    if (val === it.price) return;
    try {
      await api.setPrice(it.id, val);
      setItems((prev) => prev.map((item) => item.id === it.id ? { ...item, price: val } : item));
      setEditingPrices((prev) => { const n = { ...prev }; delete n[it.id]; return n; });
      notify(`${it.name} price updated to ₹${val}`);
    } catch (e) {
      notify(`Could not update price for ${it.name}`);
      load();
    }
  };

  const setQueueWait = async (counter, mins, opts = {}) => {
    const clamped = Math.max(0, Math.min(60, mins));
    setQueues((prev) => prev.map((q) => q.counter === counter ? { ...q, wait_minutes: clamped } : q));
    if (opts.defer) {
      // Slider drag: persist once the user pauses (500ms), not per pixel.
      clearTimeout(queueTimers.current[counter]);
      queueTimers.current[counter] = setTimeout(() => setQueueWait(counter, clamped), 500);
      return;
    }
    try {
      await api.setQueue(counter, clamped);
      notify(`${counter} queue set to ${clamped} mins`);
    } catch (e) {
      notify('Failed to update queue');
      load();
    }
  };

  const resetAllQueues = async () => {
    try {
      await api.clearQueue();
      notify('All counter queues reset to 0m');
      load();
    } catch (e) {
      notify('Failed to reset queues');
    }
  };

  const markAllLive = async () => {
    const soldOut = items.filter((i) => !i.availability);
    if (soldOut.length === 0) {
      notify('All dishes are already live!');
      return;
    }
    try {
      const r = await api.markAllLive();
      notify(`${r.restored ?? soldOut.length} dishes restored LIVE`);
      load();
      return;
    } catch { /* fall back to per-item loop below */ }
    setItems((prev) => prev.map((i) => ({ ...i, availability: true })));
    notify(`Setting ${soldOut.length} dishes live...`);
    for (const it of soldOut) {
      try {
        await api.setAvailability(it.id, true);
      } catch { /* ignore individual fails */ }
    }
    notify('All canteen dishes are now LIVE');
    load();
  };

  const markFilteredLive = async () => {
    const ids = filteredItems.filter((i) => !i.availability).map((i) => i.id);
    if (!ids.length) { notify('No sold-out dishes in this filter'); return; }
    try {
      await api.bulkAvailability(ids, true);
      notify(`${ids.length} FILTERED DISHES LIVE`);
      load();
    } catch { notify('Bulk update failed'); }
  };

  const savePrep = async (it, val) => {
    const mins = Number(val);
    // Backend contract (MenuItem): integer 2..25 min.
    if (!Number.isInteger(mins) || mins < 2 || mins > 25) {
      if (String(val ?? '').trim() !== '' && mins !== it.prep_time_minutes) {
        notify(`Invalid prep time for ${it.name} — enter 2–25 min`);
      }
      setEditingPrep((prev) => { const n = { ...prev }; delete n[it.id]; return n; });
      return;
    }
    if (mins === it.prep_time_minutes) return;
    try {
      await api.editItem(it.id, { prep_time_minutes: mins });
      setItems((prev) => prev.map((item) => item.id === it.id ? { ...item, prep_time_minutes: mins } : item));
      notify(`${it.name} prep time → ${mins}m`);
    } catch { notify(`Could not update prep for ${it.name}`); load(); }
  };

  const setOrderState = async (token, status) => {
    try {
      await api.setOrderStatus(token, status);
      notify(`ORDER ${token} → ${status}`);
      setOrders((prev) => prev.map((o) => o.token === token ? { ...o, state: status } : o));
    } catch { notify('Order status update failed'); }
  };

  const duplicateDish = async (it) => {
    const base = `${it.id}_copy`;
    let slug = base;
    const taken = new Set(items.map((i) => i.id));
    let n = 2;
    while (taken.has(slug)) { slug = `${base}${n}`; n += 1; }
    try {
      await api.addItem({
        id: slug, name: `${it.name} (Copy)`, price: it.price,
        category: it.category, cuisine: it.cuisine,
        description: it.description || 'Freshly prepared at campus counter',
        ingredients: it.ingredients || [], allergens: it.allergens || [],
        dietary_tags: it.dietary_tags || ['veg'],
        availability: true, available_until: it.available_until || null,
        prep_time_minutes: it.prep_time_minutes, calories: it.calories,
        protein_g: it.protein_g || 0, portion_size: it.portion_size,
        spice_level: it.spice_level, taste_profile: it.taste_profile || ['savory'],
        mood_tags: it.mood_tags || ['comfort'], serving_times: it.serving_times || ['all_day'],
        popularity_score: it.popularity_score ?? 50,
        is_combo: false, combo_items: [],
      });
      notify(`${it.name} DUPLICATED AS ${slug}`);
      load();
    } catch (e) { notify('Duplicate failed: ' + (e.message || 'unknown error').slice(0, 80)); }
  };

  const searchOrders = async () => {
    try {
      setOrders((await api.adminOrders(orderQuery, 30)).orders || []);
    } catch { notify('Order search failed'); }
  };

  const handleFormNameChange = (val) => {
    const autoSlug = val.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    setForm((f) => ({ ...f, name: val, id: f.id === '' || f.id === autoSlug.slice(0, -1) ? autoSlug : f.id }));
  };

  const add = async () => {
    if (!form.name.trim()) { notify('DISH NAME IS REQUIRED'); return; }
    if (!Number.isFinite(Number(form.price)) || Number(form.price) < 0) { notify('PRICE MUST BE ₹0 OR MORE'); return; }
    if (!Number.isInteger(Number(form.prep_time_minutes)) || Number(form.prep_time_minutes) < 2 || Number(form.prep_time_minutes) > 25) {
      notify('PREP TIME MUST BE 2–25 MIN');
      return;
    }
    const slug = form.id.trim() || form.name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    const dietaryTags = [form.dietary];
    if (form.dietary === 'vegan') dietaryTags.push('veg');

    try {
      await api.addItem({
        ...form,
        id: slug,
        price: Number(form.price) || 50,
        prep_time_minutes: Number(form.prep_time_minutes) || 10,
        calories: Number(form.calories) || 250,
        description: 'Freshly prepared at campus counter',
        ingredients: [],
        allergens: [],
        dietary_tags: dietaryTags,
        availability: true,
        available_until: null,
        taste_profile: ['savory', 'comforting'],
        mood_tags: ['comfort', 'study_fuel'],
        serving_times: ['all_day'],
        is_combo: false,
        combo_items: [],
      });
      notify(`${form.name} ADDED TO CANTEEN MENU`);
      setForm({
        id: '',
        name: '',
        price: 50,
        category: 'snack',
        cuisine: 'north_indian',
        prep_time_minutes: 10,
        calories: 250,
        portion_size: 'medium',
        spice_level: 1,
        popularity_score: 80,
        dietary: 'veg'
      });
      load();
    } catch (e) {
      notify('Failed to add dish: ' + (e.message || 'unknown error'));
    }
  };

  // Filtered dishes
  const liveCount = items.filter((i) => i.availability).length;
  const soldOutCount = items.length - liveCount;

  const filteredItems = useMemo(() => {
    return items.filter((it) => {
      if (filterCat === 'live' && !it.availability) return false;
      if (filterCat === 'sold_out' && it.availability) return false;
      if (filterCat === 'snack' && it.category !== 'snack') return false;
      if (filterCat === 'main_course' && it.category !== 'main_course') return false;
      if (filterCat === 'beverage' && it.category !== 'beverage') return false;

      if (search.trim()) {
        const q = search.toLowerCase();
        const matchName = it.name.toLowerCase().includes(q);
        const matchCat = (it.category || '').toLowerCase().includes(q);
        const matchCuisine = (it.cuisine || '').toLowerCase().includes(q);
        if (!matchName && !matchCat && !matchCuisine) return false;
      }
      return true;
    });
  }, [items, filterCat, search]);

  return (
    <div className="admin-container">
      {/* Header with Live Sync Status & Top Actions */}
      <div className="admin-header">
        <div>
          <div className="section-head" style={{ marginBottom: 4 }}>Canteen Operations & Live Controls</div>
          <div className="admin-subtitle">
            <span className="live-dot" />
            <span>Live Kitchen Controls · Real-time sync with biteMatch recommender</span>
          </div>
        </div>
        <div className="admin-header-actions">
          <button className="btn btn-secondary admin-btn" onClick={resetAllQueues} title="Reset all counter wait times to 0m">
            <RotateCcw size={14} /> Reset Queues
          </button>
          <button className="btn btn-secondary admin-btn" onClick={markAllLive} title="Set all menu dishes to available">
            <Check size={14} color="var(--green)" /> Mark All Live
          </button>
          <a className="btn btn-secondary admin-btn" href={api.exportUrl('menu')} download="menu.csv" title="Download menu CSV">Menu CSV</a>
          <a className="btn btn-secondary admin-btn" href={api.exportUrl('orders')} download="orders.csv" title="Download orders CSV">Orders CSV</a>
          <button className="btn btn-primary admin-btn" onClick={load} disabled={loading} title="Refresh all canteen stats">
            <RefreshCw size={14} className={loading ? 'spin' : ''} /> {loading ? 'Syncing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="admin-stats-grid">
        <div className="admin-stat-box">
          <div className="admin-stat-head">
            <span className="micro-label">KITCHEN STOCK</span>
            <Store size={18} color="var(--brand)" />
          </div>
          <div className="admin-stat-num">{liveCount} <span className="admin-stat-total">/ {items.length}</span></div>
          <div className="admin-progress-bar">
            <div
              className="admin-progress-fill"
              style={{ width: `${items.length ? (liveCount / items.length) * 100 : 0}%` }}
            />
          </div>
          <span className="admin-stat-foot">{items.length ? Math.round((liveCount / items.length) * 100) : 0}% of Menu Live in Kitchen</span>
        </div>

        <div className="admin-stat-box">
          <div className="admin-stat-head">
            <span className="micro-label">CAMPUS ORDERS</span>
            <ShoppingBag size={18} color="var(--green)" />
          </div>
          <div className="admin-stat-num" style={{ color: 'var(--green)' }}>{stats?.orders ?? '—'}</div>
          <span className="admin-stat-foot">Student Orders Processed</span>
        </div>

        <div className="admin-stat-box">
          <div className="admin-stat-head">
            <span className="micro-label">AVG STUDENT BUDGET</span>
            <TrendingUp size={18} color="var(--brand)" />
          </div>
          <div className="admin-stat-num">₹{stats?.avg_budget ? Number(stats.avg_budget).toFixed(0) : '—'}</div>
          <span className="admin-stat-foot">
            {stats?.min_budget && stats?.max_budget ? `Range ₹${stats.min_budget} - ₹${stats.max_budget}` : 'Per Student Order'}
          </span>
        </div>

        <div className="admin-stat-box">
          <div className="admin-stat-head">
            <span className="micro-label">CAMPUS BESTSELLER</span>
            <Sparkles size={18} color="#EAB308" />
          </div>
          <div className="admin-stat-num" style={{ fontSize: 18, color: 'var(--text-1)', lineHeight: 1.3 }}>
            {stats?.top_items?.[0]?.name || 'Samosa (2 pc)'}
          </div>
          <span className="admin-stat-foot">
            {stats?.top_items?.[0] ? `${stats.top_items[0].count} orders recorded` : 'Top student craving'}
          </span>
        </div>

        <div className="admin-stat-box">
          <div className="admin-stat-head">
            <span className="micro-label">TOTAL REVENUE</span>
            <TrendingUp size={18} color="#10B981" />
          </div>
          <div className="admin-stat-num" style={{ color: '#10B981' }}>₹{stats?.revenue != null ? Number(stats.revenue).toFixed(0) : '—'}</div>
          <span className="admin-stat-foot">
            {stats?.avg_order_value != null ? `Avg order ₹${Number(stats.avg_order_value).toFixed(0)}` : 'After coupons'}
          </span>
        </div>

        <div className="admin-stat-box">
          <div className="admin-stat-head">
            <span className="micro-label">NEEDS ATTENTION</span>
            <AlertCircle size={18} color="var(--brand)" />
          </div>
          <div className="admin-stat-num" style={{ fontSize: 18, color: 'var(--text-1)', lineHeight: 1.3 }}>
            {(alerts?.sold_out_count ?? soldOutCount)} sold out
          </div>
          <span className="admin-stat-foot">
            {alerts?.long_queues?.length ? `${alerts.long_queues.length} counter(s) over 8m wait` : 'Queues flowing'}
            {alerts?.disliked?.length ? ` · ${alerts.disliked.length} disliked dish(es)` : ''}
          </span>
        </div>
      </div>

      {alerts && (alerts.sold_out?.length > 0 || alerts.long_queues?.length > 0 || alerts.disliked?.length > 0) && (
        <div className="admin-inventory-card" style={{ borderColor: 'var(--brand-soft-border)', marginBottom: 4 }}>
          <div className="section-head" style={{ marginBottom: 8 }}>Kitchen Alerts — Act Now</div>
          {(alerts.sold_out || []).slice(0, 5).map((s) => (
            <div key={s.id} style={{ fontSize: 13, color: 'var(--text-2)', padding: '2px 0' }}>
              SOLD OUT: <strong>{s.name}</strong> (₹{s.price}) — toggle stock below to relist.
            </div>
          ))}
          {(alerts.long_queues || []).map((q) => (
            <div key={q.counter} style={{ fontSize: 13, color: 'var(--text-2)', padding: '2px 0' }}>
              LONG QUEUE: <strong>{q.label}</strong> at {q.wait_minutes}m — lower the slider above.
            </div>
          ))}
          {(alerts.disliked || []).slice(0, 3).map((d) => (
            <div key={d.id} style={{ fontSize: 13, color: 'var(--text-2)', padding: '2px 0' }}>
              NEGATIVE FEEDBACK: <strong>{d.name}</strong> ({d.dislikes} dislikes) — check the inbox below.
            </div>
          ))}
        </div>
      )}

      {/* Peak-hours chart from order timestamps */}
      {stats?.orders_by_hour && Object.keys(stats.orders_by_hour).length > 0 && (
        <>
          <div className="section-head" style={{ marginTop: 28 }}>Peak Order Hours (Today's Pattern)</div>
          <div className="admin-inventory-card">
            <div className="peak-chart" role="img" aria-label="Orders per hour bar chart">
              <div className="peak-chart-inner">
              {Array.from({ length: 24 }, (_, h) => {
                const v = stats.orders_by_hour[String(h)] || 0;
                const max = Math.max(1, ...Object.values(stats.orders_by_hour));
                return (
                  <div key={h} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }} title={`${h}:00 — ${v} orders`}>
                    <span className="mono" style={{ fontSize: 9, color: 'var(--text-2)' }}>{v || ''}</span>
                    <div style={{
                      width: '100%', borderRadius: '3px 3px 0 0',
                      height: `${Math.max(3, (v / max) * 78)}px`,
                      background: v === max && v > 0 ? 'var(--brand)' : 'var(--surface-2)',
                      border: '1px solid var(--hairline)', borderBottom: 'none',
                    }} />
                    <span className="mono" style={{ fontSize: 8, color: 'var(--text-3)' }}>{h}</span>
                  </div>
                );
              })}
              </div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '0 4px 4px' }}>
              Staff the highlighted peak hour first — queues + prep ETAs already follow live counters above.
            </div>
          </div>
        </>
      )}

      {/* Revenue per day, last 7 days */}
      {stats?.revenue_by_day && stats.revenue_by_day.length > 0 && (
        <>
          <div className="section-head" style={{ marginTop: 28 }}>Revenue by Day (Last 7 Days)</div>
          <div className="admin-inventory-card">
            <div className="peak-chart" role="img" aria-label="Revenue per day bar chart">
              <div className="peak-chart-inner" style={{ minWidth: 0 }}>
              {(() => {
                const max = Math.max(1, ...stats.revenue_by_day.map((d) => Number(d.total) || 0));
                return stats.revenue_by_day.map((d) => {
                  const v = Number(d.total) || 0;
                  const isToday = d.date === stats.revenue_by_day[stats.revenue_by_day.length - 1].date;
                  return (
                    <div key={d.date} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }} title={`${d.date} — Rs ${v.toFixed(0)} (${d.count} orders)`}>
                      <span className="mono" style={{ fontSize: 9, color: 'var(--text-2)' }}>{v > 0 ? `₹${v.toFixed(0)}` : ''}</span>
                      <div style={{
                        width: '100%', borderRadius: '3px 3px 0 0',
                        height: `${Math.max(3, (v / max) * 78)}px`,
                        background: isToday && v > 0 ? 'var(--brand)' : 'var(--surface-2)',
                        border: '1px solid var(--hairline)', borderBottom: 'none',
                      }} />
                      <span className="mono" style={{ fontSize: 8, color: 'var(--text-3)' }}>
                        {new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short' })}
                      </span>
                    </div>
                  );
                });
              })()}
              </div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '0 4px 4px' }}>
              Net of coupons. Today is highlighted — compare with the peak-hours pattern above to plan stock.
            </div>
          </div>
        </>
      )}

      {/* Counter Queues Management */}
      <div className="section-head">Live Counter Wait Times (Minutes)</div>      <div className="admin-queue-grid">
        {queues.map((q) => {
          const wait = q.wait_minutes || 0;
          const statusClass = wait > 15 ? 'busy' : wait > 5 ? 'moderate' : 'fast';
          const statusText = wait > 15 ? 'Peak Queue' : wait > 5 ? 'Moderate' : 'Smooth Flow';

          return (
            <div key={q.counter} className="admin-queue-card">
              <div className="admin-queue-head">
                <span className="admin-queue-name">{q.label}</span>
                <span className={`admin-queue-badge ${statusClass}`}>
                  <Clock size={12} /> {wait} min · {statusText}
                </span>
              </div>
              <div className="admin-queue-controls">
                <input
                  type="range" min="0" max="60" step="1"
                  value={wait}
                  aria-label={`${q.label} wait time`}
                  onChange={(e) => setQueueWait(q.counter, Number(e.target.value), { defer: true })}
                />
                <span className="admin-queue-val mono">{wait}m</span>
              </div>
              <div className="admin-queue-quick-steps">
                <button
                  type="button"
                  className="btn btn-secondary admin-step-btn"
                  onClick={() => setQueueWait(q.counter, wait - 5)}
                  disabled={wait <= 0}
                >
                  -5m
                </button>
                <button
                  type="button"
                  className="btn btn-secondary admin-step-btn"
                  onClick={() => setQueueWait(q.counter, 0)}
                  disabled={wait === 0}
                >
                  0m (Clear)
                </button>
                <button
                  type="button"
                  className="btn btn-secondary admin-step-btn"
                  onClick={() => setQueueWait(q.counter, wait + 5)}
                  disabled={wait >= 60}
                >
                  +5m
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Live Orders Management */}      <div className="section-head" style={{ marginTop: 28 }}>Live Student Orders (Latest {orders.length})</div>
      <div className="admin-inventory-card">
        <div className="admin-toolbar">
          <div className="admin-search-wrap">
            <Search size={16} className="admin-search-icon" />
            <input
              type="text" className="admin-search-input"
              placeholder="Search by token (CB-123) or session..."
              value={orderQuery}
              onChange={(e) => setOrderQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') searchOrders(); }}
            />
            {orderQuery && <button className="admin-search-clear" onClick={() => { setOrderQuery(''); api.adminOrders('', 30).then((r) => setOrders(r.orders || [])).catch(() => {}); }}>✕</button>}
          </div>
          <button className="btn btn-secondary admin-btn" onClick={searchOrders}>Search orders</button>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>TOKEN</th><th>ITEMS</th><th>TOTAL</th><th>STATE</th><th>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.token}>
                  <td className="mono">{o.token}</td>
                  <td style={{ fontSize: 12.5 }}>{(o.items || []).join(', ')}</td>
                  <td className="mono">₹{Number(o.payable ?? o.total ?? 0).toFixed(0)}{o.coupon ? ` (${o.coupon})` : ''}</td>
                  <td><span className={`status ${o.state === 'READY' || o.state === 'COMPLETED' ? 'live' : o.state === 'CANCELLED' ? 'off' : ''}`}>{o.state}</span></td>
                  <td>
                    <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      <button className="btn btn-secondary admin-step-btn" onClick={() => setOrderState(o.token, 'READY')}>Ready</button>
                      <button className="btn btn-secondary admin-step-btn" onClick={() => setOrderState(o.token, 'COMPLETED')}>Done</button>
                      <button className="btn btn-secondary admin-step-btn" onClick={() => setOrderState(o.token, 'CANCELLED')}>Cancel</button>
                    </span>
                  </td>
                </tr>
              ))}
              {orders.length === 0 && (
                <tr><td colSpan="5" style={{ textAlign: 'center', padding: 24, color: 'var(--text-2)' }}>No orders yet — student orders appear here live.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Menu Inventory Management */}
      <div className="section-head" style={{ marginTop: 28 }}>Live Dishes & Stock Availability</div>
      <div className="admin-inventory-card">
        {/* Toolbar: Search + Category Pills */}
        <div className="admin-toolbar">
          <div className="admin-search-wrap">
            <Search size={16} className="admin-search-icon" />
            <input
              type="text"
              className="admin-search-input"
              placeholder="Search dishes by name, category, or cuisine..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button className="admin-search-clear" onClick={() => setSearch('')}>✕</button>
            )}
          </div>

          <div className="admin-filter-pills">
            <button
              className={`cat-pill ${filterCat === 'all' ? 'active' : ''}`}
              onClick={() => setFilterCat('all')}
            >
              All ({items.length})
            </button>
            <button
              className={`cat-pill ${filterCat === 'live' ? 'active' : ''}`}
              onClick={() => setFilterCat('live')}
            >
              🟢 Live ({liveCount})
            </button>
            <button
              className={`cat-pill ${filterCat === 'sold_out' ? 'active' : ''}`}
              onClick={() => setFilterCat('sold_out')}
            >
              🔴 Sold Out ({soldOutCount})
            </button>
            <button
              className={`cat-pill ${filterCat === 'snack' ? 'active' : ''}`}
              onClick={() => setFilterCat('snack')}
            >
              Snacks
            </button>
            <button
              className={`cat-pill ${filterCat === 'main_course' ? 'active' : ''}`}
              onClick={() => setFilterCat('main_course')}
            >
              Mains
            </button>
            <button
              className={`cat-pill ${filterCat === 'beverage' ? 'active' : ''}`}
              onClick={() => setFilterCat('beverage')}
            >
              Beverages
            </button>
          </div>
        </div>

        {/* Dish Count Summary */}
        <div className="admin-count-bar">
          <span>Showing <strong>{filteredItems.length}</strong> of {items.length} dishes</span>
          <span style={{ display: 'flex', gap: 8 }}>
            {filteredItems.some((i) => !i.availability) && (
              <button className="admin-reset-filter" onClick={markFilteredLive}>Mark filtered live</button>
            )}
            {filterCat !== 'all' && (
              <button className="admin-reset-filter" onClick={() => setFilterCat('all')}>Reset Filter</button>
            )}
          </span>
        </div>

        {/* Desktop Table View (>= 768px) */}
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: '40%' }}>DISH & DETAILS</th>
                <th style={{ width: '18%' }}>PRICE (₹)</th>
                <th style={{ width: '14%' }}>PREP TIME</th>
                <th style={{ width: '16%' }}>LIVE STATUS</th>
                <th style={{ width: '12%', textAlign: 'center' }}>STOCK</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((it) => {
                const currentPriceVal = editingPrices[it.id] !== undefined ? editingPrices[it.id] : it.price;
                return (
                  <tr key={it.id} className={!it.availability ? 'row-sold-out' : ''}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <DietMarker tags={it.dietary_tags} />
                        <div>
                          <div className="admin-dish-name">{it.name}</div>
                          <div className="admin-dish-sub">
                            {(it.category || '').toUpperCase()} · {(it.cuisine || '').replace('_', ' ').toUpperCase()} · {it.calories} KCAL · {it.protein_g ?? 0}G PROTEIN · {it.sugar_g ?? 0}G SUGAR
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="admin-price-input-wrap">
                        <span className="admin-price-currency">₹</span>
                        <input
                          className="admin-price-input mono"
                          aria-label={`Price for ${it.name}`}
                          type="number"
                          value={currentPriceVal}
                          min="0"
                          onChange={(e) => handlePriceChange(it.id, e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') savePrice(it, e.target.value);
                          }}
                          onBlur={(e) => savePrice(it, e.target.value)}
                        />
                      </div>
                    </td>
                    <td>
                      <span className="admin-price-input-wrap" title="Prep time in minutes (1-60)">
                        <input
                          className="admin-price-input mono" aria-label={`Prep time for ${it.name}`}
                          type="number" min="2" max="25"
                          value={editingPrep[it.id] !== undefined ? editingPrep[it.id] : it.prep_time_minutes}
                          onChange={(e) => setEditingPrep((prev) => ({ ...prev, [it.id]: e.target.value }))}
                          onKeyDown={(e) => { if (e.key === 'Enter') { savePrep(it, e.target.value); } }}
                          onBlur={(e) => { savePrep(it, e.target.value); setEditingPrep((prev) => { const n = { ...prev }; delete n[it.id]; return n; }); }}
                          style={{ width: 56 }}
                        />
                        <span className="micro-label">MIN</span>
                      </span>
                    </td>
                    <td>
                      <span className={`status ${it.availability ? 'live' : 'off'}`}>
                        {it.availability ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                        {it.availability ? 'LIVE' : 'SOLD OUT'}
                      </span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                        <Toggle checked={it.availability} onChange={() => toggle(it)} label={`Stock toggle for ${it.name}`} />
                        <button
                          type="button" className="icon-btn" aria-label={`Duplicate ${it.name}`} title={`Duplicate ${it.name}`}
                          style={{ width: 28, height: 28, minHeight: 28 }} onClick={() => duplicateDish(it)}
                        >
                          <Copy size={14} />
                        </button>
                      </span>
                    </td>
                  </tr>
                );
              })}
              {filteredItems.length === 0 && (
                <tr>
                  <td colSpan="5" style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
                    No dishes matched your search or filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Cards View (< 768px) */}
        <div className="admin-cards-wrap">
          {filteredItems.map((it) => {
            const currentPriceVal = editingPrices[it.id] !== undefined ? editingPrices[it.id] : it.price;
            return (
              <div key={it.id} className={`admin-mobile-card ${!it.availability ? 'sold-out' : ''}`}>
                <div className="admin-mobile-card-top">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                    <DietMarker tags={it.dietary_tags} />
                    <div style={{ minWidth: 0 }}>
                      <div className="admin-dish-name" style={{ fontSize: 15 }}>{it.name}</div>
                      <div className="admin-dish-sub">
                        {(it.category || '').toUpperCase()} · {it.prep_time_minutes} MIN PREP
                      </div>
                    </div>
                  </div>
                  <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <Toggle checked={it.availability} onChange={() => toggle(it)} label={`Stock toggle for ${it.name}`} />
                    <button
                      type="button" className="icon-btn" aria-label={`Duplicate ${it.name}`} title={`Duplicate ${it.name}`}
                      style={{ width: 28, height: 28, minHeight: 28 }} onClick={() => duplicateDish(it)}
                    >
                      <Copy size={14} />
                    </button>
                  </span>
                </div>

                <div className="admin-mobile-card-bottom">
                  <div className="admin-price-input-wrap">
                    <span className="admin-price-currency">₹</span>
                    <input
                      className="admin-price-input mono"
                      aria-label={`Price for ${it.name}`}
                      type="number"
                      value={currentPriceVal}
                      min="0"
                      onChange={(e) => handlePriceChange(it.id, e.target.value)}
                      onBlur={(e) => savePrice(it, e.target.value)}
                    />
                  </div>
                  <span className={`status ${it.availability ? 'live' : 'off'}`}>
                    {it.availability ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                    {it.availability ? 'LIVE IN KITCHEN' : 'SOLD OUT'}
                  </span>
                </div>
              </div>
            );
          })}
          {filteredItems.length === 0 && (
            <div style={{ textAlign: 'center', padding: '30px 10px', color: 'var(--text-2)' }}>
              No dishes matched your search or filter.
            </div>
          )}
        </div>
      </div>

      {/* Student Feedback Inbox */}
      <div className="section-head" style={{ marginTop: 32 }}>Student Feedback Inbox (Latest {inbox.length})</div>
      <div className="admin-inventory-card">
        {inbox.length === 0 && (
          <div style={{ padding: 16, color: 'var(--text-2)', fontSize: 13 }}>No feedback yet — thumbs on any card appear here with comments.</div>
        )}
        {inbox.slice(0, 12).map((f, i) => (
          <div key={`${f.item_id || 'item'}-${f.at || i}-${i}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '8px 4px', borderBottom: '1px solid var(--hairline)', fontSize: 13 }}>
            <span>
              <strong>{f.item_name || f.item_id}</strong>{' '}
              <span style={{ color: f.rating > 0 ? '#10B981' : 'var(--brand)' }}>{f.rating > 0 ? 'LIKED' : 'DISLIKED'}</span>
              {f.comment ? <span style={{ color: 'var(--text-2)' }}> — “{f.comment}”</span> : null}
            </span>
            <span className="micro-label mono">{(f.at || '').slice(0, 16).replace('T', ' ')}</span>
          </div>
        ))}
      </div>

      {/* Add New Dish Form */}
      <div className="section-head" style={{ marginTop: 32 }}>Add New Dish to Canteen Menu</div>
      <div className="admin-add-card">
        <div className="admin-form-grid">
          <div className="admin-field">
            <label className="admin-label">DISH NAME *</label>
            <input
              className="admin-input"
              placeholder="e.g. Paneer Kathi Roll"
              value={form.name}
              onChange={(e) => handleFormNameChange(e.target.value)}
            />
          </div>

          <div className="admin-field">
            <label className="admin-label">SLUG ID (UNIQUE) *</label>
            <input
              className="admin-input mono"
              placeholder="e.g. paneer_kathi_roll"
              value={form.id}
              onChange={(e) => setForm({ ...form, id: e.target.value })}
            />
          </div>

          <div className="admin-field">
            <label className="admin-label">PRICE (₹) *</label>
            <input
              className="admin-input mono"
              type="number"
              placeholder="50"
              min="0"
              value={form.price}
              onChange={(e) => setForm({ ...form, price: Number(e.target.value) })}
            />
          </div>

          <div className="admin-field">
            <label className="admin-label">CATEGORY</label>
            <select
              className="admin-select"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              <option value="snack">Snack</option>
              <option value="main_course">Main Course</option>
              <option value="beverage">Beverage</option>
              <option value="dessert">Dessert</option>
            </select>
          </div>

          <div className="admin-field">
            <label className="admin-label">DIET</label>
            <select
              className="admin-select"
              value={form.dietary}
              onChange={(e) => setForm({ ...form, dietary: e.target.value })}
            >
              <option value="veg">Vegetarian</option>
              <option value="non_veg">Non-Vegetarian</option>
              <option value="vegan">Vegan</option>
              <option value="jain">Jain</option>
            </select>
          </div>

          <div className="admin-field">
            <label className="admin-label">PREP TIME (MINUTES)</label>
            <input
              className="admin-input mono"
              type="number"
              placeholder="10"
              min="2"
              max="25"
              value={form.prep_time_minutes}
              onChange={(e) => setForm({ ...form, prep_time_minutes: Number(e.target.value) })}
            />
          </div>
        </div>

        <div className="admin-form-actions">
          <button className="btn btn-primary" onClick={add} style={{ minWidth: 160 }}>
            <Plus size={16} /> Add Dish to Kitchen
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
            Dish immediately becomes searchable and live for student recommendations.
          </span>
        </div>
      </div>
    </div>
  );
}
