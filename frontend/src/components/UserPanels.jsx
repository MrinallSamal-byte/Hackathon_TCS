import React, { useEffect, useRef, useState } from 'react';
import { Receipt, User, TrendingUp, RefreshCw, BellRing, Leaf } from 'lucide-react';
import { api } from '../api.js';

export const ALLERGENS = ['peanuts', 'tree_nuts', 'dairy', 'gluten', 'soy', 'egg', 'seafood', 'sesame'];

export function VegToggle({ vegOnly, onToggle }) {
  return (
    <button
      type="button" aria-pressed={!!vegOnly} title="Veg-only mode: hides all non-veg across chat and menu"
      onClick={() => onToggle(!vegOnly)}
      className={`cat-pill${vegOnly ? ' active' : ''}`}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
    >
      <Leaf size={13} /> {vegOnly ? 'VEG-ONLY ON' : 'VEG-ONLY'}
    </button>
  );
}

export function OrderTracker({ sessionId, notify }) {
  const [token, setToken] = useState('');
  const [status, setStatus] = useState(null);
  const [input, setInput] = useState('');
  const announced = useRef('');
  const poll = useRef(null);

  const fetchStatus = async (tok, silent) => {
    if (!tok) return;
    try {
      const st = await api.orderStatus(tok);
      setStatus(st);
      if (st.state === 'READY' && announced.current !== tok) {
        announced.current = tok;
        notify(`ORDER ${tok} IS READY FOR PICKUP`);
      }
    } catch { if (!silent) notify('ORDER NOT FOUND'); }
  };

  // Auto-attach the session's latest order on mount.
  useEffect(() => {
    let live = true;
    if (!sessionId) return;
    api.orders(sessionId, 1).then((r) => {
      if (live && r.orders && r.orders[0]) {
        setToken(r.orders[0].token);
        fetchStatus(r.orders[0].token, true);
      }
    }).catch(() => {});
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Poll while preparing (20s); stop on READY/COMPLETED/CANCELLED.
  useEffect(() => {
    clearInterval(poll.current);
    if (token && (!status || status.state === 'PREPARING')) {
      poll.current = setInterval(() => fetchStatus(token, true), 20000);
    }
    return () => clearInterval(poll.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, status && status.state]);

  if (!token && !status) return null;
  return (
    <div className="drawer" aria-label="Live order tracking" style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 14 }}>
        <BellRing size={15} color="var(--brand)" /> LIVE TRACKING
      </div>
      <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
        <input
          aria-label="Order token to track" placeholder="CB-123" value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          onKeyDown={(e) => { if (e.key === 'Enter' && input.trim()) { setToken(input.trim()); fetchStatus(input.trim()); } }}
          style={{ flex: 1, background: 'var(--surface-2)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '8px 10px', color: 'var(--text-1)', fontSize: 12.5, fontFamily: 'var(--font-data)' }}
        />
        <button className="btn btn-secondary" style={{ padding: '8px 12px', fontSize: 12 }} onClick={() => { if (input.trim()) { setToken(input.trim()); fetchStatus(input.trim()); } }}>Track</button>
      </div>
      {status && (
        <div style={{ marginTop: 8, background: 'var(--surface-2)', border: '1px solid var(--hairline)', borderRadius: 12, padding: '8px 10px', fontSize: 12.5 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <strong className="mono">{status.token}</strong>
            <span className="mono" style={{ color: status.state === 'READY' ? '#10B981' : 'var(--text-2)' }}>{status.state}</span>
          </div>
          <div style={{ color: 'var(--text-2)', marginTop: 2 }}>{(status.items || []).join(', ')}</div>
          <div className="mono" style={{ marginTop: 2 }}>{status.detail}</div>
        </div>
      )}
    </div>
  );
}

export function SpendingBadge({ sessionId }) {
  const [sp, setSp] = useState(null);
  useEffect(() => {
    let live = true;
    if (!sessionId) return;
    api.spending(sessionId).then((r) => { if (live) setSp(r); }).catch(() => {});
    return () => { live = false; };
  }, [sessionId]);
  if (!sp || (!sp.today_total && !sp.order_count)) return null;
  return (
    <div className="micro-label mono" style={{ color: 'var(--text-2)' }}>
      TODAY ₹{Number(sp.today_total).toFixed(0)} · {sp.today_count} ORDERS · 7-DAY ₹{Number(sp.week_total).toFixed(0)}
    </div>
  );
}

export function TrendingStrip({ onAdd, notify }) {
  const [items, setItems] = useState([]);
  useEffect(() => {
    let live = true;
    api.trending(5).then((r) => { if (live) setItems(r.items || []); }).catch(() => {});
    return () => { live = false; };
  }, []);
  if (!items.length) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      <div className="micro-label" style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
        <TrendingUp size={13} color="var(--brand)" /> TRENDING ON CAMPUS
      </div>
      <div className="chip-row" role="group" aria-label="Trending dishes">
        {items.map((it) => (
          <button key={it.id} className="chip" title={`${it.name} — Rs ${it.price}`} onClick={() => onAdd && onAdd(it)}>
            {it.name} · ₹{Number(it.price).toFixed(0)}
          </button>
        ))}
      </div>
    </div>
  );
}

export function OrdersPanel({ sessionId, onReorder, notify }) {
  const [orders, setOrders] = useState([]);
  const [open, setOpen] = useState(false);
  const load = async () => {
    try {
      const r = await api.orders(sessionId, 8);
      setOrders(r.orders || []);
    } catch { notify && notify('ORDERS LOAD FAILED'); }
  };
  useEffect(() => { if (open && sessionId) load(); }, [open]); // eslint-disable-line
  const cancel = async (token) => {
    try {
      await api.cancelOrder(token);
      notify(`ORDER ${token} CANCELLED`);
      load();
    } catch (e) { notify('CANCEL FAILED — ALREADY READY?'); }
  };
  return (
    <div className="drawer" aria-label="My orders" style={{ marginBottom: 12 }}>
      <button
        type="button" aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', background: 'none', border: 'none', padding: 0, color: 'inherit', cursor: 'pointer' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 14 }}>
          <Receipt size={15} color="var(--brand)" /> MY ORDERS {orders.length ? `(${orders.length})` : ''}
        </div>
        <span className="micro-label">{open ? 'HIDE' : 'VIEW'}</span>
      </button>
      {open && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button className="btn btn-secondary" style={{ padding: '6px 10px', fontSize: 12 }} onClick={load}>
            <RefreshCw size={12} /> Refresh status
          </button>
          {orders.length === 0 && <div style={{ fontSize: 12.5, color: 'var(--text-3)' }}>No orders yet on this device.</div>}
          {orders.map((o) => (
            <div key={o.token} style={{ background: 'var(--surface-2)', border: '1px solid var(--hairline)', borderRadius: 12, padding: '8px 10px', fontSize: 12.5 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <strong className="mono">{o.token}</strong>
                <span className="mono" style={{ color: o.state === 'READY' ? '#10B981' : 'var(--text-2)' }}>{o.state}</span>
              </div>
              <div style={{ color: 'var(--text-2)', marginTop: 2 }}>{(o.items || []).join(', ')}</div>
              <div className="mono" style={{ marginTop: 2 }}>₹{Number(o.payable ?? o.total).toFixed(0)}{o.counter_label ? ` · ${o.counter_label}` : ''}</div>
              <span style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                {onReorder && <button className="btn btn-secondary" style={{ flex: 1, padding: '6px 8px', fontSize: 12 }} onClick={() => onReorder(o)}>Reorder</button>}
                {o.state === 'PREPARING' && <button className="btn btn-secondary" style={{ flex: 1, padding: '6px 8px', fontSize: 12 }} onClick={() => cancel(o.token)}>Cancel</button>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const DIETS = ['', 'veg', 'vegan', 'jain', 'gluten_free', 'halal'];
const GOALS = ['', 'high_protein', 'low_calorie', 'diabetic'];

export function ProfilePanel({ sessionId, notify, onSaved }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ dietary_restrictions: [], goal: '', budget: '', weekly_budget: '', health_conditions: [], no_onion_garlic: false });
  const [weekSpent, setWeekSpent] = useState(null);
  useEffect(() => {
    if (!open || !sessionId) return;
    api.getProfile(sessionId).then((r) => {
      const p = r.profile || {};
      setForm({
        dietary_restrictions: p.dietary_restrictions || [],
        goal: p.goal || '', budget: p.budget ?? '', weekly_budget: p.weekly_budget ?? '',
        health_conditions: p.health_conditions || [],
        no_onion_garlic: !!p.no_onion_garlic,
      });
    }).catch(() => {});
    api.spending(sessionId).then((s) => setWeekSpent(s)).catch(() => {});
  }, [open, sessionId]);
  const toggleDiet = (d) => {
    setForm((f) => {
      const cur = f.dietary_restrictions || [];
      return { ...f, dietary_restrictions: cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d] };
    });
  };
  const save = async () => {
    try {
      const payload = {
        session_id: sessionId,
        dietary_restrictions: form.dietary_restrictions,
        goal: form.goal || null,
        budget: form.budget === '' ? null : Number(form.budget),
        weekly_budget: form.weekly_budget === '' ? null : Math.max(0, Number(form.weekly_budget) || 0),
        health_conditions: form.health_conditions,
        no_onion_garlic: !!form.no_onion_garlic,
      };
      const r = await api.saveProfile(payload);
      notify('DIETARY PROFILE SAVED');
      onSaved && onSaved(r.profile);
    } catch { notify('PROFILE SAVE FAILED'); }
  };
  return (
    <div className="drawer" aria-label="Dietary profile" style={{ marginBottom: 12 }}>
      <button
        type="button" aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', background: 'none', border: 'none', padding: 0, color: 'inherit', cursor: 'pointer' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 14 }}>
          <User size={15} color="var(--brand)" /> MY DIET PROFILE
        </div>
        <span className="micro-label">{open ? 'HIDE' : 'SET DEFAULTS'}</span>
      </button>
      {open && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="micro-label">DEFAULT DIET (AUTO-APPLIED)</div>
          <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {DIETS.filter(Boolean).map((d) => (
              <button key={d} type="button" aria-pressed={form.dietary_restrictions.includes(d)} className={`cat-pill${form.dietary_restrictions.includes(d) ? ' active' : ''}`} onClick={() => toggleDiet(d)}>
                {d.replace('_', ' ').toUpperCase()}
              </button>
            ))}
          </span>
          <label className="micro-label" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            FITNESS GOAL
            <select value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })}
              style={{ background: 'var(--surface)', color: 'var(--text-1)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '8px 10px', fontSize: 12.5 }}>
              {GOALS.map((g) => <option key={g} value={g}>{g === '' ? 'NO GOAL' : g.replace('_', ' ').toUpperCase()}</option>)}
            </select>
          </label>
          <label className="micro-label" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            USUAL BUDGET (RS)
            <input type="number" min="0" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })}
              style={{ background: 'var(--surface)', color: 'var(--text-1)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '8px 10px', fontSize: 12.5 }} />
          </label>
          <label className="micro-label" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            WEEKLY SPEND LIMIT (RS)
            <input type="number" min="0" value={form.weekly_budget} onChange={(e) => setForm({ ...form, weekly_budget: e.target.value })}
              style={{ background: 'var(--surface)', color: 'var(--text-1)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '8px 10px', fontSize: 12.5 }} />
          </label>
          {form.weekly_budget !== '' && weekSpent && (
            <div>
              <div className="micro-label mono" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>THIS WEEK ₹{Number(weekSpent.week_total).toFixed(0)} / ₹{Number(form.weekly_budget).toFixed(0)}</span>
                <span style={{ color: weekSpent.week_total > Number(form.weekly_budget) ? 'var(--red-text)' : '#10B981', fontWeight: 800 }}>
                  {weekSpent.week_total > Number(form.weekly_budget) ? 'OVER LIMIT' : `₹${(Number(form.weekly_budget) - weekSpent.week_total).toFixed(0)} LEFT`}
                </span>
              </div>
          {(form.health_conditions || []).length > 0 && (
            <div>
              <div className="micro-label">SAVED HEALTH NOTES (AUTO-REMEMBERED FROM CHAT)</div>
              <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                {form.health_conditions.map((c) => (
                  <span key={c} className="cat-pill active" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    {String(c).toUpperCase()}
                    <button
                      type="button" aria-label={`Remove ${c} health note`}
                      onClick={() => setForm((f) => ({ ...f, health_conditions: (f.health_conditions || []).filter((x) => x !== c) }))}
                      style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0, fontSize: 13, lineHeight: 1 }}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </span>
              <div style={{ fontSize: 11.5, color: 'var(--text-3)', marginTop: 4 }}>
                Recommendations automatically respect these. Remove + Save if outdated.
              </div>
            </div>
          )}
              <div className="budget-track">
                <div className="budget-fill" style={{ width: `${Number(form.weekly_budget) > 0 ? Math.min(100, (weekSpent.week_total / Number(form.weekly_budget)) * 100) : 0}%` }} />
              </div>
              {Array.isArray(weekSpent.by_day) && weekSpent.by_day.length === 7 && (
                <div style={{ marginTop: 8 }}>
                  <div className="micro-label">SPEND EACH DAY (RS)</div>
                  <div className="daybars" role="img" aria-label="Daily spend bar chart, last 7 days">
                    {(() => {
                      const max = Math.max(1, ...weekSpent.by_day.map((d) => Number(d.total) || 0));
                      return weekSpent.by_day.map((d) => {
                        const v = Number(d.total) || 0;
                        const isToday = d.date === weekSpent.by_day[6].date;
                        return (
                          <div key={d.date} className="daybar-col" title={`${d.date}: Rs ${v.toFixed(0)} (${d.count} orders)`}>
                            <span className="mono">{v > 0 ? v.toFixed(0) : ''}</span>
                            <div className={`daybar${isToday ? ' today' : ''}`} style={{ height: `${Math.max(3, (v / max) * 44)}px` }} />
                            <span className="mono">{new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'narrow' })}</span>
                          </div>
                        );
                      });
                    })()}
                  </div>
                </div>
              )}
            </div>
          )}
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12.5, color: 'var(--text-2)' }}>
            <input type="checkbox" checked={form.no_onion_garlic} onChange={(e) => setForm({ ...form, no_onion_garlic: e.target.checked })} />
            Always exclude onion / garlic
          </label>
          <button className="btn btn-primary" style={{ padding: '8px 12px', fontSize: 13 }} onClick={save}>Save defaults</button>
          <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>Defaults fill in only what you don't restate — hard dietary filters are never relaxed.</span>
        </div>
      )}
    </div>
  );
}

export function OrderReceipt({ order, onClose }) {
  if (!order) return null;
  const lines = [
    `biteMatch — Order Receipt`,
    `Token: ${order.token}`,
    `Total: Rs ${Number(order.total).toFixed(2)}`,
    order.discount ? `Coupon ${order.coupon}: -Rs ${Number(order.discount).toFixed(2)} (Pay Rs ${Number(order.payable).toFixed(2)})` : null,
    order.counter_label ? `Pickup: ${order.counter_label}` : null,
    `ETA: ~${order.eta_minutes} min`,
  ].filter(Boolean).join('\n');
  return (
    <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
      <button
        className="btn btn-secondary" style={{ flex: 1, fontSize: 12.5 }}
        onClick={() => {
          const blob = new Blob([lines], { type: 'text/plain' });
          const url = URL.createObjectURL(blob);
          try {
            const a = document.createElement('a');
            a.href = url;
            a.download = `${order.token}-receipt.txt`;
            document.body.appendChild(a);
            a.click();
            a.remove();
          } finally {
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }
        }}
      >
        Download receipt
      </button>
      {onClose && <button className="btn btn-secondary" style={{ flex: 1, fontSize: 12.5 }} onClick={onClose}>Back to food</button>}
    </div>
  );
}
