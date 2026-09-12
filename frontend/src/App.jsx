import React, { useEffect, useRef, useState } from 'react';
import { Send, SlidersHorizontal, ShoppingBag, Trash2, LayoutGrid, MessageSquare, Sun, Moon, Plus, UtensilsCrossed } from 'lucide-react';
import { api } from './api.js';
import { ChatWindow, QuickChipRow } from './components/chat.jsx';
import { MenuBrowser } from './components/MenuBrowser.jsx';
import { RecommendationCard } from './components/RecommendationCard.jsx';
import { BudgetMeter, TrayPanel, FilterDrawer } from './components/panels.jsx';
import { Toast, SkeletonCard, EmptyState } from './components/bits.jsx';
import { AdminPanel } from './components/AdminPanel.jsx';

const DEFAULT_CHIPS = ['Under Rs 50', 'Rs 70, spicy veg, 10 mins', 'Show combos', 'Vegan', 'In a hurry'];

export default function App() {
  const [view, setView] = useState('chat');
  const [messages, setMessages] = useState([]);
  const [cards, setCards] = useState([]);
  const [chips, setChips] = useState(DEFAULT_CHIPS);
  const [prefs, setPrefs] = useState({});
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState('');
  const [tray, setTray] = useState([]);
  const [trayMeta, setTrayMeta] = useState({ total: 0, eta: 0, overBy: 0 });
  const [filters, setFilters] = useState({ category: '', max_price: 250, dietary: '', max_spice: 3, max_prep: 25, goal: '' });
  const [showFilters, setShowFilters] = useState(false);
  const [liveCount, setLiveCount] = useState('—');
  const [aiTag, setAiTag] = useState('');
  const [quickAdd, setQuickAdd] = useState([]);
  const [suggest, setSuggest] = useState(null);
  const [queues, setQueues] = useState([]);
  // Persistent session: the backend remembers prefs/orders/likes per id
  // (Supabase chat_memory when configured, JSON mirror otherwise).
  const [sid, setSid] = useState(() => {
    try {
      let s = localStorage.getItem('cb_session');
      if (!s) { s = Math.random().toString(36).slice(2, 14); localStorage.setItem('cb_session', s); }
      return s;
    } catch { return ''; }
  });
  const [light, setLight] = useState(false);
  const bottomRef = useRef(null);

  const notify = (t) => { setToast(t); setTimeout(() => setToast(''), 2200); };
  const stamp = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const budget = Number(prefs.budget || filters.max_price || 100);

  useEffect(() => {
    document.documentElement.classList.toggle('theme-light', light);
  }, [light]);

  useEffect(() => {
    api.health().then((h) => setLiveCount(`${h.live} ITEMS LIVE`)).catch(() => setLiveCount('OFFLINE'));
    api.queues().then((q) => setQueues(q.queues || [])).catch(() => {});
    send('Hello', true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, cards, loading]);

  async function send(text, silent) {
    const msg = (text || '').trim();
    if (!msg || loading) return;
    if (!silent) setMessages((m) => [...m, { role: 'user', text: msg, time: stamp() }]);
    setInput('');
    setLoading(true);
    try {
      const r = await api.chat(msg, prefs, undefined, sid);
      if (r.session_id && r.session_id !== sid) {
        setSid(r.session_id);
        try { localStorage.setItem('cb_session', r.session_id); } catch { /* ignore */ }
      }
      if (r.prefs) setPrefs(r.prefs);
      const all = [...(r.singles || []), ...(r.combos || [])];
      setCards(all);
      setChips(r.chips || DEFAULT_CHIPS);
      setQuickAdd(r.quick_add || []);
      setSuggest(null);
      const tagged = r.ai && r.ai !== 'rule-based' ? r.ai : '';
      setAiTag(tagged);
      setMessages((m) => [...m, { role: 'bot', text: r.reply, time: stamp() }]);
      if (r.sold_out_item) setCards(r.singles || []);
    } catch (e) {
      setMessages((m) => [...m, { role: 'bot', text: 'Backend unreachable. Start it with: uvicorn backend.app:app --reload (port 8000).', time: stamp() }]);
    } finally {
      setLoading(false);
    }
  }

  async function revalidate(nextTray) {
    if (!nextTray.length) { setTrayMeta({ total: 0, eta: 0, overBy: 0 }); return; }
    const ids = nextTray.map((t) => t.rawId);
    try {
      const v = await api.validateTray(ids, Number(prefs.budget) || undefined);
      setTrayMeta({ total: v.total, eta: v.eta_minutes, overBy: v.over_by || 0 });
      if (v.over_budget) notify(`OVER BUDGET +₹${Number(v.over_by).toFixed(0)}`);
      if (v.unavailable && v.unavailable.length) notify(`SOLD OUT: ${v.unavailable.join(', ')}`);
    } catch { /* ignore */ }
  }

  function addCard(card) {
    const isDyn = card.is_dynamic;
    const entry = {
      key: `${card.id || card.name}-${Date.now()}`,
      rawId: card.id || card.name,
      name: card.name,
      price: Number(card.total_price ?? card.price),
    };
    if (isDyn && card.item_ids) entry.rawId = card.id || `dyn_${card.item_ids.join('__')}`;
    const next = [...tray, entry];
    setTray(next);
    revalidate(next);
    notify(`${card.name} ADDED`);
  }

  async function feedback(card, rating) {
    try {
      await api.feedback(card.id || (card.item_ids && card.item_ids[0]) || card.name, rating, { budget: prefs.budget, mood: prefs.mood, session_id: sid });
      notify(rating > 0 ? 'LIKED — LOGGED' : 'DISLIKED — LOGGED');
    } catch { notify('FEEDBACK FAILED'); }
  }

  async function confirmOrder() {
    if (!tray.length) { notify('TRAY EMPTY'); return; }
    try {
      const r = await api.order(tray.map((t) => t.rawId), Number(prefs.budget) || undefined, sid);
      setMessages((m) => [...m, { role: 'bot', text: `${r.message} Token ${r.token}.`, time: stamp() }]);
      setTray([]); setTrayMeta({ total: 0, eta: 0, overBy: 0 });
      notify(`ORDER ${r.token} CONFIRMED`);
    } catch (e) {
      notify('ORDER FAILED — CHECK SOLD-OUT');
    }
  }

  async function browseWithFilters() {
    setLoading(true);
    try {
      const r = await api.menu({
        category: filters.category || undefined,
        max_price: filters.max_price,
        dietary: filters.dietary || undefined,
        max_spice: filters.max_spice,
        max_prep: filters.max_prep,
        goal: filters.goal || undefined,
        available_only: true,
      });
      setCards(r.items || []);
      setQuickAdd([]);
      setSuggest(null);
      setMessages((m) => [...m, { role: 'bot', text: `// FILTERED — ${r.count} ITEMS`, time: stamp() }]);
    } catch { notify('BROWSE FAILED'); }
    finally { setLoading(false); }
  }

  async function completeMeal() {
    if (!tray.length) { notify('TRAY EMPTY — ADD SOMETHING FIRST'); return; }
    try {
      const r = await api.suggestFill(tray.map((t) => t.rawId), Number(prefs.budget) || undefined, prefs);
      setSuggest(r);
      if (!(r.suggestions || []).length) notify('NOTHING FITS THE LEFTOVER');
    } catch (e) { notify('SUGGEST FAILED — SET A BUDGET'); }
  }

  function addAllQuick() {
    const byId = {};
    cards.forEach((c) => { byId[c.id] = c; });
    let n = 0;
    quickAdd.forEach((id) => { if (byId[id]) { addCard(byId[id]); n += 1; } });
    if (n) { setQuickAdd([]); notify(`${n} ITEMS ADDED`); }
  }

  const total = trayMeta.total || tray.reduce((a, t) => a + Number(t.price), 0);

  const railPanel = (
    <aside className="rail" aria-label="Tray and filters">
      {queues.length > 0 && (
        <div className="micro-label mono">
          QUEUES · {queues.map((q) => `${q.counter.toUpperCase()} ${q.wait_minutes}M`).join(' · ')}
        </div>
      )}
      <TrayPanel
        tray={tray} budget={Number(prefs.budget) || 0} eta={trayMeta.eta} overBy={trayMeta.overBy}
        onRemove={(k) => { const n = tray.filter((t) => t.key !== k); setTray(n); revalidate(n); }}
        onClear={() => { setTray([]); setTrayMeta({ total: 0, eta: 0, overBy: 0 }); }}
        onOrder={confirmOrder}
      />
      <button className="btn btn-secondary" style={{ width: '100%' }} onClick={completeMeal}>
        <Plus size={16} strokeWidth={1.5} /> COMPLETE MY MEAL
      </button>
      <FilterDrawer filters={filters} onChange={setFilters} />
    </aside>
  );

  const menuAlternatives = (card) => { setView('chat'); send(`alternative to ${card.name}`); };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <span className="wordmark"><span className="brand-accent" />campusbite</span>
          <div className="micro-label mono">MENU v1.0 — {liveCount} · {stamp()}</div>
        </div>
        <div className="header-actions">
          <div className="tabs" role="tablist">
            <button className={`tab${view === 'chat' ? ' active' : ''}`} onClick={() => setView('chat')}><MessageSquare size={16} strokeWidth={1.5} style={{ verticalAlign: -3 }} /> CHAT</button>
            <button className={`tab${view === 'menu' ? ' active' : ''}`} onClick={() => setView('menu')}><UtensilsCrossed size={16} strokeWidth={1.5} style={{ verticalAlign: -3 }} /> MENU</button>
            <button className={`tab${view === 'admin' ? ' active' : ''}`} onClick={() => setView('admin')}><LayoutGrid size={16} strokeWidth={1.5} style={{ verticalAlign: -3 }} /> ADMIN</button>
          </div>
          <button className="icon-btn" aria-label="Toggle theme" onClick={() => setLight(!light)}>
            {light ? <Moon size={18} strokeWidth={1.5} /> : <Sun size={18} strokeWidth={1.5} />}
          </button>
        </div>
      </header>

      {view === 'admin' ? (
        <main className="chat-column" style={{ maxWidth: 960 }}>
          <AdminPanel notify={notify} />
        </main>
      ) : view === 'menu' ? (
        <div className="layout">
          <main className="chat-column" style={{ paddingBottom: 120 }}>
            <MenuBrowser onAdd={addCard} onFeedback={feedback} onAlternatives={menuAlternatives} notify={notify} />
            <div ref={bottomRef} />
          </main>
          {railPanel}
        </div>
      ) : (
        <div className="layout">
          <main className="chat-column">
            <ChatWindow messages={messages} loading={loading}>
              {loading && <SkeletonCard />}
              {!loading && cards.length === 0 && messages.length > 2 && (
                <EmptyState hint="No cards right now — adjust budget, time, or filters." />
              )}
            </ChatWindow>

            {cards.length > 0 && <div className="section-head">// RECOMMENDED{aiTag ? <span className="micro-label" style={{ marginLeft: 8 }}>AI · {aiTag}</span> : null}</div>}
            {quickAdd.length > 0 && (
              <button className="btn btn-primary" style={{ width: '100%', marginBottom: 8 }} onClick={addAllQuick}>
                <ShoppingBag size={16} strokeWidth={1.5} /> ADD ALL ({quickAdd.length}) TO TRAY — ONE TAP
              </button>
            )}
            {cards.map((c, i) => (
              <RecommendationCard
                key={(c.id || c.name) + i}
                card={c}
                onAdd={addCard}
                onFeedback={feedback}
                onAlternatives={(card) => send(`alternative to ${card.name}`)}
              />
            ))}
            <QuickChipRow chips={chips} onPick={(c) => send(c)} />
            {suggest && (suggest.suggestions || []).length > 0 && (
              <>
                <div className="section-head">// COMPLETE YOUR MEAL — Rs {Number(suggest.remaining).toFixed(0)} LEFT</div>
                {suggest.suggestions.map((c, i) => (
                  <RecommendationCard key={(c.id || c.name) + i} card={c} onAdd={addCard} onFeedback={feedback} onAlternatives={(card) => send(`alternative to ${card.name}`)} />
                ))}
              </>
            )}

            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button className="btn btn-secondary" onClick={() => setShowFilters(!showFilters)}>
                <SlidersHorizontal size={16} strokeWidth={1.5} /> FILTERS
              </button>
              <button className="btn btn-secondary" onClick={browseWithFilters}>APPLY FILTERS</button>
              <button className="btn btn-secondary" onClick={completeMeal}>COMPLETE MY MEAL</button>
              <button className="btn btn-secondary" onClick={() => { setTray([]); setTrayMeta({ total: 0, eta: 0, overBy: 0 }); notify('TRAY CLEARED'); }}>
                <Trash2 size={16} strokeWidth={1.5} /> CLEAR TRAY
              </button>
            </div>
            {showFilters && <div style={{ marginTop: 12 }}><FilterDrawer filters={filters} onChange={setFilters} /></div>}

            <div ref={bottomRef} />
          </main>

          {railPanel}
        </div>
      )}

      {(view === 'chat' || view === 'menu') && (
        <>
          {tray.length > 0 && (
            <div className="tray-sheet">
              <BudgetMeter spent={total} budget={Number(prefs.budget) || 0} />
              <button className="btn btn-primary" style={{ width: '100%' }} onClick={confirmOrder}>
                <ShoppingBag size={16} strokeWidth={1.5} /> TRAY ₹{total.toFixed(0)} · {tray.length} ITEMS · ORDER
              </button>
            </div>
          )}
          {view === 'chat' && (
          <div className="composer">
            <div className="composer-inner">
              <input
                aria-label="Message CampusBite"
                placeholder="Try: Rs 70, spicy veg, 10 mins"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') send(input); }}
              />
              <button className="btn btn-primary" aria-label="Send message" onClick={() => send(input)}>
                <Send size={18} strokeWidth={1.5} />
              </button>
            </div>
          </div>
          )}
        </>
      )}
      <Toast text={toast} />
    </div>
  );
}
