import React, { useState } from 'react';
import {
  Award, X, Timer, Users, Code2, Sparkles, BookOpen, ExternalLink,
  Copy, Check, Mic, ShieldAlert, HeartPulse, Zap, Layers, Users2,
  Quote, CheckCircle2, ChevronRight
} from 'lucide-react';

const CAPABILITIES = [
  { icon: <Mic size={15} />, title: 'Voice Craving AI', desc: 'Multimodal natural speech & intent parsing' },
  { icon: <Sparkles size={15} />, title: 'Hinglish NLU', desc: 'Understands code-mixed Hindi & campus slang' },
  { icon: <HeartPulse size={15} />, title: 'Clinical Dietary Guard', desc: 'Diabetic carb bounds & allergy validation' },
  { icon: <Zap size={15} />, title: 'Live Queue Telemetry', desc: 'Real-time student rush & wait time estimates' },
  { icon: <Timer size={15} />, title: 'Parallel Prep ETA', desc: 'Multi-station kitchen bottleneck tracking' },
  { icon: <Layers size={15} />, title: 'Smart Tray Auto-Fill', desc: 'Auto-completes balanced combos under budget' },
  { icon: <Users2 size={15} />, title: 'Split Billing', desc: 'Instant student group bill calculation' },
  { icon: <Code2 size={15} />, title: 'Canteen Admin KDS', desc: 'Live kitchen telemetry & stock manager' },
];

export function HackathonModal({ onClose, onShowToast }) {
  const [copied, setCopied] = useState(false);
  const DOCS_URL = 'https://hackathon-tcs-azure.vercel.app/docs';

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(DOCS_URL);
      setCopied(true);
      if (onShowToast) onShowToast('API Documentation URL copied to clipboard! 📋');
      setTimeout(() => setCopied(false), 2400);
    } catch {
      if (onShowToast) onShowToast('Could not copy link to clipboard');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="About biteMatch and TCS Hackathon 3rd Place"
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(10, 10, 15, 0.78)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'clamp(10px, 3vw, 16px)',
        animation: 'fadeIn 0.2s ease-out'
      }}
    >
      <div
        className="custom-modal-scroll"
        style={{
          background: 'var(--surface)',
          border: '1.5px solid var(--brand-soft-border)',
          borderRadius: 'clamp(20px, 4vw, 32px)',
          maxWidth: 620,
          width: '100%',
          maxHeight: 'min(92vh, 780px)',
          overflowY: 'auto',
          boxShadow: '0 25px 60px -12px rgba(0, 0, 0, 0.35), 0 0 40px -10px rgba(255, 107, 87, 0.25)',
          animation: 'modalPop 0.28s cubic-bezier(0.16, 1, 0.3, 1)',
          position: 'relative',
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        {/* Ambient background glow decoration */}
        <div style={{
          position: 'absolute',
          top: -30,
          right: -30,
          width: 220,
          height: 220,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(255, 107, 87, 0.18) 0%, rgba(245, 158, 11, 0.08) 60%, transparent 80%)',
          pointerEvents: 'none',
          filter: 'blur(30px)'
        }} />

        {/* Sticky/Fixed Modal Header */}
        <div style={{
          padding: 'clamp(16px, 3vw, 22px) clamp(16px, 4vw, 28px) 14px',
          borderBottom: '1px solid var(--hairline)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          background: 'var(--surface)',
          zIndex: 10,
          borderTopLeftRadius: 'clamp(20px, 4vw, 32px)',
          borderTopRightRadius: 'clamp(20px, 4vw, 32px)',
          gap: 10
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', minWidth: 0, flex: 1 }}>
            <div className="hackathon-trophy-badge" style={{ fontSize: 'clamp(11px, 2.7vw, 12.5px)', padding: '5px clamp(8px, 2.5vw, 14px)' }}>
              <span className="trophy-pulse-dot" />
              <Award size={14} style={{ color: '#F59E0B', flexShrink: 0 }} />
              <span>3rd Place Winner</span>
              <span style={{ opacity: 0.6, fontSize: 10 }}>•</span>
              <span style={{ fontWeight: 800 }}>TCS Hackathon 2026</span>
            </div>
            <span style={{
              fontSize: 10.5,
              fontFamily: 'var(--font-data)',
              background: 'var(--surface-2)',
              color: 'var(--text-3)',
              padding: '3px 8px',
              borderRadius: 'var(--r-pill)',
              border: '1px solid var(--hairline)'
            }}>
              60-Min Sprint
            </span>
          </div>

          <button
            className="icon-btn"
            aria-label="Close dialog"
            onClick={onClose}
            style={{
              width: 32,
              height: 32,
              minWidth: 32,
              minHeight: 32,
              borderRadius: '50%',
              background: 'var(--surface-2)',
              border: '1px solid var(--hairline)',
              color: 'var(--text-2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s ease',
              flexShrink: 0
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Modal Scrollable Content */}
        <div style={{ padding: 'clamp(16px, 3.5vw, 24px) clamp(14px, 3.5vw, 28px)', display: 'flex', flexDirection: 'column', gap: 20 }}>
          
          {/* Main Title & Story */}
          <div>
            <h2 style={{
              fontSize: 'clamp(22px, 3.8vw, 29px)',
              fontWeight: 900,
              margin: '0 0 10px',
              letterSpacing: '-0.03em',
              lineHeight: 1.2,
              color: 'var(--text-1)'
            }}>
              Built in under 1 hour by{' '}
              <span className="gradient-title-accent">Mrinal Samal & 5 teammates</span>.
            </h2>
            <p style={{ color: 'var(--text-2)', fontSize: 14.5, lineHeight: 1.65, margin: 0 }}>
              Created during a fast-paced hackathon hosted by <strong>TCS</strong>, where the challenge prompt was to build a <em>base recommendation system for a college canteen</em>. Competing against multiple teams, our solution clinched <strong>3rd Place</strong>!
            </p>
          </div>

          {/* Metrics Grid */}
          <div className="metrics-quad-grid">
            <div className="metric-pill-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, color: 'var(--brand)', marginBottom: 4 }}>
                <Timer size={14} />
                <span className="micro-label" style={{ fontSize: 9.5 }}>SPRINT</span>
              </div>
              <div className="mono" style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>&lt; 1 Hr</div>
              <div style={{ fontSize: 10.5, color: 'var(--text-3)', marginTop: 2 }}>Idea to Live Prod</div>
            </div>

            <div className="metric-pill-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, color: 'var(--brand)', marginBottom: 4 }}>
                <Users size={14} />
                <span className="micro-label" style={{ fontSize: 9.5 }}>TEAM</span>
              </div>
              <div className="mono" style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>6 Devs</div>
              <div style={{ fontSize: 10.5, color: 'var(--text-3)', marginTop: 2 }}>Mrinal + 5 Teammates</div>
            </div>

            <div className="metric-pill-card featured">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, color: '#D97706', marginBottom: 4 }}>
                <Award size={14} />
                <span className="micro-label" style={{ fontSize: 9.5, color: '#D97706' }}>AWARD</span>
              </div>
              <div className="mono" style={{ fontSize: 18, fontWeight: 900, color: '#D97706' }}>3rd Place 🥉</div>
              <div style={{ fontSize: 10.5, color: 'var(--text-2)', marginTop: 2, fontWeight: 600 }}>TCS Hackathon 2026</div>
            </div>

            <div className="metric-pill-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, color: '#10B981', marginBottom: 4 }}>
                <CheckCircle2 size={14} />
                <span className="micro-label" style={{ fontSize: 9.5 }}>TESTS</span>
              </div>
              <div className="mono" style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>164 Pass</div>
              <div style={{ fontSize: 10.5, color: 'var(--text-3)', marginTop: 2 }}>100% Passing Tests</div>
            </div>
          </div>

          {/* Engineered Capabilities Grid */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{
                fontSize: 11,
                fontWeight: 800,
                color: 'var(--text-2)',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                fontFamily: 'var(--font-data)'
              }}>
                ⚡ Engineered in 60 Minutes
              </div>
              <span style={{ fontSize: 11.5, color: 'var(--brand)', fontWeight: 700 }}>
                8 Production Modules
              </span>
            </div>

            <div className="capability-badges-grid">
              {CAPABILITIES.map((cap, idx) => (
                <div key={idx} className="capability-badge-item">
                  <div className="cap-icon-box">
                    {cap.icon}
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 750, fontSize: 12.5, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {cap.title}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {cap.desc}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Builder's Authentic Reflection */}
          <div className="reflection-quote-card" style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <div style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: 'var(--brand-soft)',
              color: 'var(--brand)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              marginTop: 2
            }}>
              <Quote size={16} />
            </div>
            <div>
              <div style={{ fontStyle: 'italic', color: 'var(--text-1)', lineHeight: 1.65, fontSize: 13.5 }}>
                “I know a few minor things are missing or could use polish, but yeah — this is what we could build in under 1 hour using modern AI capabilities nowadays! What would traditionally take days was conceived, tested against 164 test specs, and deployed live in 60 minutes.”
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
                <div style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, var(--brand), #FF9040)',
                  color: '#fff',
                  fontSize: 10,
                  fontWeight: 900,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}>
                  MS
                </div>
                <div style={{ fontSize: 12.5, fontWeight: 800, color: 'var(--text-1)' }}>
                  Mrinal Samal & Teammates
                </div>
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>• Lead Builders</span>
              </div>
            </div>
          </div>

          {/* Interactive API & Architecture Hub */}
          <div className="api-hub-card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, fontWeight: 800, color: 'var(--brand)', letterSpacing: '0.04em' }}>
                <BookOpen size={16} /> INTERACTIVE API & ARCHITECTURE DOCS
              </div>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
                fontSize: 10.5,
                fontFamily: 'var(--font-data)',
                color: '#10B981',
                background: 'rgba(16, 185, 129, 0.1)',
                padding: '2px 8px',
                borderRadius: 'var(--r-pill)',
                fontWeight: 700
              }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10B981', display: 'inline-block' }} />
                OpenAPI 3.1 Live
              </span>
            </div>

            <p style={{ margin: '0 0 12px', fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>
              Interested in how the deterministic recommendation model, clinical dietary constraints, and live telemetry endpoints work under the hood? Explore or test them in real-time:
            </p>

            {/* Endpoints preview tag list */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
              <span className="api-endpoint-chip"><span className="method-post">POST</span> /chat</span>
              <span className="api-endpoint-chip"><span className="method-get">GET</span> /menu</span>
              <span className="api-endpoint-chip"><span className="method-post">POST</span> /orders</span>
              <span className="api-endpoint-chip"><span className="method-get">GET</span> /queue-telemetry</span>
            </div>

            {/* Actions Bar: Open Docs & Copy Link */}
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <a
                href={DOCS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-secondary"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  flex: '1 1 200px',
                  justifyContent: 'center',
                  padding: '10px 16px',
                  fontSize: 13,
                  fontWeight: 700,
                  color: 'var(--brand)',
                  background: 'var(--surface)',
                  border: '1.5px solid var(--brand-soft-border)',
                  borderRadius: 12,
                  textDecoration: 'none',
                  transition: 'all 0.15s ease'
                }}
              >
                <BookOpen size={15} />
                <span>Open Interactive Swagger Docs</span>
                <ExternalLink size={14} />
              </a>

              <button
                type="button"
                onClick={handleCopyLink}
                className="btn"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '10px 14px',
                  fontSize: 12.5,
                  fontWeight: 700,
                  color: copied ? '#10B981' : 'var(--text-2)',
                  background: 'var(--surface)',
                  border: copied ? '1.5px solid rgba(16, 185, 129, 0.4)' : '1px solid var(--hairline)',
                  borderRadius: 12,
                  transition: 'all 0.2s ease',
                  cursor: 'pointer'
                }}
                title="Copy docs URL to clipboard"
              >
                {copied ? <Check size={14} style={{ color: '#10B981' }} /> : <Copy size={14} />}
                <span>{copied ? 'Copied URL!' : 'Copy Link'}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div style={{
          padding: '14px clamp(14px, 3.5vw, 28px) clamp(16px, 3.5vw, 24px)',
          borderTop: '1px solid var(--hairline)',
          background: 'var(--surface)',
          display: 'flex',
          gap: 12,
          borderBottomLeftRadius: 'clamp(20px, 4vw, 32px)',
          borderBottomRightRadius: 'clamp(20px, 4vw, 32px)'
        }}>
          <button
            className="btn btn-primary"
            style={{
              width: '100%',
              padding: '12px 20px',
              fontSize: 14.5,
              fontWeight: 800,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              borderRadius: 14,
              boxShadow: 'var(--brand-shadow)'
            }}
            onClick={onClose}
          >
            <span>Back to Canteen App</span>
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
