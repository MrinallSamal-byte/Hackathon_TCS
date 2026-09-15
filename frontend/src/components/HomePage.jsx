import React, { useState, useEffect } from 'react';
import {
  Mic, Sparkles, Clock, Utensils, MessageSquare,
  Flame, ShoppingBag, ShieldCheck, ArrowRight,
  TrendingUp, Dumbbell, Zap, ChevronRight, Store,
  CheckCircle2, Compass, RefreshCw, Users, Award, Timer, Code2, BookOpen, ExternalLink,
  Copy, Check, HeartPulse, Layers, Users2, Quote
} from 'lucide-react';

export function HomePage({ onNavigate, onLaunchSearch, liveCount }) {
  const [cravingInput, setCravingInput] = useState('');
  const [activeStep, setActiveStep] = useState(0);
  const [activeShowcaseTab, setActiveShowcaseTab] = useState(0);
  const [isListening, setIsListening] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [copiedDocLink, setCopiedDocLink] = useState(false);

  const handleCopyDocs = async () => {
    try {
      await navigator.clipboard.writeText('https://hackathon-tcs-azure.vercel.app/docs');
      setCopiedDocLink(true);
      setTimeout(() => setCopiedDocLink(false), 2400);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (typeof window !== 'undefined' && ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      setSpeechSupported(true);
    }
  }, []);

  const startVoiceCraving = () => {
    if (!speechSupported) {
      alert('Voice recognition is not supported in this browser. Please type your craving!');
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    try {
      const recognition = new SpeechRecognition();
      recognition.lang = 'en-IN'; // Indian English / Hinglish friendly
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);

      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setCravingInput(transcript);
        setIsListening(false);
        if (transcript.trim()) {
          onLaunchSearch(transcript);
        }
      };

      recognition.start();
    } catch (e) {
      setIsListening(false);
    }
  };

  const handleSearchSubmit = (e) => {
    if (e) e.preventDefault();
    if (cravingInput.trim()) {
      onLaunchSearch(cravingInput.trim());
    } else {
      onNavigate('chat');
    }
  };

  const PRESET_CHIPS = [
    { label: '🔥 Spicy Maggi & Chai under ₹60', query: 'Spicy Maggi with cutting chai under Rs 60' },
    { label: '💪 High protein post-gym', query: 'High protein gym meal with eggs or paneer' },
    { label: '⚡ Ready in 5 mins', query: 'Quick food in 5 minutes in a hurry' },
    { label: '🌱 Jain / Veg special', query: 'Jain pure veg food no onion no garlic' },
    { label: '☕ Cold Coffee & Sandwich', query: 'Cold coffee and grilled sandwich' },
  ];

  const STEPS = [
    {
      num: 1,
      title: 'Speak your craving',
      desc: 'Tell biteMatch what you want using voice, English, or campus Hinglish like "Rs 60 mein kuch spicy veg".',
      screenTitle: 'Craving Input',
      screenBadge: 'Voice / Text Input',
      screenPreview: (
        <div style={{ padding: '16px 12px', background: 'var(--surface)', borderRadius: 20, boxShadow: 'var(--shadow-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--brand-soft)', padding: '8px 12px', borderRadius: 14, color: 'var(--brand)', fontWeight: 700, fontSize: 13, marginBottom: 12 }}>
            <Mic size={16} /> "Rs 60 mein spicy maggi aur chai"
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', display: 'flex', justifyContent: 'space-between' }}>
            <span>Auto-detects: Budget ₹60</span>
            <span style={{ color: 'var(--brand)', fontWeight: 700 }}>Hinglish OK</span>
          </div>
        </div>
      )
    },
    {
      num: 2,
      title: 'AI understands',
      desc: 'Our engine extracts budget, cuisine, dietary safety, spice tolerance, and break time limits instantly.',
      screenTitle: 'AI Analysis',
      screenBadge: 'Deterministic Core',
      screenPreview: (
        <div style={{ padding: '16px 12px', background: 'var(--surface)', borderRadius: 20, boxShadow: 'var(--shadow-card)' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--hairline)' }}>
              <span style={{ color: 'var(--text-2)' }}>Budget Filter</span>
              <strong style={{ color: 'var(--brand)' }}>Max ₹60.00</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--hairline)' }}>
              <span style={{ color: 'var(--text-2)' }}>Diet / Allergens</span>
              <strong>Veg (Verified)</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
              <span style={{ color: 'var(--text-2)' }}>Live Prep ETA</span>
              <strong style={{ color: '#10B981' }}>~8 Mins</strong>
            </div>
          </div>
        </div>
      )
    },
    {
      num: 3,
      title: 'Get smart matches',
      desc: 'See live canteen dishes and budget-optimized combos that leave zero hunger and zero wasted cash.',
      screenTitle: 'Smart Combo Match',
      screenBadge: '48 Items Live',
      screenPreview: (
        <div style={{ padding: '14px 12px', background: 'var(--surface)', borderRadius: 20, boxShadow: 'var(--shadow-card)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <strong style={{ fontSize: 14 }}>Masala Maggi + Cutting Chai</strong>
            <span style={{ color: 'var(--brand)', fontWeight: 800 }}>₹55.00</span>
          </div>
          <div style={{ display: 'flex', gap: 6, fontSize: 10, color: 'var(--text-2)' }}>
            <span style={{ background: 'var(--surface-2)', padding: '2px 6px', borderRadius: 8 }}>8 MIN PREP</span>
            <span style={{ background: 'var(--surface-2)', padding: '2px 6px', borderRadius: 8 }}>410 KCAL</span>
            <span style={{ background: '#ECFDF5', color: '#10B981', fontWeight: 700, padding: '2px 6px', borderRadius: 8 }}>₹5 SAVED</span>
          </div>
        </div>
      )
    },
    {
      num: 4,
      title: 'Skip the queue & enjoy',
      desc: 'Confirm your tray, receive a CB-XXX pickup token, and walk to the counter right as your meal is hot.',
      screenTitle: 'Token Confirmed',
      screenBadge: 'Live Counter Route',
      screenPreview: (
        <div style={{ padding: '16px 12px', background: 'var(--surface)', borderRadius: 20, textAlign: 'center', boxShadow: 'var(--shadow-card)' }}>
          <div style={{ fontSize: 11, letterSpacing: '0.1em', color: 'var(--text-2)', textTransform: 'uppercase' }}>PICKUP TOKEN</div>
          <div style={{ fontSize: 28, fontWeight: 900, color: 'var(--brand)', margin: '4px 0' }}>CB-429</div>
          <div style={{ fontSize: 12, color: '#10B981', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <CheckCircle2 size={14} /> Ready at Counter 1
          </div>
        </div>
      )
    }
  ];

  return (
    <div className="home-page">
      {/* =====================================================================
          HERO SECTION
          ===================================================================== */}
      <section className="hero-wrap">
        <div className="blur-orb-1" />
        <div className="blur-orb-2" />

        <div className="hero-container">
          {/* Left Column: Messaging & Search */}
          <div className="hero-content">
            <div className="hero-pill-badge">
              <Sparkles size={14} /> AI Campus Food Discovery App
            </div>

            <h1 className="hero-title">
              Speak your craving. <br />
              <span className="highlight">Beat the canteen rush.</span>
            </h1>

            <p className="hero-desc">
              Tell biteMatch what you feel like eating, your budget, and break time.
              Our AI matches live canteen counters, calculates prep time, and builds budget-friendly combos in seconds.
            </p>

            {/* Interactive Craving Search Box */}
            <form className="hero-search-bar" onSubmit={handleSearchSubmit}>
              <input
                type="text"
                className="hero-search-input"
                placeholder={isListening ? "Listening to your craving..." : "Try: Rs 60 mein spicy maggi, veg, 10 mins..."}
                value={cravingInput}
                onChange={(e) => setCravingInput(e.target.value)}
              />

              <button
                type="button"
                className={`mic-btn${isListening ? ' listening' : ''}`}
                onClick={startVoiceCraving}
                aria-label="Speak your craving"
                title="Click and speak your craving"
              >
                <Mic size={20} />
              </button>

              <button type="submit" className="btn-cta" style={{ height: 44, padding: '0 20px', borderRadius: 9999 }}>
                Find Food <ArrowRight size={16} />
              </button>
            </form>

            {/* Quick Chips */}
            <div className="hero-chip-row">
              {PRESET_CHIPS.map((c) => (
                <button
                  key={c.label}
                  type="button"
                  className="hero-chip"
                  onClick={() => onLaunchSearch(c.query)}
                >
                  {c.label}
                </button>
              ))}
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: 14, marginTop: 28, flexWrap: 'wrap' }}>
              <button className="btn btn-primary" onClick={() => onNavigate('chat')}>
                <MessageSquare size={18} /> Launch AI Assistant
              </button>
              <button className="btn btn-secondary" onClick={() => onNavigate('menu')}>
                <Store size={18} /> Explore Live Menu ({liveCount})
              </button>
            </div>
          </div>

          {/* Right Column: Phone Mockup Frame & Floating Badges */}
          <div className="phone-mockup-wrapper">
            {/* Floating Badge 1 */}
            <div className="floating-badge float-1">
              <div className="badge-icon-box">
                <Sparkles size={18} />
              </div>
              <div>
                <div className="badge-text-top">AI Match</div>
                <div className="badge-text-val">{liveCount || '48'} Items Live</div>
              </div>
            </div>

            {/* Floating Badge 2 */}
            <div className="floating-badge float-2">
              <div className="badge-icon-box">
                <Mic size={18} />
              </div>
              <div>
                <div className="badge-text-top">Craving</div>
                <div className="badge-text-val">Spicy • Under ₹60</div>
              </div>
            </div>

            {/* Floating Badge 3 */}
            <div className="floating-badge float-3">
              <div className="badge-icon-box">
                <Clock size={18} />
              </div>
              <div>
                <div className="badge-text-top">Counter 1</div>
                <div className="badge-text-val">~4 min wait</div>
              </div>
            </div>

            {/* Physical Smartphone Device Mockup */}
            <div className="phone-device">
              <div className="phone-island" />
              <div className="phone-screen">
                {/* Mini App UI inside the phone */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <span style={{ fontSize: 13, fontWeight: 900, color: 'var(--brand)' }}>biteMatch</span>
                  <span style={{ fontSize: 10, background: 'var(--brand-soft)', color: 'var(--brand)', padding: '2px 8px', borderRadius: 9999, fontWeight: 700 }}>
                    AI LIVE
                  </span>
                </div>

                {/* Simulated Chat Message */}
                <div style={{ background: 'var(--surface-2)', padding: '10px 12px', borderRadius: '16px 16px 16px 4px', fontSize: 12, marginBottom: 10, lineHeight: 1.4 }}>
                  Good afternoon! Found your <strong>Rs 60 spicy craving</strong> before the lunch queue backs up:
                </div>

                {/* Simulated Recommendation Card */}
                <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 16, padding: '12px', boxShadow: 'var(--shadow-card)', marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 800, fontSize: 14 }}>
                    <span>Masala Maggi + Chai</span>
                    <span style={{ color: 'var(--brand)' }}>₹50.00</span>
                  </div>
                  <div style={{ display: 'flex', gap: 6, fontSize: 10, color: 'var(--text-2)', marginTop: 4 }}>
                    <span>⚡ 8 MIN</span>
                    <span>🥗 VEG</span>
                    <span style={{ color: 'var(--brand)', fontWeight: 700 }}>COMBO</span>
                  </div>
                  <p style={{ fontSize: 11, color: 'var(--text-2)', margin: '6px 0 8px', lineHeight: 1.3 }}>
                    Classic chef-paired study combo. Fits comfortably inside your ₹60 budget.
                  </p>
                  <button
                    className="btn-cta"
                    style={{ width: '100%', height: 32, fontSize: 12, padding: 0, justifyContent: 'center' }}
                    onClick={() => onNavigate('chat')}
                  >
                    + Add to Tray
                  </button>
                </div>

                {/* Simulated Budget Meter */}
                <div style={{ marginTop: 'auto', background: 'var(--surface-2)', padding: '8px 12px', borderRadius: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontWeight: 700 }}>
                    <span>TRAY: ₹50 / ₹60</span>
                    <span style={{ color: '#10B981' }}>₹10 REMAINING</span>
                  </div>
                  <div style={{ height: 4, background: 'var(--hairline)', borderRadius: 2, marginTop: 4, overflow: 'hidden' }}>
                    <div style={{ width: '83%', height: '100%', background: 'linear-gradient(90deg, #10B981, #FF6B57)' }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          HOW IT WORKS (4-Step Interactive Section)
          ===================================================================== */}
      <section id="how-it-works" className="steps-section">
        <div className="section-title-wrap">
          <h2 className="section-headline">How biteMatch Works</h2>
          <p className="section-subtitle">A faster, smarter way to discover food and beat the campus rush without endless scrolling.</p>
        </div>

        <div className="steps-grid">
          {/* Steps 1 & 2 */}
          <div style={{ display: 'grid', gap: 16 }}>
            {[STEPS[0], STEPS[1]].map((step, idx) => (
              <button
                key={step.num}
                type="button"
                className={`step-btn${activeStep === idx ? ' active' : ''}`}
                onClick={() => setActiveStep(idx)}
              >
                <div className="step-badge">{step.num}</div>
                <div className="step-content">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    {idx === 0 ? <Mic size={18} color="var(--brand)" /> : <Zap size={18} color="var(--brand)" />}
                    <h3>{step.title}</h3>
                  </div>
                  <p>{step.desc}</p>
                </div>
              </button>
            ))}
          </div>

          {/* Interactive Center Phone Showcase */}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <div className="phone-device" style={{ width: 'min(270px, calc(100vw - 36px))' }}>
              <div className="phone-island" />
              <div className="phone-screen" style={{ justifyContent: 'center' }}>
                <div style={{ textAlign: 'center', marginBottom: 14 }}>
                  <span style={{ fontSize: 10, fontWeight: 800, color: 'var(--brand)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                    STEP {STEPS[activeStep].num} OF 4
                  </span>
                  <div style={{ fontSize: 16, fontWeight: 900, color: 'var(--text-1)' }}>
                    {STEPS[activeStep].screenTitle}
                  </div>
                </div>
                {STEPS[activeStep].screenPreview}
                <div style={{ textAlign: 'center', marginTop: 14 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-2)' }}>
                    biteMatch Smart Engine
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Steps 3 & 4 */}
          <div style={{ display: 'grid', gap: 16 }}>
            {[STEPS[2], STEPS[3]].map((step, idx) => (
              <button
                key={step.num}
                type="button"
                className={`step-btn${activeStep === (idx + 2) ? ' active' : ''}`}
                onClick={() => setActiveStep(idx + 2)}
              >
                <div className="step-badge">{step.num}</div>
                <div className="step-content">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    {idx === 0 ? <Sparkles size={18} color="var(--brand)" /> : <ShoppingBag size={18} color="var(--brand)" />}
                    <h3>{step.title}</h3>
                  </div>
                  <p>{step.desc}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* =====================================================================
          FROM CRAVING TO RECOMMENDATION IN SECONDS
          ===================================================================== */}
      <section style={{ padding: '60px 20px', maxWidth: 1180, margin: '0 auto' }}>
        <div style={{ display: 'grid', gap: 40, alignItems: 'center' }} className="from-craving-grid">
          <div style={{ display: 'grid', gap: 18 }}>
            <div className="hero-pill-badge" style={{ marginBottom: 0 }}>
              Craving to Match
            </div>
            <h2 className="section-headline" style={{ textAlign: 'left', margin: 0 }}>
              From craving to recommendation in seconds.
            </h2>
            <p className="section-subtitle" style={{ textAlign: 'left' }}>
              biteMatch turns casual student language into practical canteen discovery by understanding what you mean, what counters are busy, and what fits your pockets.
            </p>

            <div style={{ display: 'grid', gap: 14, marginTop: 12 }}>
              <div className="feat-card" style={{ padding: 20 }}>
                <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                  <div className="badge-icon-box"><MessageSquare size={20} /></div>
                  <div>
                    <h4 style={{ margin: 0, fontSize: 16, fontWeight: 800 }}>Describe your mood</h4>
                    <p style={{ margin: 0, fontSize: 13, color: 'var(--text-2)' }}>Say things like "I want something spicy, light, and under ₹50."</p>
                  </div>
                </div>
              </div>

              <div className="feat-card" style={{ padding: 20 }}>
                <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                  <div className="badge-icon-box"><ShieldCheck size={20} /></div>
                  <div>
                    <h4 style={{ margin: 0, fontSize: 16, fontWeight: 800 }}>AI filters the rush</h4>
                    <p style={{ margin: 0, fontSize: 13, color: 'var(--text-2)' }}>Checks counter wait queues, kitchen prep time, and allergens automatically.</p>
                  </div>
                </div>
              </div>

              <div className="feat-card" style={{ padding: 20 }}>
                <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                  <div className="badge-icon-box"><Sparkles size={20} /></div>
                  <div>
                    <h4 style={{ margin: 0, fontSize: 16, fontWeight: 800 }}>Discover budget combos</h4>
                    <p style={{ margin: 0, fontSize: 13, color: 'var(--text-2)' }}>Builds paired meals that fill leftover budget with delicious sides.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          FEATURES DESIGNED AROUND CAMPUS LIFE
          ===================================================================== */}
      <section id="features" style={{ padding: '70px 20px', maxWidth: 1180, margin: '0 auto' }}>
        <div className="section-title-wrap">
          <h2 className="section-headline">Features designed around campus cravings.</h2>
          <p className="section-subtitle">Built specifically for students with fast break times, tight budgets, and authentic taste.</p>
        </div>

        <div className="features-grid">
          <div className="feat-card">
            <div className="feat-icon-box"><Mic size={24} /></div>
            <h3>Voice & Hinglish Cravings</h3>
            <p>Speak naturally in English or Hinglish. biteMatch understands terms like "kam teekha", "jaldi", "pocket friendly", and "garma garam".</p>
          </div>

          <div className="feat-card">
            <div className="feat-icon-box"><ShieldCheck size={24} /></div>
            <h3>Strict Budget Optimizer</h3>
            <p>Deterministic mathematics guarantee you never overspend your budget by a single rupee, with real-time overage warnings.</p>
          </div>

          <div className="feat-card">
            <div className="feat-icon-box"><Clock size={24} /></div>
            <h3>Live Counter Queues & Real ETA</h3>
            <p>Monitors wait times at the Snack Bar, Main Meals, and Beverage counters to route your orders around peak rushes.</p>
          </div>

          <div className="feat-card">
            <div className="feat-icon-box"><Sparkles size={24} /></div>
            <h3>Smart Dynamic Combos</h3>
            <p>Chef-paired dynamic combos that calculate parallel preparation times so everything is freshly served together.</p>
          </div>

          <div className="feat-card">
            <div className="feat-icon-box"><Dumbbell size={24} /></div>
            <h3>Gym & Nutrition Goals</h3>
            <p>Sort dishes by real protein grams for post-workout recovery or low calories for light study snacking.</p>
          </div>

          <div className="feat-card">
            <div className="feat-icon-box"><ShoppingBag size={24} /></div>
            <h3>Token Orders & Quick Reorder</h3>
            <p>Receive live CB-XXX pickup tokens and reorder your favorite past meals in a single tap without re-browsing.</p>
          </div>
        </div>
      </section>

      {/* =====================================================================
          SMART FOOD INTELLIGENCE (Connected Flow)
          ===================================================================== */}
      <section className="intel-wrapper">
        <div className="section-title-wrap" style={{ marginBottom: 30 }}>
          <div className="hero-pill-badge" style={{ marginBottom: 10 }}>Smart Canteen Intelligence</div>
          <h2 className="section-headline" style={{ fontSize: 'clamp(28px, 3.8vw, 46px)' }}>
            Connected across counters, menus, and cravings.
          </h2>
          <p className="section-subtitle">
            biteMatch turns a loose craving into a hot meal by connecting natural language with real kitchen data.
          </p>
        </div>

        <div className="intel-grid">
          <div className="intel-card">
            <div className="badge-icon-box"><MessageSquare size={20} /></div>
            <div className="intel-step-tag">What you say</div>
            <h4>spicy, veg, under ₹70</h4>
            <p>Starts with your craving exactly as you speak or type it.</p>
          </div>

          <div className="intel-card">
            <div className="badge-icon-box"><Zap size={20} /></div>
            <div className="intel-step-tag">What AI understands</div>
            <h4>budget, diet, break time</h4>
            <p>Turns casual words into clear structured constraints.</p>
          </div>

          <div className="intel-card">
            <div className="badge-icon-box"><Clock size={20} /></div>
            <div className="intel-step-tag">What Canteen checks</div>
            <h4>counter queues, live stock</h4>
            <p>Verifies real ingredients, allergen safety, and counter wait times.</p>
          </div>

          <div className="intel-card">
            <div className="badge-icon-box"><Sparkles size={20} /></div>
            <div className="intel-step-tag">What you get</div>
            <h4>matched meals & token</h4>
            <p>Smart picks ready on time with zero queue standing.</p>
          </div>
        </div>
      </section>

      {/* =====================================================================
          ABOUT SECTION — TCS HACKATHON & TEAM
          ===================================================================== */}
      <section id="about" style={{ padding: '0 clamp(10px, 3vw, 20px) clamp(40px, 6vw, 80px)', maxWidth: 1180, margin: '0 auto' }}>
        <div style={{
          background: 'var(--surface)',
          border: '1.5px solid var(--hairline)',
          borderRadius: 'clamp(20px, 4vw, 36px)',
          padding: 'clamp(18px, 4vw, 56px)',
          boxShadow: 'var(--shadow-card)',
          position: 'relative',
          overflow: 'hidden'
        }}>
          {/* Ambient accent glow */}
          <div style={{
            position: 'absolute',
            top: -60,
            right: -60,
            width: 260,
            height: 260,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(255, 107, 87, 0.16) 0%, rgba(245, 158, 11, 0.08) 55%, transparent 75%)',
            filter: 'blur(50px)',
            pointerEvents: 'none'
          }} />

          <div style={{ maxWidth: 860, position: 'relative', zIndex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
              <div className="hackathon-trophy-badge">
                <span className="trophy-pulse-dot" />
                <Award size={15} style={{ color: '#F59E0B' }} />
                <span>3rd Place Winner</span>
                <span style={{ opacity: 0.6, fontSize: 11 }}>•</span>
                <span style={{ fontWeight: 800 }}>TCS Hackathon 2026</span>
              </div>
              <span style={{
                fontSize: 11.5,
                fontFamily: 'var(--font-data)',
                background: 'var(--surface-2)',
                color: 'var(--text-3)',
                padding: '4px 10px',
                borderRadius: 'var(--r-pill)',
                border: '1px solid var(--hairline)'
              }}>
                60-Min Sprint
              </span>
            </div>

            <h2 style={{ fontSize: 'clamp(28px, 4vw, 44px)', fontWeight: 900, letterSpacing: '-0.03em', margin: '0 0 16px', lineHeight: 1.15 }}>
              Built in under 1 hour by{' '}
              <span className="gradient-title-accent">Mrinal Samal & 5 teammates</span> — 3rd Place Winner.
            </h2>

            <p style={{ fontSize: 16, color: 'var(--text-2)', lineHeight: 1.75, margin: '0 0 16px' }}>
              This project was created during a fast-paced hackathon conducted by <strong>TCS</strong>. The original problem statement challenged teams to build a <em>base recommendation system for a college canteen</em>. Our project secured <strong>3rd Place</strong> among competing teams!
            </p>

            <p style={{ fontSize: 16, color: 'var(--text-2)', lineHeight: 1.75, margin: '0 0 26px' }}>
              Rather than stopping at a basic script, <strong>Mrinal Samal</strong> and <strong>5 other teammates</strong> rallied together to see how far modern AI and rapid full-stack architecture could take the idea within 60 minutes. We engineered <strong>biteMatch</strong> with a comprehensive set of production-grade features: multimodal voice craving capture, conversational Hinglish comprehension, clinical dietary validation, diabetic carb guards, live queue telemetry, parallel prep ETA calculation, dynamic combo auto-fill, coupon discounts, split billing, and an end-to-end canteen kitchen admin console.
            </p>

            {/* Sprint Stats Grid */}
            <div className="metrics-quad-grid" style={{ marginBottom: 28 }}>
              <div className="metric-pill-card" style={{ padding: '16px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: 'var(--brand)', marginBottom: 6 }}>
                  <Timer size={16} />
                  <span className="micro-label" style={{ fontSize: 10 }}>SPRINT DURATION</span>
                </div>
                <div className="mono" style={{ fontSize: 24, fontWeight: 900, color: 'var(--text-1)' }}>&lt; 1 Hour</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>Ideation to live deployment</div>
              </div>

              <div className="metric-pill-card" style={{ padding: '16px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: 'var(--brand)', marginBottom: 6 }}>
                  <Users size={16} />
                  <span className="micro-label" style={{ fontSize: 10 }}>TEAM</span>
                </div>
                <div className="mono" style={{ fontSize: 24, fontWeight: 900, color: 'var(--text-1)' }}>6 Builders</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>Mrinal Samal + 5 teammates</div>
              </div>

              <div className="metric-pill-card featured" style={{ padding: '16px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: '#D97706', marginBottom: 6 }}>
                  <Award size={16} />
                  <span className="micro-label" style={{ fontSize: 10, color: '#D97706' }}>AWARD</span>
                </div>
                <div className="mono" style={{ fontSize: 24, fontWeight: 900, color: '#D97706' }}>3rd Place 🥉</div>
                <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4, fontWeight: 600 }}>TCS Hackathon 2026</div>
              </div>

              <div className="metric-pill-card" style={{ padding: '16px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, color: '#10B981', marginBottom: 6 }}>
                  <Code2 size={16} />
                  <span className="micro-label" style={{ fontSize: 10 }}>TEST SUITE</span>
                </div>
                <div className="mono" style={{ fontSize: 24, fontWeight: 900, color: 'var(--text-1)' }}>164 Tests</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>FastAPI + Vite + OpenRouter</div>
              </div>
            </div>

            {/* Engineered Modules Showcase */}
            <div style={{ marginBottom: 28 }}>
              <div style={{
                fontSize: 11.5,
                fontWeight: 800,
                color: 'var(--text-2)',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                fontFamily: 'var(--font-data)',
                marginBottom: 12
              }}>
                ⚡ 8 Production Modules Engineered in 60 Minutes
              </div>
              <div className="capability-badges-grid">
                <div className="capability-badge-item">
                  <div className="cap-icon-box"><Mic size={15} /></div>
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--text-1)' }}>Voice Craving AI</strong>
                    <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>Multimodal speech & intent parser</span>
                  </div>
                </div>
                <div className="capability-badge-item">
                  <div className="cap-icon-box"><Sparkles size={15} /></div>
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--text-1)' }}>Hinglish NLU</strong>
                    <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>Understands Hindi-English campus slang</span>
                  </div>
                </div>
                <div className="capability-badge-item">
                  <div className="cap-icon-box"><HeartPulse size={15} /></div>
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--text-1)' }}>Clinical Dietary Guard</strong>
                    <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>Diabetic carb limits & allergens</span>
                  </div>
                </div>
                <div className="capability-badge-item">
                  <div className="cap-icon-box"><Zap size={15} /></div>
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--text-1)' }}>Live Queue Telemetry</strong>
                    <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>Real-time student rush & wait times</span>
                  </div>
                </div>
                <div className="capability-badge-item">
                  <div className="cap-icon-box"><Timer size={15} /></div>
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--text-1)' }}>Parallel Prep ETA</strong>
                    <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>Kitchen bottleneck predictor</span>
                  </div>
                </div>
                <div className="capability-badge-item">
                  <div className="cap-icon-box"><Layers size={15} /></div>
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--text-1)' }}>Smart Tray Auto-Fill</strong>
                    <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>Nutritious budget combos</span>
                  </div>
                </div>
                <div className="capability-badge-item">
                  <div className="cap-icon-box"><Users2 size={15} /></div>
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--text-1)' }}>Split Billing</strong>
                    <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>Instant friend share calculation</span>
                  </div>
                </div>
                <div className="capability-badge-item">
                  <div className="cap-icon-box"><Code2 size={15} /></div>
                  <div>
                    <strong style={{ display: 'block', fontSize: 13, color: 'var(--text-1)' }}>Canteen Admin KDS</strong>
                    <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>Live orders & kitchen telemetry</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Honest Builder Reflection Note */}
            <div className="reflection-quote-card" style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 16,
              padding: 'clamp(14px, 3.5vw, 20px) clamp(14px, 3.5vw, 24px)',
              marginBottom: 24
            }}>
              <div style={{
                width: 38, height: 38, borderRadius: '50%',
                background: 'var(--brand-soft)', color: 'var(--brand)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                marginTop: 2
              }}>
                <Quote size={18} />
              </div>
              <div>
                <strong style={{ fontSize: 15, color: 'var(--text-1)', display: 'block', marginBottom: 4 }}>
                  A Note from the Builders
                </strong>
                <p style={{ margin: 0, fontSize: 14, color: 'var(--text-2)', lineHeight: 1.65, fontStyle: 'italic' }}>
                  "I know a few minor things are missing or could use polish, but yeah — this is what we could build in under 1 hour using modern AI capabilities nowadays! What traditionally took days of boilerplates, mocks, and manual UI wiring was designed, tested against 164 test specs, and shipped end-to-end in 60 minutes."
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
                  <div style={{
                    width: 22, height: 22, borderRadius: '50%',
                    background: 'linear-gradient(135deg, var(--brand), #FF9040)',
                    color: '#fff', fontSize: 10, fontWeight: 900,
                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                  }}>
                    MS
                  </div>
                  <div style={{ fontSize: 12.5, fontWeight: 800, color: 'var(--brand)' }}>
                    Mrinal Samal & Team
                  </div>
                  <span style={{ fontSize: 11.5, color: 'var(--text-3)' }}>• TCS Hackathon 2026 (3rd Place)</span>
                </div>
              </div>
            </div>

            {/* Interactive API & Architecture Documentation Hub */}
            <div className="api-hub-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 800, color: 'var(--brand)', letterSpacing: '0.04em' }}>
                  <BookOpen size={17} /> WANT TO LEARN HOW THIS PROJECT WORKS?
                </div>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  fontSize: 11,
                  fontFamily: 'var(--font-data)',
                  color: '#10B981',
                  background: 'rgba(16, 185, 129, 0.1)',
                  padding: '3px 9px',
                  borderRadius: 'var(--r-pill)',
                  fontWeight: 700
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10B981', display: 'inline-block' }} />
                  Live OpenAPI 3.1
                </span>
              </div>
              <p style={{ margin: '0 0 12px', fontSize: 14.5, color: 'var(--text-2)', lineHeight: 1.65 }}>
                If you are interested in exploring the deterministic scoring model, clinical dietary algorithms, or interacting with the endpoints directly, check out our live interactive API documentation:
              </p>

              {/* Endpoints preview tags */}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
                <span className="api-endpoint-chip"><span className="method-post">POST</span> /chat</span>
                <span className="api-endpoint-chip"><span className="method-get">GET</span> /menu</span>
                <span className="api-endpoint-chip"><span className="method-post">POST</span> /orders</span>
                <span className="api-endpoint-chip"><span className="method-get">GET</span> /queue-telemetry</span>
              </div>

              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <a
                  href="https://hackathon-tcs-azure.vercel.app/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                    textDecoration: 'none',
                    fontSize: 13.5,
                    fontWeight: 700,
                    padding: '10px 18px',
                    color: 'var(--brand)',
                    background: 'var(--surface)',
                    border: '1.5px solid var(--brand-soft-border)',
                    borderRadius: 12
                  }}
                >
                  <BookOpen size={16} />
                  <span>Open Interactive Swagger Docs</span>
                  <ExternalLink size={14} />
                </a>

                <button
                  type="button"
                  onClick={handleCopyDocs}
                  className="btn"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '10px 16px',
                    fontSize: 13,
                    fontWeight: 700,
                    color: copiedDocLink ? '#10B981' : 'var(--text-2)',
                    background: 'var(--surface)',
                    border: copiedDocLink ? '1.5px solid rgba(16, 185, 129, 0.4)' : '1px solid var(--hairline)',
                    borderRadius: 12,
                    cursor: 'pointer'
                  }}
                  title="Copy docs URL"
                >
                  {copiedDocLink ? <Check size={15} style={{ color: '#10B981' }} /> : <Copy size={15} />}
                  <span>{copiedDocLink ? 'Copied URL!' : 'Copy Link'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          CAMPUS LAUNCH BANNER & CTA
          ===================================================================== */}
      <section style={{ padding: '0 clamp(10px, 3vw, 20px) clamp(40px, 6vw, 80px)', maxWidth: 1180, margin: '0 auto' }}>
        <div className="cta-banner" style={{
          background: 'linear-gradient(135deg, #FFF8F5 0%, #FFFFFF 52%, #FFE7DF 100%)',
          borderRadius: 'clamp(24px, 4vw, 40px)', padding: 'clamp(28px, 5vw, 48px) clamp(16px, 4vw, 36px)',
          boxShadow: 'var(--shadow-elevated)', border: '1px solid var(--hairline)',
          display: 'grid', gap: 24, alignItems: 'center'
        }}>
          <div style={{ maxWidth: 640 }}>
            <div className="hero-pill-badge"><Sparkles size={14} /> Ready for your next meal</div>
            {/* Ink is explicit: this banner stays light in BOTH themes, so it
                must not inherit the (white in dark mode) theme text color. */}
            <h2 style={{ fontSize: 'clamp(32px, 4.5vw, 56px)', fontWeight: 900, letterSpacing: '-0.04em', margin: '12px 0 16px', lineHeight: 1.05, color: '#161616' }}>
              biteMatch is live at your campus canteen.
            </h2>
            <p style={{ fontSize: 16, color: '#55565C', lineHeight: 1.7, margin: '0 0 24px' }}>
              Speak your craving or browse the live menu now. Save your break time for eating, not standing in long counter lines.
            </p>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <button className="btn btn-primary" onClick={() => onNavigate('chat')}>
                <MessageSquare size={18} /> Start AI Discovery
              </button>
              <button className="btn btn-secondary" onClick={() => onNavigate('menu')}>
                <Store size={18} /> View Today's Menu
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          CRAVIO-STYLE FOOTER
          ===================================================================== */}
      <footer className="cravio-footer">
        <div className="footer-inner">
          <div>
            <div className="brand-logo" onClick={() => onNavigate('home')}>
              <div className="brand-icon"><Flame size={20} /></div>
              <span>biteMatch</span>
            </div>
            <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, marginTop: 14, maxWidth: 320 }}>
              AI-powered campus canteen food discovery for students who know what they crave before they know where to order.
            </p>
          </div>

          <div>
            <strong style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Discovery</strong>
            <div style={{ display: 'grid', gap: 10, marginTop: 14, fontSize: 14 }}>
              <a href="#how-it-works" style={{ color: 'var(--text-2)', textDecoration: 'none' }}>How it Works</a>
              <a href="#features" style={{ color: 'var(--text-2)', textDecoration: 'none' }}>Features</a>
              <a href="#about" style={{ color: 'var(--text-2)', textDecoration: 'none' }}>About the Team</a>
              <span style={{ color: 'var(--text-2)', cursor: 'pointer' }} onClick={() => onNavigate('chat')}>AI Chat</span>
              <span style={{ color: 'var(--text-2)', cursor: 'pointer' }} onClick={() => onNavigate('menu')}>Live Menu</span>
            </div>
          </div>

          <div>
            <strong style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Campus Counters</strong>
            <div style={{ display: 'grid', gap: 10, marginTop: 14, fontSize: 14 }}>
              <span style={{ color: 'var(--text-2)' }}>Counter 1 · Snack Bar</span>
              <span style={{ color: 'var(--text-2)' }}>Counter 2 · Main Meals</span>
              <span style={{ color: 'var(--text-2)' }}>Counter 3 · Beverages</span>
              <span style={{ color: 'var(--brand)', fontWeight: 700, cursor: 'pointer' }} onClick={() => onNavigate('admin')}>Canteen Admin</span>
            </div>
          </div>

          <div>
            <strong style={{ fontSize: 14, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Status</strong>
            <div style={{ marginTop: 14, fontSize: 14, color: 'var(--text-2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#10B981', fontWeight: 700, marginBottom: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981' }} />
                {liveCount || 'MENU LOADING…'}
              </div>
              <p style={{ fontSize: 12, margin: 0 }}>Campus Canteen v1.0 · Fast Deterministic Core + OpenRouter AI</p>
            </div>
          </div>
        </div>

        <div style={{ maxWidth: 1180, margin: '40px auto 0', paddingTop: 24, borderTop: '1px solid var(--hairline)', display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-3)', flexWrap: 'wrap', gap: 12 }}>
          <span>© 2026 biteMatch. Inspired by Cravio. Made for students.</span>
          <span>Zero queue waiting · Safe dietary validation</span>
        </div>

        <div className="footer-watermark">BITEMATCH</div>
      </footer>
    </div>
  );
}
