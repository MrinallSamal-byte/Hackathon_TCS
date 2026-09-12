import React, { useEffect, useState } from 'react';
import { RefreshCw, Plus } from 'lucide-react';
import { api } from '../api.js';
import { Toggle } from './bits.jsx';

export function AdminPanel({ notify }) {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [queues, setQueues] = useState([]);
  const [form, setForm] = useState({ id: '', name: '', price: 50, category: 'snack', cuisine: 'north_indian', prep_time_minutes: 10, calories: 200, portion_size: 'medium', spice_level: 1, popularity_score: 50 });

  const load = async () => {
    const m = await api.menu({ available_only: false });
    setItems(m.items || []);
    try { setStats(await api.analytics()); } catch { setStats(null); }
    try { setQueues((await api.queues()).queues || []); } catch { /* ignore */ }
  };
  useEffect(() => { load(); }, []);

  const toggle = async (it) => {
    await api.setAvailability(it.id, !it.availability);
    notify(`${it.name} → ${!it.availability ? 'LIVE' : 'OFF'}`);
    load();
  };
  const savePrice = async (it, price) => {
    await api.setPrice(it.id, Number(price));
    notify(`${it.name} price → ₹${price}`);
    load();
  };
  const add = async () => {
    if (!form.id || !form.name) { notify('ID + NAME REQUIRED'); return; }
    await api.addItem({
      ...form, description: 'Admin-added item', ingredients: [], allergens: [],
      dietary_tags: ['veg'], availability: true, available_until: null,
      taste_profile: ['savory'], mood_tags: ['comfort'], serving_times: ['all_day'],
      is_combo: false, combo_items: [],
    });
    notify(`${form.name} ADDED`);
    load();
  };

  return (
    <div>
      <div className="section-head">// ADMIN — MENU + ANALYTICS</div>
      {stats && (
        <p className="micro-label">
          {stats.total_items} ITEMS · {stats.live_items} LIVE · {stats.orders} ORDERS · AVG BUDGET ₹{stats.avg_budget ?? '—'}
        </p>
      )}
      {stats && stats.top_items && stats.top_items.length > 0 && (
        <p className="mono" style={{ fontSize: 12 }}>TOP: {stats.top_items.slice(0, 5).map((t) => `${t.name} (${t.count})`).join(' · ')}</p>
      )}
      <div className="section-head">// LIVE QUEUES (MIN)</div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
        {queues.map((q) => (
          <label key={q.counter} className="micro-label" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {q.label.toUpperCase()}
            <input
              className="mono" aria-label={`Queue minutes for ${q.label}`}
              type="number" min="0" max="120" defaultValue={q.wait_minutes} style={{ width: 64, background: 'var(--surface-2)', color: 'var(--text-1)', border: '1px solid var(--hairline)', borderRadius: 6, padding: 6 }}
              onBlur={async (e) => {
                await api.setQueue(q.counter, Number(e.target.value));
                notify(`${q.label.toUpperCase()} QUEUE → ${e.target.value}M`);
                load();
              }}
            />
          </label>
        ))}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="admin-table">
          <thead><tr><th>ITEM</th><th>PRICE</th><th>STATUS</th><th>STOCK</th></tr></thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id}>
                <td>{it.name}</td>
                <td className="num">
                  <input
                    className="mono" aria-label={`Price for ${it.name}`}
                    type="number" defaultValue={it.price} min="0" style={{ width: 72, background: 'var(--surface-2)', color: 'var(--text-1)', border: '1px solid var(--hairline)', borderRadius: 6, padding: 6 }}
                    onBlur={(e) => { if (Number(e.target.value) !== it.price) savePrice(it, e.target.value); }}
                  />
                </td>
                <td>
                  <span className={`status${it.availability ? ' live' : ''}`}>
                    <span className="sq" />{it.availability ? 'LIVE' : 'OFF'}
                  </span>
                </td>
                <td><Toggle checked={it.availability} onChange={() => toggle(it)} label={`Stock toggle for ${it.name}`} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="section-head">// ADD ITEM</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input aria-label="New item id" placeholder="id" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} style={{ background: 'var(--surface)', color: 'var(--text-1)', border: '1px solid var(--hairline)', borderRadius: 8, padding: 10 }} />
        <input aria-label="New item name" placeholder="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={{ background: 'var(--surface)', color: 'var(--text-1)', border: '1px solid var(--hairline)', borderRadius: 8, padding: 10 }} />
        <button className="btn btn-secondary" onClick={add}><Plus size={16} strokeWidth={1.5} /> ADD</button>
        <button className="btn btn-secondary" onClick={load}><RefreshCw size={16} strokeWidth={1.5} /> RELOAD</button>
      </div>
    </div>
  );
}
