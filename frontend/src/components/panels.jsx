import React from 'react';

export function BudgetMeter({ spent, budget }) {
  const b = Number(budget || 0);
  const s = Number(spent || 0);
  const pct = b > 0 ? Math.min(100, (s / b) * 100) : 0;
  const over = b > 0 && s > b;
  return (
    <div className={`budget-wrap${over ? ' over' : ''}`} role="status" aria-label="Budget meter">
      <div className="budget-label mono">
        <span>{over ? `OVER BUDGET +₹${(s - b).toFixed(0)}` : `BUDGET ₹${s.toFixed(0)} / ₹${b.toFixed(0)}`}</span>
        <span>{b > 0 ? `${pct.toFixed(0)}%` : ''}</span>
      </div>
      <div className="budget-track"><div className="budget-fill" style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

export function TrayPanel({ tray, budget, eta, overBy, onRemove, onClear, onOrder }) {
  const total = tray.reduce((a, t) => a + Number(t.price || t.total_price || 0), 0);
  return (
    <div className="tray" aria-label="Your tray">
      <div className="section-head">// YOUR TRAY</div>
      <BudgetMeter spent={total} budget={budget || 0} />
      {tray.length === 0 && <p style={{ color: 'var(--text-2)', fontSize: 14 }}>Tray is empty. Add cards with ADD.</p>}
      {tray.map((t) => (
        <div className="tray-row" key={t.key}>
          <span>{t.name}</span>
          <span className="tray-price mono">₹{Number(t.price || t.total_price || 0).toFixed(2)}</span>
          <button className="icon-btn" style={{ width: 32, height: 32, minHeight: 32 }} aria-label={`Remove ${t.name}`} onClick={() => onRemove(t.key)}>×</button>
        </div>
      ))}
      {tray.length > 0 && (
        <>
          <div className="tray-total mono"><span>TOTAL</span><span>₹{total.toFixed(2)}</span></div>
          <div className="micro-label">ETA {eta || 0} MIN · PARALLEL PREP</div>
          {overBy > 0 && <div className="micro-label" style={{ color: 'var(--red-text)' }}>EXCEEDS BUDGET BY ₹{overBy.toFixed(0)}</div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn btn-secondary" onClick={onClear}>CLEAR</button>
            <button className="btn btn-primary" onClick={onOrder}>CONFIRM ORDER</button>
          </div>
        </>
      )}
    </div>
  );
}

export function FilterDrawer({ filters, onChange }) {
  const set = (k, v) => onChange({ ...filters, [k]: v });
  return (
    <div className="drawer" aria-label="Filters">
      <div className="section-head">// FILTERS</div>
      <label htmlFor="f-cat">CATEGORY</label>
      <select id="f-cat" value={filters.category || ''} onChange={(e) => set('category', e.target.value)}>
        <option value="">ALL</option>
        <option value="breakfast">BREAKFAST</option>
        <option value="main_course">MAIN COURSE</option>
        <option value="snack">SNACK</option>
        <option value="beverage">BEVERAGE</option>
        <option value="dessert">DESSERT</option>
        <option value="combo">COMBO</option>
      </select>
      <label htmlFor="f-price">MAX PRICE ₹{filters.max_price || 250}</label>
      <input id="f-price" type="range" min="15" max="250" value={filters.max_price || 250} onChange={(e) => set('max_price', Number(e.target.value))} />
      <label htmlFor="f-diet">DIETARY</label>
      <select id="f-diet" value={filters.dietary || ''} onChange={(e) => set('dietary', e.target.value)}>
        <option value="">ANY</option>
        <option value="veg">VEG</option>
        <option value="vegan">VEGAN</option>
        <option value="jain">JAIN</option>
        <option value="gluten_free">GLUTEN-FREE</option>
        <option value="halal">HALAL</option>
      </select>
      <label htmlFor="f-spice">MAX SPICE {filters.max_spice ?? 3}</label>
      <input id="f-spice" type="range" min="0" max="3" value={filters.max_spice ?? 3} onChange={(e) => set('max_spice', Number(e.target.value))} />
      <label htmlFor="f-prep">MAX PREP {filters.max_prep || 25} MIN</label>
      <input id="f-prep" type="range" min="2" max="25" value={filters.max_prep || 25} onChange={(e) => set('max_prep', Number(e.target.value))} />
      <label htmlFor="f-goal">NUTRITION GOAL</label>
      <select id="f-goal" value={filters.goal || ''} onChange={(e) => set('goal', e.target.value)}>
        <option value="">NONE</option>
        <option value="high_protein">HIGH-PROTEIN (GYM)</option>
        <option value="low_calorie">LOW-CALORIE (DIET)</option>
      </select>
    </div>
  );
}
