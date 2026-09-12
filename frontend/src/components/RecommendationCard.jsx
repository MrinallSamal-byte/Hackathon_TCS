import React, { useState } from 'react';
import { Clock, Flame, Wheat, ThumbsUp, ThumbsDown, ChevronDown, Plus, UtensilsCrossed } from 'lucide-react';
import { Badge, DietMarker } from './bits.jsx';

function Spice({ level }) {
  return (
    <span className="spice" aria-label={`Spice level ${level} of 3`}>
      {[0, 1, 2].map((i) => (
        <Flame
          key={i}
          strokeWidth={1.5}
          color={i < level ? '#FFFFFF' : '#4E4E4E'}
          fill={i < level ? '#FFFFFF' : 'none'}
          size={16}
        />
      ))}
    </span>
  );
}

export function RecommendationCard({ card, onAdd, onFeedback, onAlternatives }) {
  const [open, setOpen] = useState(false);
  const soldOut = card.availability === false;
  const badges = [];
  const tags = new Set(card.dietary_tags || []);
  if (tags.has('vegan')) badges.push('VEGAN');
  if (tags.has('jain')) badges.push('JAIN');
  if (tags.has('gluten_free')) badges.push('GF');
  if (tags.has('dairy_free')) badges.push('DAIRY-FREE');
  if (tags.has('halal') && tags.has('non_veg')) badges.push('HALAL');

  return (
    <article className={`rec-card${soldOut ? ' soldout' : ''}`} aria-label={card.name}>
      <div className="card-body">
        <div className="card-row1">
          <span className="item-name">{card.name}</span>
          <span className="item-price mono">₹{Number(card.total_price ?? card.price).toFixed(2)}</span>
        </div>
        <div className="card-row2">
          <DietMarker tags={card.dietary_tags} />
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <Clock size={14} strokeWidth={1.5} /> {(card.eta ?? card.prep_time_minutes)} MIN
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <UtensilsCrossed size={14} strokeWidth={1.5} /> {card.calories ?? ''} {card.calories || card.calories === 0 ? 'KCAL' : (card.portion_size || '').toUpperCase()} · {card.protein_g ?? 0}G PROTEIN
          </span>
          {soldOut && <span className="soldout-tag">SOLD OUT</span>}
        </div>
        {(card.likes > 0 || card.dislikes > 0) && (
          <div className="micro-label" style={{ marginTop: 6, display: 'flex', gap: 4, alignItems: 'center' }}>
            <ThumbsUp size={12} strokeWidth={1.5} /> {card.likes} LIKED BY STUDENTS{card.dislikes > 0 ? ` · ${card.dislikes} PASSED` : ''}
          </div>
        )}
        <div className="card-row3">
          {(card.category === 'combo' || card.is_dynamic) && <Badge>COMBO</Badge>}
          {badges.map((b) => <Badge key={b}>{b}</Badge>)}
          {(card.allergens || []).map((a) => <Badge key={a}>HAS {String(a).toUpperCase()}</Badge>)}
          <Spice level={card.spice_level || 0} />
        </div>
        {card.description && <p style={{ color: 'var(--text-2)', fontSize: 14, margin: '8px 0 0' }}>{card.description}</p>}
        {card.cross_contamination_warning && (
          <p style={{ color: 'var(--text-2)', fontSize: 13, margin: '8px 0 0', display: 'flex', gap: 6, alignItems: 'center' }}>
            <Wheat size={16} strokeWidth={1.5} /> {card.cross_contamination_warning}
          </p>
        )}
      </div>
      <div className="card-foot">
        <button className="why-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
          WHY THIS <ChevronDown size={16} strokeWidth={1.5} />
        </button>
        <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="icon-btn" aria-label={`Like ${card.name}`} onClick={() => onFeedback && onFeedback(card, 1)}>
            <ThumbsUp size={18} strokeWidth={1.5} />
          </button>
          <button className="icon-btn" aria-label={`Dislike ${card.name}`} onClick={() => onFeedback && onFeedback(card, -1)}>
            <ThumbsDown size={18} strokeWidth={1.5} />
          </button>
          {soldOut ? (
            <button className="btn btn-danger" onClick={() => onAlternatives && onAlternatives(card)}>SEE ALTERNATIVES</button>
          ) : (
            <button className="btn-add" onClick={() => onAdd && onAdd(card)} aria-label={`Add ${card.name} to tray`}>
              ADD <Plus size={16} strokeWidth={1.5} style={{ verticalAlign: -3 }} />
            </button>
          )}
        </span>
      </div>
      {open && card.explanation && <p className="why-text">{card.explanation}</p>}
    </article>
  );
}
