const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function adminHeaders() {
  try {
    const t = localStorage.getItem('cb_admin_token');
    return t ? { 'X-Admin-Token': t } : {};
  } catch { return {}; }
}

async function req(path, opts = {}) {
  const { headers: optHeaders, ...rest } = opts || {};
  const r = await fetch(`${BASE}${path}`, {
    ...rest,
    headers: { 'Content-Type': 'application/json', ...adminHeaders(), ...(optHeaders || {}) },
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || `Request failed: ${r.status}`);
  }
  const text = await r.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Invalid JSON response: ${r.status}`);
  }
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
  validateTray: (tray_ids, budget, coupon_code) => req('/tray/validate', {
    method: 'POST', body: JSON.stringify({ tray_ids, budget, coupon_code }),
  }),
  suggestFill: (tray_ids, budget, prefs) => req('/tray/suggest', {
    method: 'POST', body: JSON.stringify({ tray_ids, budget, prefs: prefs || {} }),
  }),
  queues: () => req('/queue'),
  orderStatus: (token) => req(`/order/${encodeURIComponent(token)}`),
  order: (tray_ids, budget, session_id, coupon_code) => req('/order', {
    method: 'POST', body: JSON.stringify({ tray_ids, budget, session_id, coupon_code }),
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
  clearQueue: () => req('/admin/queue', { method: 'DELETE' }),
  analytics: () => req('/admin/analytics'),
  // Real-world additions (all additive)
  orders: (session_id, limit) => req(`/orders?session_id=${encodeURIComponent(session_id || '')}&limit=${limit || 10}`),
  cancelOrder: (token) => req(`/order/${encodeURIComponent(token)}`, { method: 'DELETE' }),
  favorites: (session_id) => req(`/favorites?session_id=${encodeURIComponent(session_id || '')}`),
  toggleFavorite: (item_id, session_id) => req('/favorites', {
    method: 'POST', body: JSON.stringify({ item_id, session_id }),
  }),
  getProfile: (session_id) => req(`/profile?session_id=${encodeURIComponent(session_id || '')}`),
  saveProfile: (data) => req('/profile', { method: 'POST', body: JSON.stringify(data) }),
  reviews: (item_id) => req(`/feedback/${encodeURIComponent(item_id)}`),
  splitBill: (tray_ids, people, coupon_code) => req('/bill/split', {
    method: 'POST', body: JSON.stringify({ tray_ids, people, coupon_code }),
  }),
  trending: (limit) => req(`/trending?limit=${limit || 5}`),
  specials: () => req('/specials'),
  getItem: (id) => req(`/menu/${encodeURIComponent(id)}`),
  spending: (session_id) => req(`/spending?session_id=${encodeURIComponent(session_id || '')}`),
  coupons: () => req('/coupons'),
  adminOrders: (q, limit) => req(`/admin/orders?q=${encodeURIComponent(q || '')}&limit=${limit || 50}`),
  setOrderStatus: (token, status) => req(`/admin/orders/${encodeURIComponent(token)}`, {
    method: 'PATCH', body: JSON.stringify({ status }),
  }),
  adminFeedback: (limit) => req(`/admin/feedback?limit=${limit || 50}`),
  bulkAvailability: (ids, available) => req('/admin/items/bulk-availability', {
    method: 'POST', body: JSON.stringify({ ids, available }),
  }),
  markAllLive: () => req('/admin/items/mark-all-live', { method: 'POST' }),
  editItem: (id, patch) => req(`/admin/items/${id}`, {
    method: 'PATCH', body: JSON.stringify(patch),
  }),
  adminAlerts: () => req('/admin/alerts'),
  exportUrl: (kind) => `${BASE}/admin/export?kind=${kind || 'menu'}`,
};
