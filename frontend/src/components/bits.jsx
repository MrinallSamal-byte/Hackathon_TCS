import React from 'react';

export function Badge({ children }) {
  return <span className="badge">{children}</span>;
}

export function Toggle({ checked, onChange, label }) {
  return (
    <button
      className="toggle"
      role="switch"
      aria-checked={checked ? 'true' : 'false'}
      aria-label={label || 'toggle'}
      onClick={() => onChange(!checked)}
    >
      <span className="knob" />
    </button>
  );
}

export function Toast({ text }) {
  if (!text) return null;
  return <div className="toast" role="status">{text}</div>;
}

export function SkeletonCard() {
  return (
    <div className="skel" aria-hidden="true">
      <div className="bar" style={{ width: '55%' }} />
      <div className="bar" style={{ width: '85%' }} />
      <div className="bar" style={{ width: '40%' }} />
    </div>
  );
}

export function EmptyState({ title, hint }) {
  return (
    <div className="empty">
      <svg viewBox="0 0 72 72" aria-hidden="true">
        <path d="M12 32 h48 c0 14 -10 24 -24 24 s-24 -10 -24 -24 z" />
        <path d="M20 32 c2 -8 10 -12 16 -12 s14 4 16 12" />
        <line x1="28" y1="12" x2="28" y2="18" />
        <line x1="36" y1="10" x2="36" y2="18" />
        <line x1="44" y1="12" x2="44" y2="18" />
      </svg>
      <div className="micro-label">{title || 'NO MATCHES — RELAXING CONSTRAINTS'}</div>
      <p style={{ color: 'var(--text-2)', fontSize: 14 }}>{hint || 'Try raising the budget or clearing a filter.'}</p>
    </div>
  );
}

export function DietMarker({ tags }) {
  const t = new Set(tags || []);
  const isNonVeg = t.has('non_veg');
  const isEgg = t.has('egg') && !t.has('veg') && !t.has('vegan');
  if (isNonVeg || isEgg) {
    return (
      <span className="diet-marker">
        <span className="nonveg-box" aria-hidden="true" />
        <span className="diet-label">{isNonVeg ? 'NON-VEG' : 'EGG'}</span>
      </span>
    );
  }
  return (
    <span className="diet-marker">
      <span className="veg-box" aria-hidden="true" />
      <span className="diet-label">VEG</span>
    </span>
  );
}
