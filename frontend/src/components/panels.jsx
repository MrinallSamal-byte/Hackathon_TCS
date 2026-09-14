import React, { useState } from 'react';
import { ShoppingBag, Clock, Trash2, CheckCircle2, AlertTriangle, SlidersHorizontal, ChevronDown, Sparkles, Plus } from 'lucide-react';

// Finite-number price: a missing/NaN price must never poison tray totals.
export const num = (v, fb = 0) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fb;
};

export function BudgetMeter({ spent, budget }) {
  const b = Number(budget || 0);
  const s = Number(spent || 0);
  const pct = b > 0 ? Math.min(100, (s / b) * 100) : 0;
  const over = b > 0 && s > b;
  const remaining = b > s ? (b - s) : 0;

  return (
    <div className={`budget-wrap${over ? ' over' : ''}`} role="status" aria-label="Budget meter">
      <div className="budget-label mono">
        <span>
          {b > 0
            ? (over ? `OVER BUDGET +₹${(s - b).toFixed(0)}` : `TRAY ₹${s.toFixed(0)} / BUDGET ₹${b.toFixed(0)}`)
            : `TRAY TOTAL: ₹${s.toFixed(0)}`}
        </span>
        {b > 0 && (
          <span style={{ color: over ? 'var(--red)' : '#10B981', fontWeight: 800 }}>
            {over ? 'LIMIT EXCEEDED' : `₹${remaining.toFixed(0)} LEFT`}
          </span>
        )}
      </div>
      {b > 0 && (
        <div className="budget-track">
          <div className="budget-fill" style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}

export function TrayPanel({ tray, budget, eta, overBy, onRemove, onClear, onOrder, onCompleteMeal,
  coupon, onCoupon, discount, payable, couponError, split, onSplit }) {
  const total = tray.reduce((a, t) => a + num(t.price ?? t.total_price), 0);
  const shownTotal = num(payable ?? total);
  const over = num(overBy) > 0;

  return (
    <div className="tray" aria-label="Your tray">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 16 }}>
          <ShoppingBag size={18} color="var(--brand)" /> YOUR TRAY
        </div>
        {tray.length > 0 && (
          <span style={{ background: 'var(--brand-soft)', color: 'var(--brand)', padding: '2px 8px', borderRadius: 9999, fontSize: 11, fontWeight: 800 }}>
            {tray.length} {tray.length === 1 ? 'ITEM' : 'ITEMS'}
          </span>
        )}
      </div>

      <BudgetMeter spent={total} budget={budget || 0} />

      {tray.length === 0 && (
        <div style={{ textAlign: 'center', padding: '20px 12px', color: 'var(--text-2)', fontSize: 13 }}>
          <ShoppingBag size={28} color="var(--text-3)" style={{ margin: '0 auto 8px', opacity: 0.4 }} />
          <p style={{ margin: 0, fontWeight: 600 }}>Tray is empty.</p>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Tap "+ ADD" on any dish to build your tray.</span>
        </div>
      )}

      {tray.map((t) => (
        <div className="tray-row" key={t.key}>
          <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
            <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name}</span>
          </div>
          <span className="tray-price mono" style={{ margin: '0 8px' }}>₹{num(t.price ?? t.total_price).toFixed(2)}</span>
          <button
            className="icon-btn"
            style={{ width: 28, height: 28, minHeight: 28, background: 'transparent' }}
            aria-label={`Remove ${t.name}`}
            onClick={() => onRemove(t.key)}
            title="Remove item"
          >
            <Trash2 size={14} color="var(--text-3)" />
          </button>
        </div>
      ))}

      {tray.length > 0 && (
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--hairline)' }}>
          <div className="tray-total mono" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 16, fontWeight: 800 }}>
            <span>TOTAL</span>
            <span style={{ color: 'var(--brand)' }}>₹{shownTotal.toFixed(2)}</span>
          </div>
          {discount > 0 && (
            <div className="mono" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#10B981', marginTop: 4 }}>
              <span>COUPON {coupon} SAVINGS</span>
              <span>−₹{Number(discount).toFixed(2)}</span>
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-2)', marginTop: 8 }}>
            <Clock size={14} color="#10B981" />
            <span>Ready in ~<strong>{eta || 0} mins</strong> (Parallel Prep)</span>
          </div>

          {over && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--red-text)', marginTop: 6, fontWeight: 700 }}>
              <AlertTriangle size={14} /> Exceeds budget limit by ₹{num(overBy).toFixed(0)}
            </div>
          )}

          {onCoupon && (
            <div style={{ marginTop: 12 }}>
              <label className="micro-label" htmlFor="tray-coupon">COUPON CODE (STUDENT10 · FESTIVE15 · FIRSTORDER)</label>
              <span style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                <input
                  id="tray-coupon" placeholder="e.g. STUDENT10"
                  value={coupon || ''} onChange={(e) => onCoupon(e.target.value.toUpperCase())}
                  style={{ flex: 1, background: 'var(--surface-2)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '8px 10px', color: 'var(--text-1)', fontSize: 12.5, fontFamily: 'var(--font-data)' }}
                />
                {coupon && (
                  <button className="btn btn-secondary" style={{ padding: '8px 10px', fontSize: 12 }} onClick={() => onCoupon('')}>Clear</button>
                )}
              </span>
              {couponError && <div style={{ fontSize: 12, color: 'var(--red-text)', marginTop: 4 }}>{couponError}</div>}
            </div>
          )}

          {onSplit && (
            <div style={{ marginTop: 10, background: 'var(--surface-2)', border: '1px solid var(--hairline)', borderRadius: 12, padding: '10px 12px' }}>
              <div className="micro-label">SPLIT BILL {split && split.people ? `· ${split.people} PEOPLE → ₹${Number(split.per_person).toFixed(2)} EACH` : ''}</div>
              <span style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                {[2, 3, 4].map((n) => (
                  <button key={n} className="btn btn-secondary" style={{ flex: 1, padding: '6px 8px', fontSize: 12 }} onClick={() => onSplit(n)}>{n} ways</button>
                ))}
                <button className="btn btn-secondary" style={{ flex: 1, padding: '6px 8px', fontSize: 12 }} onClick={() => onSplit(1)}>Full</button>
              </span>
            </div>
          )}

          {onCompleteMeal && (
            <button
              className="btn btn-secondary"
              style={{ width: '100%', marginTop: 12, padding: '8px 12px', fontSize: 13, gap: 6 }}
              onClick={onCompleteMeal}
            >
              <Sparkles size={14} color="var(--brand)" /> Complete Meal (Auto-Fill Sides)
            </button>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn btn-secondary" style={{ flex: 1, padding: '8px 12px', fontSize: 13 }} onClick={onClear}>
              Clear Tray
            </button>
            <button className="btn btn-primary" style={{ flex: 2, padding: '8px 14px', fontSize: 13 }} onClick={onOrder}>
              <CheckCircle2 size={15} /> Confirm Order
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function FilterDrawer({ filters, onChange, onApply, collapsible = false, defaultExpanded = true }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const set = (k, v) => onChange({ ...filters, [k]: v });

  return (
    <div className="drawer" aria-label="Filters">
      <button
        type="button"
        aria-expanded={collapsible ? expanded : undefined}
        onClick={() => collapsible && setExpanded(!expanded)}
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%',
          background: 'none', border: 'none', padding: 0, color: 'inherit',
          cursor: collapsible ? 'pointer' : 'default', marginBottom: expanded ? 14 : 0
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 15 }}>
          <SlidersHorizontal size={16} color="var(--brand)" /> KITCHEN FILTERS
        </div>
        {collapsible && (
          <ChevronDown
            size={18}
            style={{
              transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
              transition: 'transform 0.2s ease', color: 'var(--text-2)'
            }}
          />
        )}
      </button>

      {expanded && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <label htmlFor="f-cat">CATEGORY</label>
            <select id="f-cat" value={filters.category || ''} onChange={(e) => set('category', e.target.value)}>
              <option value="">ALL CATEGORIES</option>
              <option value="breakfast">BREAKFAST</option>
              <option value="main_course">MAIN COURSE</option>
              <option value="snack">SNACK</option>
              <option value="beverage">BEVERAGE</option>
              <option value="dessert">DESSERT</option>
              <option value="combo">COMBO</option>
            </select>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <label htmlFor="f-price" style={{ margin: 0 }}>MAX PRICE</label>
              <span className="mono" style={{ fontSize: 13, fontWeight: 800, color: 'var(--brand)' }}>₹{filters.max_price || 250}</span>
            </div>
            <input id="f-price" type="range" min="15" max="250" value={filters.max_price || 250} onChange={(e) => set('max_price', Number(e.target.value))} />
          </div>

          <div>
            <label htmlFor="f-diet">DIETARY SAFETY</label>
            <select id="f-diet" value={filters.dietary || ''} onChange={(e) => set('dietary', e.target.value)}>
              <option value="">ANY DIET</option>
              <option value="veg">VEGETARIAN</option>
              <option value="vegan">VEGAN</option>
              <option value="jain">JAIN (NO ONION/GARLIC)</option>
              <option value="gluten_free">GLUTEN-FREE</option>
              <option value="halal">HALAL NON-VEG</option>
            </select>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <label htmlFor="f-spice" style={{ margin: 0 }}>SPICE TOLERANCE</label>
              <span className="mono" style={{ fontSize: 12, fontWeight: 700 }}>LEVEL {filters.max_spice ?? 3} OF 3</span>
            </div>
            <input id="f-spice" type="range" min="0" max="3" value={filters.max_spice ?? 3} onChange={(e) => set('max_spice', Number(e.target.value))} />
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <label htmlFor="f-prep" style={{ margin: 0 }}>MAX PREP TIME</label>
              <span className="mono" style={{ fontSize: 12, fontWeight: 700 }}>{filters.max_prep || 25} MINS</span>
            </div>
            <input id="f-prep" type="range" min="2" max="25" value={filters.max_prep || 25} onChange={(e) => set('max_prep', Number(e.target.value))} />
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <label htmlFor="f-cal" style={{ margin: 0 }}>MAX CALORIES</label>
              <span className="mono" style={{ fontSize: 12, fontWeight: 700 }}>{filters.max_cal || 1050} KCAL</span>
            </div>
            <input id="f-cal" type="range" min="50" max="1050" step="10" value={filters.max_cal || 1050} onChange={(e) => set('max_cal', Number(e.target.value))} />
          </div>

          <div>
            <label htmlFor="f-goal">NUTRITION & FITNESS GOAL</label>
            <select id="f-goal" value={filters.goal || ''} onChange={(e) => set('goal', e.target.value)}>
              <option value="">NO GOAL</option>
              <option value="high_protein">💪 HIGH-PROTEIN (GYM POST-WORKOUT)</option>
              <option value="low_calorie">🥗 LOW-CALORIE (LIGHT STUDY SNACK)</option>
              <option value="diabetic">LOWER-SUGAR (DIABETIC-FRIENDLY PICKS)</option>
            </select>
          </div>

          {onApply && (
            <button
              className="btn btn-primary"
              style={{ width: '100%', marginTop: 6, padding: '10px 14px', fontSize: 13, gap: 6 }}
              onClick={onApply}
            >
              <SlidersHorizontal size={14} /> Apply Kitchen Filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}
