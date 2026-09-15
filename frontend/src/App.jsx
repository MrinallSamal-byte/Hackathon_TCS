import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Send, SlidersHorizontal, ShoppingBag, Trash2, LayoutGrid,
  MessageSquare, Sun, Moon, Plus, UtensilsCrossed, Flame,
  Menu as MenuIcon, X, Mic, CheckCircle2, ArrowRight, Store, Clock, Sparkles,
  Award, BookOpen, ExternalLink, Timer, Users, Code2
} from 'lucide-react';
import { api } from './api.js';
import { HomePage } from './components/HomePage.jsx';
import { HackathonModal } from './components/HackathonModal.jsx';
import { ChatWindow, QuickChipRow } from './components/chat.jsx';
import { MenuBrowser } from './components/MenuBrowser.jsx';
import { RecommendationCard } from './components/RecommendationCard.jsx';
import { BudgetMeter, TrayPanel, FilterDrawer, num } from './components/panels.jsx';
import { Toast, SkeletonCard, EmptyState } from './components/bits.jsx';
import { AdminPanel } from './components/AdminPanel.jsx';
import { SpendingBadge, TrendingStrip, OrdersPanel, ProfilePanel, OrderTracker, VegToggle } from './components/UserPanels.jsx';

const DEFAULT_CHIPS = ['Under Rs 50', 'Rs 70, spicy veg, 10 mins', 'Show combos', 'Vegan', 'In a hurry', 'Surprise me'];

export default function App() {
  const [view, setView] = useState(() => {
    try {
      const hash = window.location.hash.replace('#', '');
      return ['chat', 'menu', 'admin'].includes(hash) ? hash : 'home';
    } catch {
      return 'home';
    }
  });

  useEffect(() => {
    try {
      if (window.location.hash !== `#${view}`) {
        window.history.replaceState(null, '', `#${view}`);
      }
    } catch { /* ignore */ }
  }, [view]);
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
  const [liveCount, setLiveCount] = useState('48 LIVE');
  const [aiTag, setAiTag] = useState('');
  const [quickAdd, setQuickAdd] = useState([]);
  const [suggest, setSuggest] = useState(null);
  const [queues, setQueues] = useState([]);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [orderModal, setOrderModal] = useState(null);
  const [aboutModal, setAboutModal] = useState(false);
  const [coupon, setCoupon] = useState('');
  const [couponError, setCouponError] = useState('');
  const [discount, setDiscount] = useState(0);
  const [payable, setPayable] = useState(0);
  const [split, setSplit] = useState(null);
  const [favorites, setFavorites] = useState([]);
  const [favOnly, setFavOnly] = useState(false);
  // Veg-only mode: persisted locally, forces veg across chat + menu.
  const [vegOnly, setVegOnly] = useState(() => {
    try { return localStorage.getItem('cb_vegonly') === '1'; } catch { return false; }
  });
  const toggleVeg = (v) => {
    setVegOnly(v);
    try {
      if (v) localStorage.setItem('cb_vegonly', '1');
      else localStorage.removeItem('cb_vegonly');
    } catch { /* ignore */ }
    setPrefs((prev) => {
      const cur = prev.dietary_restrictions || [];
      if (v && !cur.includes('veg')) return { ...prev, dietary_restrictions: [...cur, 'veg'] };
      if (!v) return { ...prev, dietary_restrictions: cur.filter((d) => d !== 'veg') };
      return prev;
    });
    notify(v ? 'VEG-ONLY MODE ON' : 'VEG-ONLY MODE OFF');
  };
  const withVeg = (p) => {
    if (!vegOnly) return p;
    const cur = (p && p.dietary_restrictions) || [];
    return { ...(p || {}), dietary_restrictions: [...new Set([...cur, 'veg'])] };
  };

  // Persistent session
  const [sid, setSid] = useState(() => {
    try {
      let s = localStorage.getItem('cb_session');
      if (!s) { s = Math.random().toString(36).slice(2, 14); localStorage.setItem('cb_session', s); }
      return s;
    } catch { return ''; }
  });
  const [dark, setDark] = useState(false);
  const bottomRef = useRef(null);
  // Refs: toast timer (avoid overlap), send guard (state lags rapid taps),
  // message ids (stable React keys), coupon debounce, sheet dismiss.
  const toastTimer = useRef(null);
  const sendingRef = useRef(false);
  const orderingRef = useRef(false);
  const msgId = useRef(0);
  const couponTimer = useRef(null);
  const [sheetHidden, setSheetHidden] = useState(false);
  useEffect(() => () => {
    clearTimeout(toastTimer.current);
    clearTimeout(couponTimer.current);
  }, []);

  const notify = (t) => {
    setToast(t);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(''), 2400);
  };
  const stamp = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const nextMsg = (m) => ({ id: ++msgId.current, time: stamp(), ...m });

  useEffect(() => {
    document.documentElement.classList.toggle('theme-dark', dark);
  }, [dark]);

  useEffect(() => {
    api.health()
      .then((h) => setLiveCount(`${h.live} ITEMS LIVE`))
      .catch(() => setLiveCount('OFFLINE'));
    api.queues()
      .then((q) => setQueues(q.queues || []))
      .catch(() => {});
    if (sid) {
      api.favorites(sid).then((r) => setFavorites(r.favorites || [])).catch(() => {});
    }
  }, [sid]);

  useEffect(() => {
    if (view === 'chat' && messages.length > 1) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, cards, loading, view]);

  useEffect(() => {
    if (view === 'chat' && messages.length === 0 && !loading) {
      send('Hello', true);
    }
  }, [view]);

  useEffect(() => {
    if (tray.length === 0) setSheetHidden(false);
  }, [tray.length]);

  useEffect(() => {
    if (orderModal || aboutModal) {
      const prevOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      const onKeyDown = (e) => {
        if (e.key === 'Escape') {
          setOrderModal(null);
          setAboutModal(false);
        }
      };
      window.addEventListener('keydown', onKeyDown);
      return () => {
        document.body.style.overflow = prevOverflow;
        window.removeEventListener('keydown', onKeyDown);
      };
    }
  }, [orderModal, aboutModal]);

  async function send(text, silent) {
    const msg = (text || '').trim();
    if (!msg || loading || sendingRef.current) return;
    sendingRef.current = true;
    if (!silent) setMessages((m) => [...m, nextMsg({ role: 'user', text: msg })]);
    setInput('');
    setLoading(true);
    // Clear stale results at request start so the typing indicator never
    // stacks above last turn's cards (skeleton + old picks looked broken).
    setCards([]);
    setSuggest(null);
    setQuickAdd([]);
    const effPrefs = withVeg(prefs);
    try {
      const r = await api.chat(msg, effPrefs, undefined, sid);
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
      const tagged = r.ai && r.ai !== 'rule-based' ? 'AI ASSIST' : '';
      setAiTag(tagged);
      setMessages((m) => [...m, nextMsg({ role: 'bot', text: r.reply || 'Here are some picks from the live menu:' })]);
      if (r.sold_out_item) setCards(r.singles || []);
    } catch (e) {
      setMessages((m) => [...m, nextMsg({
        role: 'bot',
        text: 'Backend offline or busy. Ensure uvicorn is running: uvicorn backend.app:app --reload',
      })]);
    } finally {
      setLoading(false);
      sendingRef.current = false;
    }
  }

  // Handle launch from Home page craving bar
  const launchFromHome = (query) => {
    setView('chat');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (query && query.trim()) {
      send(query.trim());
    } else {
      if (messages.length === 0) {
        send('Hello', true);
      }
    }
  };

  // Browser Web Speech API Voice input in chat composer
  const startComposerVoice = () => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      notify('VOICE INPUT NOT SUPPORTED IN THIS BROWSER');
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    try {
      const recognition = new SpeechRecognition();
      recognition.lang = 'en-IN';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);

      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setInput(transcript);
        setIsListening(false);
        if (transcript.trim()) {
          send(transcript);
        }
      };

      recognition.start();
    } catch (e) {
      setIsListening(false);
    }
  };

  async function revalidate(nextTray, couponCode) {
    if (!nextTray.length) { setTrayMeta({ total: 0, eta: 0, overBy: 0 }); setDiscount(0); setPayable(0); setCouponError(''); setSplit(null); return; }
    const ids = nextTray.map((t) => t.rawId);
    try {
      const v = await api.validateTray(ids, Number(prefs.budget) || undefined, couponCode !== undefined ? couponCode : (coupon || undefined));
      setTrayMeta({ total: v.total, eta: v.eta_minutes, overBy: v.over_by || 0 });
      setDiscount(v.discount || 0);
      setPayable(v.payable ?? v.total);
      setCouponError(v.coupon_error || '');
      if (v.over_budget) notify(`OVER BUDGET +₹${Number(v.over_by).toFixed(0)}`);
      if (v.unavailable && v.unavailable.length) notify(`SOLD OUT: ${v.unavailable.join(', ')}`);
    } catch { notify('TRAY SYNC FAILED — SHOWING LAST KNOWN TOTAL'); }
  }

  function changeCoupon(next) {
    setCoupon(next);
    // Debounce: validate once the user pauses typing, not per keystroke.
    clearTimeout(couponTimer.current);
    couponTimer.current = setTimeout(() => revalidate(tray, next || undefined), 450);
  }

  async function splitTray(people) {
    if (!tray.length) return;
    try {
      const r = await api.splitBill(tray.map((t) => t.rawId), people, coupon || undefined);
      setSplit(r);
      notify(`${people} WAY SPLIT · ₹${Number(r.per_person).toFixed(0)} EACH`);
    } catch { notify('SPLIT FAILED'); }
  }

  function applyProfile(p) {
    // Reflect saved defaults immediately (backend also applies them server-side).
    if (p && typeof p === 'object') {
      setPrefs((prev) => ({
        ...prev,
        ...(p.budget != null ? { budget: p.budget } : {}),
        ...(p.goal ? { goal: p.goal } : {}),
        ...((p.dietary_restrictions || []).length ? { dietary_restrictions: p.dietary_restrictions } : {}),
      }));
    }
  }

  async function toggleFavorite(card) {    const id = card.id || (card.item_ids && card.item_ids[0]);
    if (!id) return;
    try {
      const r = await api.toggleFavorite(id, sid);
      setFavorites(r.favorites || []);
      notify(r.favorited ? `${card.name} SAVED TO FAVORITES` : `${card.name} REMOVED`);
    } catch { notify('FAVORITE FAILED'); }
  }

  async function reorderOrder(order) {
    try {
      const m = await api.menu({ available_only: true });
      const byId = {};
      (m.items || []).forEach((c) => { byId[c.id] = c; });
      const expand = (raw) => (String(raw).startsWith('dyn_') ? String(raw).slice(4).split('__') : [raw]);
      const ids = (order.tray || []).flatMap(expand);
      // Batch: build the whole tray locally, validate ONCE (not per item).
      const adds = ids.map((id) => byId[id]).filter(Boolean).map(makeEntry);
      if (adds.length) {
        const next = [...tray, ...adds];
        setTray(next);
        revalidate(next);
      }
      notify(adds.length ? `${adds.length} ITEMS FROM ${order.token} ADDED` : 'THOSE ITEMS ARE SOLD OUT NOW');
      if (view === 'home') setView('chat');
    } catch { notify('REORDER FAILED'); }
  }

  function makeEntry(card) {
    const isDyn = card.is_dynamic;
    const price = num(card.total_price ?? card.price);
    const entry = {
      key: `${card.id || card.name}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`,
      rawId: card.id || card.name,
      name: card.name,
      price,
    };
    if (isDyn && card.item_ids) entry.rawId = card.id || `dyn_${card.item_ids.join('__')}`;
    return entry;
  }

  function addCard(card) {
    const price = num(card.total_price ?? card.price, NaN);
    if (!Number.isFinite(price)) { notify('PRICE UNAVAILABLE FOR THIS DISH'); return; }
    const next = [...tray, makeEntry(card)];
    setTray(next);
    revalidate(next);
    notify(`${card.name} ADDED TO TRAY`);
  }

  async function feedback(card, rating, comment) {
    try {
      await api.feedback(
        card.id || (card.item_ids && card.item_ids[0]) || card.name,
        rating,
        { budget: prefs.budget, mood: prefs.mood, session_id: sid, ...(comment ? { comment } : {}) }
      );
      notify(rating > 0 ? 'RECOMMENDATION SAVED 👍' : 'FEEDBACK RECORDED 👎');
    } catch { notify('FEEDBACK FAILED'); }
  }

  async function confirmOrder() {
    if (!tray.length) { notify('TRAY EMPTY — ADD ITEMS FIRST'); return; }
    if (orderingRef.current) return; // block double-tap duplicate orders
    orderingRef.current = true;
    try {
      const r = await api.order(tray.map((t) => t.rawId), Number(prefs.budget) || undefined, sid, coupon || undefined);
      setOrderModal(r);
      setMessages((m) => [...m, nextMsg({ role: 'bot', text: `${r.message} Token ${r.token}.` })]);
      setTray([]); setTrayMeta({ total: 0, eta: 0, overBy: 0 });
      setDiscount(0); setPayable(0); setSplit(null);
      notify(`ORDER ${r.token} CONFIRMED`);
    } catch (e) {
      notify('ORDER FAILED — CHECK SOLD-OUT ITEMS');
    } finally {
      orderingRef.current = false;
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
        max_calories: filters.max_cal && filters.max_cal < 1050 ? filters.max_cal : undefined,
        goal: filters.goal || undefined,
        available_only: true,
      });
      setCards(r.items || []);
      setQuickAdd([]);
      setSuggest(null);
      setMessages((m) => [...m, nextMsg({ role: 'bot', text: `// KITCHEN FILTERED — ${r.count} DISHES READY` })]);
    } catch { notify('FILTER BROWSE FAILED'); }
    finally { setLoading(false); }
  }

  async function completeMeal() {
    if (!tray.length) { notify('TRAY EMPTY — ADD AN ITEM FIRST'); return; }
    try {
      const r = await api.suggestFill(tray.map((t) => t.rawId), Number(prefs.budget) || undefined, withVeg(prefs));
      setSuggest(r);
      if (!(r.suggestions || []).length) notify('NO SIDES FIT THE LEFTOVER BUDGET');
    } catch (e) { notify('SUGGESTION FAILED — SET A BUDGET FIRST'); }
  }

  function addAllQuick() {
    const byId = {};
    cards.forEach((c) => { byId[c.id] = c; });
    const adds = quickAdd.map((id) => byId[id]).filter(Boolean).map(makeEntry);
    if (adds.length) {
      const next = [...tray, ...adds];
      setTray(next);
      revalidate(next);
      setQuickAdd([]);
      notify(`${adds.length} ITEMS ADDED TO TRAY`);
    }
  }

  const total = num(trayMeta.total ?? tray.reduce((a, t) => a + num(t.price), 0));

  const railPanel = (
    <aside className="rail" aria-label="Tray and filters">
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <VegToggle vegOnly={vegOnly} onToggle={toggleVeg} />
        <SpendingBadge sessionId={sid} />
      </div>
      <OrderTracker sessionId={sid} notify={notify} />
      <OrdersPanel sessionId={sid} onReorder={reorderOrder} notify={notify} />
      <ProfilePanel sessionId={sid} notify={notify} onSaved={applyProfile} />
      {queues.some((q) => (q.wait_minutes || 0) > 0) && (
        <div className="queue-status-card">
          <div className="queue-header">
            <Clock size={13} color="var(--brand)" />
            <span>LIVE COUNTER WAIT TIMES</span>
          </div>
          <div className="queue-pills">
            {queues.map((q) => (
              <div key={q.counter} className="queue-pill">
                <span className={`queue-dot ${q.wait_minutes > 15 ? 'busy' : q.wait_minutes > 5 ? 'mod' : 'ready'}`} />
                <span className="queue-name">{q.label}</span>
                <span className="queue-time">{q.wait_minutes}m</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <TrayPanel
        tray={tray} budget={Number(prefs.budget) || 0} eta={trayMeta.eta} overBy={trayMeta.overBy}
        onRemove={(k) => { const n = tray.filter((t) => t.key !== k); setTray(n); revalidate(n); }}
        onClear={() => { setTray([]); setTrayMeta({ total: 0, eta: 0, overBy: 0 }); }}
        onOrder={confirmOrder}
        onCompleteMeal={tray.length > 0 ? completeMeal : undefined}
        coupon={coupon} onCoupon={changeCoupon} discount={discount} payable={payable}
        couponError={couponError} split={split} onSplit={splitTray}
      />
      <FilterDrawer
        filters={filters}
        onChange={setFilters}
        onApply={browseWithFilters}
        collapsible={true}
        defaultExpanded={false}
      />
    </aside>
  );

  return (
    <div className="app-shell">
      {/* Floating Cravio Navigation Header */}
      <header className="nav-header">
        <nav className="nav-pill">
          {/* Logo */}
          <button
            type="button" className="brand-logo" aria-label="Go to home"
            onClick={() => setView('home')}
            style={{ background: 'none', border: 'none', cursor: 'pointer', font: 'inherit', color: 'inherit', padding: 0 }}
          >
            <div className="brand-icon"><Flame size={20} /></div>
            <span>biteMatch</span>
            <span className="brand-status-tag">{liveCount}</span>
          </button>

          {/* Nav Links */}
          <div className="nav-links">
            <button
              className={`nav-link${view === 'home' ? ' active' : ''}`}
              onClick={() => { setView('home'); setMobileMenuOpen(false); }}
            >
              Home
            </button>
            <button
              className={`nav-link${view === 'chat' ? ' active' : ''}`}
              onClick={() => { launchFromHome(); setMobileMenuOpen(false); }}
            >
              <MessageSquare size={16} /> AI Chat
            </button>
            <button
              className={`nav-link${view === 'menu' ? ' active' : ''}`}
              onClick={() => { setView('menu'); setMobileMenuOpen(false); }}
            >
              <Store size={16} /> Live Menu
            </button>
            <button
              className={`nav-link${view === 'admin' ? ' active' : ''}`}
              onClick={() => { setView('admin'); setMobileMenuOpen(false); }}
            >
              <LayoutGrid size={16} /> Canteen Admin
            </button>
          </div>

          {/* Action CTAs */}
          <div className="nav-actions">
            {/* 3rd Place Award / About Circle Button */}
            <button
              className="icon-btn about-circle-btn"
              aria-label="About biteMatch · TCS Hackathon 3rd Place"
              title="About Project · 3rd Place at TCS Hackathon"
              onClick={() => setAboutModal(true)}
              style={{
                position: 'relative',
                borderRadius: '50%',
                background: 'var(--brand-soft)',
                color: 'var(--brand)',
                border: '1.5px solid var(--brand-soft-border)',
                width: 38,
                height: 38,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 8px rgba(255, 107, 87, 0.18)',
                cursor: 'pointer'
              }}
            >
              <Award size={18} strokeWidth={2.2} />
              <span style={{
                position: 'absolute',
                top: -3,
                right: -3,
                background: 'var(--brand)',
                color: '#FFFFFF',
                fontSize: '9px',
                fontWeight: 900,
                width: 15,
                height: 15,
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: 'var(--font-data)',
                border: '1.5px solid var(--surface)'
              }}>
                3
              </span>
            </button>

            <button
              className="icon-btn"
              aria-label="Toggle dark / light theme"
              onClick={() => setDark(!dark)}
              title={dark ? "Switch to Warm Light Mode" : "Switch to Obsidian Dark Mode"}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            {tray.length > 0 && (
              <button
                className="btn-cta"
                onClick={() => {
                  if (view === 'home') setView('chat');
                  confirmOrder();
                }}
                style={{ padding: '8px 16px', fontSize: 13 }}
              >
                <ShoppingBag size={16} /> ₹{total.toFixed(0)} ({tray.length})
              </button>
            )}

            {view === 'home' && tray.length === 0 && (
              <button
                className="btn-cta nav-cta-btn"
                onClick={() => launchFromHome()}
              >
                <MessageSquare size={16} /> Launch AI
              </button>
            )}

            <button
              className="mobile-menu-btn"
              aria-label="Toggle mobile menu"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X size={20} /> : <MenuIcon size={20} />}
            </button>
          </div>
        </nav>

        {/* Mobile Dropdown Drawer */}
        {mobileMenuOpen && (
          <div className="mobile-drawer">
            <button
              className={`nav-link${view === 'home' ? ' active' : ''}`}
              onClick={() => { setView('home'); setMobileMenuOpen(false); }}
            >
              Home
            </button>
            <button
              className="nav-link"
              onClick={() => { setMobileMenuOpen(false); setAboutModal(true); }}
              style={{ display: 'flex', alignItems: 'center', gap: 8 }}
            >
              <Award size={16} color="var(--brand)" /> 3rd Place TCS Hackathon · About
            </button>
            <button
              className={`nav-link${view === 'chat' ? ' active' : ''}`}
              onClick={() => { launchFromHome(); setMobileMenuOpen(false); }}
            >
              <MessageSquare size={16} /> AI Chat Discovery
            </button>
            <button
              className={`nav-link${view === 'menu' ? ' active' : ''}`}
              onClick={() => { setView('menu'); setMobileMenuOpen(false); }}
            >
              <Store size={16} /> Live Canteen Menu
            </button>
            <button
              className={`nav-link${view === 'admin' ? ' active' : ''}`}
              onClick={() => { setView('admin'); setMobileMenuOpen(false); }}
            >
              <LayoutGrid size={16} /> Canteen Admin Dashboard
            </button>
          </div>
        )}
      </header>

      {/* View Routing */}
      {view === 'home' ? (
        <HomePage
          onNavigate={(target) => {
            setView(target);
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }}
          onLaunchSearch={launchFromHome}
          liveCount={liveCount}
        />
      ) : view === 'admin' ? (
        <div className="layout layout-admin">
          <main className="admin-column">
            <AdminPanel notify={notify} />
          </main>
        </div>
      ) : view === 'menu' ? (
        <div className="layout layout-menu">
          <main className="menu-column">
            <MenuBrowser
              onAdd={addCard}
              onFeedback={feedback}
              onAlternatives={(card) => { setView('chat'); send(`alternative to ${card.name}`); }}
              notify={notify}
              favorites={favorites}
              onFavorite={toggleFavorite}
              favOnly={favOnly}
              onToggleFavOnly={setFavOnly}
              lockedDietary={vegOnly ? 'veg' : ''}
            />
            <div ref={bottomRef} />
          </main>
          <aside className="rail rail-menu" aria-label="Tray">
            <div style={{ marginBottom: 12 }}>
              <VegToggle vegOnly={vegOnly} onToggle={toggleVeg} />
            </div>
            <OrdersPanel sessionId={sid} onReorder={reorderOrder} notify={notify} />
            <TrayPanel
              tray={tray} budget={Number(prefs.budget) || 0} eta={trayMeta.eta} overBy={trayMeta.overBy}
              onRemove={(k) => { const n = tray.filter((t) => t.key !== k); setTray(n); revalidate(n); }}
              onClear={() => { setTray([]); setTrayMeta({ total: 0, eta: 0, overBy: 0 }); }}
              onOrder={confirmOrder}
              onCompleteMeal={tray.length > 0 ? completeMeal : undefined}
              coupon={coupon} onCoupon={changeCoupon} discount={discount} payable={payable}
              couponError={couponError} split={split} onSplit={splitTray}
            />
          </aside>
        </div>
      ) : (
        /* Chat View */
        <div className="layout">
          <main className="chat-column">
            <div className="chat-messages-container">
              <ChatWindow messages={messages} loading={loading}>
                {loading && <SkeletonCard />}
                {!loading && cards.length === 0 && messages.length > 1 && (
                  <EmptyState hint="No dishes found for this craving — try relaxing budget or clearing a restriction." />
                )}
              </ChatWindow>

              {cards.length > 0 && (
                <div className="section-head">
                  Kitchen Picks {aiTag ? <span className="micro-label" style={{ color: 'var(--brand)', marginLeft: 8 }}>· {aiTag}</span> : null}
                </div>
              )}

              {quickAdd.length > 0 && (
                <button className="btn btn-primary" style={{ width: '100%', marginBottom: 12 }} onClick={addAllQuick}>
                  <ShoppingBag size={16} /> ADD ALL ({quickAdd.length}) TO TRAY IN ONE TAP
                </button>
              )}

              {cards.map((c) => (
                <RecommendationCard
                  key={`pick-${c.id || c.name}`}
                  card={c}
                  onAdd={addCard}
                  onFeedback={feedback}
                  onAlternatives={(card) => send(`alternative to ${card.name}`)}
                  isFavorite={favorites.includes(c.id)}
                  onFavorite={toggleFavorite}
                />
              ))}

              <TrendingStrip onAdd={addCard} notify={notify} />

              <QuickChipRow chips={chips} onPick={(c) => send(c)} />

              {/* Mobile tools: rail panels are desktop-only, so mirror the
                  essentials inline on small screens */}
              <div className="mobile-tools">
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <VegToggle vegOnly={vegOnly} onToggle={toggleVeg} />
                </div>
                <OrderTracker sessionId={sid} notify={notify} />
                <OrdersPanel sessionId={sid} onReorder={reorderOrder} notify={notify} />
                <ProfilePanel sessionId={sid} notify={notify} onSaved={applyProfile} />
              </div>

              {suggest && (suggest.suggestions || []).length > 0 && (
                <>
                  <div className="section-head">
                    Complete Your Meal · ₹{Number(suggest.remaining).toFixed(0)} Left In Budget
                  </div>
                  {suggest.suggestions.map((c) => (
                    <RecommendationCard
                      key={`sug-${c.id || c.name}`}
                      card={c}
                      onAdd={addCard}
                      onFeedback={feedback}
                      onAlternatives={(card) => send(`alternative to ${card.name}`)}
                      isFavorite={favorites.includes(c.id)}
                      onFavorite={toggleFavorite}
                    />
                  ))}
                </>
              )}

              {/* Mobile-Only Quick Filter/Meal Pills */}
              <div className="mobile-chat-actions">
                <button
                  className="btn btn-secondary"
                  style={{ padding: '6px 14px', fontSize: 12, borderRadius: 'var(--r-pill)' }}
                  onClick={() => setShowFilters(!showFilters)}
                >
                  <SlidersHorizontal size={13} /> {showFilters ? 'Hide Filters' : 'Kitchen Filters'}
                </button>
                {tray.length > 0 && (
                  <button
                    className="btn btn-secondary"
                    style={{ padding: '6px 14px', fontSize: 12, borderRadius: 'var(--r-pill)' }}
                    onClick={completeMeal}
                  >
                    <Sparkles size={13} color="var(--brand)" /> Auto-Fill Sides
                  </button>
                )}
              </div>

              {showFilters && (
                <div style={{ marginTop: 12 }}>
                  <FilterDrawer filters={filters} onChange={setFilters} onApply={browseWithFilters} />
                </div>
              )}
            </div>

            {/* Chat Composer Sticky inside Chat Column - Never overlaps sidebar */}
            <div className="chat-composer-wrap">
              <div className="composer-inner">
                <input
                  aria-label="Speak or type your craving"
                  placeholder={isListening ? "Listening to your craving..." : "Ask: Rs 70 mein spicy veg, ready in 10 mins..."}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') send(input); }}
                />

                <button
                  type="button"
                  className={`mic-btn${isListening ? ' listening' : ''}`}
                  style={{ width: 38, height: 38, flexShrink: 0 }}
                  onClick={startComposerVoice}
                  aria-label="Speak craving"
                  title="Speak your craving"
                >
                  <Mic size={18} />
                </button>

                <button
                  className="btn btn-primary"
                  style={{ width: 40, height: 40, borderRadius: '50%', padding: 0, flexShrink: 0 }}
                  aria-label="Send message"
                  onClick={() => send(input)}
                >
                  <Send size={16} />
                </button>
              </div>
            </div>
            {/* Scroll target AFTER the composer: at full scroll the input rests
                in-flow below the last card instead of sticking over it. */}
            <div ref={bottomRef} />
          </main>

          {railPanel}
        </div>
      )}

      {/* Floating Tray Bottom Sheet on Mobile (dismissible; reappears when tray changes) */}
      {(view === 'chat' || view === 'menu') && tray.length > 0 && !sheetHidden && (
        <div className="tray-sheet">
          <button
            type="button" aria-label="Hide tray summary"
            onClick={() => setSheetHidden(true)}
            style={{ position: 'absolute', top: 6, right: 10, background: 'none', border: 'none', color: 'var(--text-3)', fontSize: 16, cursor: 'pointer', padding: 4 }}
          >
            ✕
          </button>
          <BudgetMeter spent={total} budget={Number(prefs.budget) || 0} />
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <input
              aria-label="Coupon code" placeholder="Coupon (STUDENT10)"
              value={coupon} onChange={(e) => changeCoupon(e.target.value.toUpperCase())}
              style={{ flex: 1, minWidth: 0, background: 'var(--surface-2)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '8px 10px', color: 'var(--text-1)', fontSize: 12.5, fontFamily: 'var(--font-data)' }}
            />
          </div>
          {couponError ? <div style={{ fontSize: 12, color: 'var(--red-text)', marginTop: 4 }}>{couponError}</div> : null}
          {discount > 0 ? <div className="mono" style={{ fontSize: 12, color: '#10B981', marginTop: 4 }}>COUPON SAVES ₹{num(discount).toFixed(0)}</div> : null}
          <button className="btn btn-primary" style={{ width: '100%', marginTop: 8 }} onClick={confirmOrder}>
            <ShoppingBag size={16} /> ORDER TRAY ₹{total.toFixed(0)} · {tray.length} ITEMS
          </button>
        </div>
      )}

      {/* Order Confirmation Modal */}
      {orderModal && typeof document !== 'undefined' && createPortal(
        <div
          role="dialog" aria-modal="true" aria-label={`Order ${orderModal.token} confirmed`}
          onKeyDown={(e) => { if (e.key === 'Escape') setOrderModal(null); }}
          onClick={(e) => { if (e.target === e.currentTarget) setOrderModal(null); }}
          style={{
            position: 'fixed', inset: 0, zIndex: 9999,
            background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(10px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 'clamp(10px, 3vw, 20px)',
            animation: 'fadeIn 0.2s ease-out'
          }}
        >
          <div style={{
            background: 'var(--surface)', border: '1.5px solid var(--brand-soft-border)',
            borderRadius: 'clamp(20px, 4vw, 32px)',
            padding: 'clamp(24px, 5vw, 36px) clamp(16px, 4vw, 28px)',
            maxWidth: 'min(460px, calc(100vw - 20px))', width: '100%',
            textAlign: 'center', boxShadow: 'var(--shadow-elevated)', animation: 'modalPop 0.25s cubic-bezier(0.16, 1, 0.3, 1)'
          }}>
            <div style={{
              width: 64, height: 64, borderRadius: '50%', background: 'var(--brand-soft)',
              color: 'var(--brand)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px', boxShadow: '0 8px 24px rgba(255, 107, 87, 0.25)'
            }}>
              <CheckCircle2 size={36} />
            </div>
            <span className="hero-pill-badge" style={{ marginBottom: 8 }}>Kitchen Confirmed</span>
            <h2 style={{ fontSize: 'clamp(20px, 4vw, 26px)', fontWeight: 900, margin: '8px 0', letterSpacing: '-0.03em' }}>
              Your order is in the kitchen!
            </h2>
            <div style={{
              fontSize: 'clamp(24px, 5.5vw, 34px)', fontWeight: 900, color: 'var(--brand)',
              margin: '14px 0', fontFamily: 'var(--font-data)'
            }}>
              TOKEN {orderModal.token}
            </div>
            <p style={{ color: 'var(--text-2)', fontSize: 14.5, lineHeight: 1.6, margin: '0 0 20px' }}>
              Total: <strong>₹{Number(orderModal.total).toFixed(2)}</strong>
              {orderModal.discount ? <> · Coupon {orderModal.coupon} −₹{Number(orderModal.discount).toFixed(2)} · Pay <strong>₹{Number(orderModal.payable).toFixed(2)}</strong></> : null}
              {' '}· Ready in approx <strong>{orderModal.eta_minutes} mins</strong>
              {orderModal.counter_label ? <> · Pickup at <strong>{orderModal.counter_label}</strong></> : null}.
              Show your token at the counter for instant pickup.
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                className="btn btn-secondary"
                style={{ flex: '1 1 140px', padding: '10px 14px', fontSize: 13 }}
                onClick={() => {
                  try {
                    const lines = [
                      'biteMatch — Order Receipt', `Token: ${orderModal.token}`,
                      `Total: Rs ${Number(orderModal.total).toFixed(2)}`,
                      orderModal.discount ? `Coupon ${orderModal.coupon}: -Rs ${Number(orderModal.discount).toFixed(2)} (Pay Rs ${Number(orderModal.payable).toFixed(2)})` : '',
                      orderModal.counter_label ? `Pickup: ${orderModal.counter_label}` : '',
                      `ETA: ~${orderModal.eta_minutes} min`,
                    ].filter(Boolean).join('\n');
                    const blob = new Blob([lines], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${orderModal.token}-receipt.txt`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                  } catch { /* ignore */ }
                }}
              >
                Download receipt
              </button>
              <button
                className="btn btn-primary"
                style={{ flex: '1 1 140px', padding: '10px 14px', fontSize: 13 }}
                onClick={() => setOrderModal(null)}
              >
                Done / Back to Food
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* About Project & TCS Hackathon Modal */}
      {aboutModal && typeof document !== 'undefined' && createPortal(
        <HackathonModal
          onClose={() => setAboutModal(false)}
          onShowToast={(msg) => setToast(msg)}
        />,
        document.body
      )}

      <Toast text={toast} />
    </div>
  );
}
