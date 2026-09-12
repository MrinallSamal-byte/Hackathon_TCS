const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function req(path, opts = {}) {
  const r = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `Request failed: ${r.status}`);
  }
  return r.json();
}

export const api = {
  health: () => req('/health'),
  menu: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') q.set(k, v); });
    return req(`/menu?${q.toString()}`);
  },
  chat: (message, prefs, meal_override, session_id) => req('/chat', {
    method: 'POST', body: JSON.stringify({ message, prefs: prefs || {}, meal_override, session_id }),
  }),
  recommend: (preferences, meal) => req('/recommend', {
    method: 'POST', body: JSON.stringify({ preferences: preferences || {}, meal }),
  }),
  validateTray: (tray_ids, budget) => req('/tray/validate', {
    method: 'POST', body: JSON.stringify({ tray_ids, budget }),
  }),
  suggestFill: (tray_ids, budget, prefs) => req('/tray/suggest', {
    method: 'POST', body: JSON.stringify({ tray_ids, budget, prefs: prefs || {} }),
  }),
  queues: () => req('/queue'),
  orderStatus: (token) => req(`/order/${encodeURIComponent(token)}`),
  order: (tray_ids, budget, session_id) => req('/order', {
    method: 'POST', body: JSON.stringify({ tray_ids, budget, session_id }),
  }),
  feedback: (item_id, rating, extra = {}) => req('/feedback', {
    method: 'POST', body: JSON.stringify({ item_id, rating, ...extra }),
  }),
  setAvailability: (id, available) => req(`/admin/items/${id}/availability`, {
    method: 'PATCH', body: JSON.stringify({ available }),
  }),
  setPrice: (id, price) => req(`/admin/items/${id}/price`, {
    method: 'PATCH', body: JSON.stringify({ price }),
  }),
  addItem: (data) => req('/admin/items', { method: 'POST', body: JSON.stringify(data) }),
  setQueue: (counter, minutes) => req('/admin/queue', {
    method: 'PATCH', body: JSON.stringify({ counter, minutes }),
  }),
  analytics: () => req('/admin/analytics'),
};
