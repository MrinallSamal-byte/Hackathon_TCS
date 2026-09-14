import React, { useEffect, useState } from 'react';
import { Clock, Flame, Wheat, ThumbsUp, ThumbsDown, ChevronDown, Plus, UtensilsCrossed, Sparkles, Heart, MessageSquare } from 'lucide-react';
import { Badge, DietMarker } from './bits.jsx';
import { api } from '../api.js';
import { num } from './panels.jsx';

function Spice({ level }) {
  return (
    <span className="spice" aria-label={`Spice level ${level} of 3`} title={`Spice level: ${level}/3`}>
      {[0, 1, 2].map((i) => (
        <Flame
          key={i}
          strokeWidth={1.8}
          color={i < level ? '#FF6B57' : 'var(--text-3)'}
          fill={i < level ? '#FF6B57' : 'none'}
          size={16}
        />
      ))}
    </span>
  );
}

export function RecommendationCard({ card, onAdd, onFeedback, onAlternatives, isFavorite, onFavorite }) {
  const [reviews, setReviews] = useState(null);
  const [reviewsError, setReviewsError] = useState(false);
  const [showReviews, setShowReviews] = useState(false);
  const [reviewComment, setReviewComment] = useState('');
  const [reviewVote, setReviewVote] = useState(1);
  const [details, setDetails] = useState(null);
  const openDetails = async () => {
    if (card.is_dynamic || !card.id) return;
    try { setDetails(await api.getItem(card.id)); }
    catch { setDetails({ error: true, name: card.name }); }
  };
  const loadReviews = async () => {
    if (!showReviews && !reviews && !reviewsError && card.id && !card.is_dynamic) {
      try { setReviews(await api.reviews(card.id)); }
      catch { setReviewsError(true); }
    }
    setShowReviews(!showReviews);
  };
  const isTryOrSpecial = Boolean(card.explanation && (
    card.explanation.toLowerCase().includes('give it a try') ||
    card.explanation.toLowerCase().includes('chef') ||
    card.explanation.toLowerCase().includes('bestseller') ||
    card.explanation.toLowerCase().includes('past order') ||
    card.explanation.toLowerCase().includes('favorite')
  ));
  const [open, setOpen] = useState(isTryOrSpecial);
  // Cards are keyed by id in most lists, but identical ids can be reused at
  // the same position across searches — resync disclosure state per dish.
  useEffect(() => { setOpen(isTryOrSpecial); setShowReviews(false); setReviews(null); setReviewsError(false); setReviewComment(''); }, [card.id]); // eslint-disable-line
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
        {isTryOrSpecial && (
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            padding: '3px 9px',
            background: 'var(--brand-soft)',
            color: 'var(--brand)',
            borderRadius: 'var(--r-pill)',
            fontSize: '10.5px',
            fontWeight: 800,
            fontFamily: 'var(--font-data)',
            letterSpacing: '0.04em',
            marginBottom: '8px'
          }}>
            <Sparkles size={12} strokeWidth={2.5} />
            AI PICK · GIVE IT A TRY
          </div>
        )}
        <div className="card-row1">
          <span className="item-name">{card.name}</span>
          <span className="item-price mono">₹{num(card.total_price ?? card.price).toFixed(2)}</span>
        </div>
        <div className="card-row2">
          <DietMarker tags={card.dietary_tags} />
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <Clock size={13} strokeWidth={1.8} /> {(card.eta ?? card.prep_time_minutes)} MIN
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <UtensilsCrossed size={13} strokeWidth={1.8} /> {card.calories ?? ''} {card.calories || card.calories === 0 ? 'KCAL' : (card.portion_size || '').toUpperCase()} · {card.protein_g ?? 0}G PROTEIN{(card.sugar_g ?? 0) > 0 ? ` · ${card.sugar_g}G SUGAR` : ''}
          </span>
          {soldOut && <span className="soldout-tag" style={{ color: 'var(--brand)', border: '1px solid var(--brand)' }}>SOLD OUT</span>}
        </div>
        {(card.likes > 0 || card.dislikes > 0) && (
          <div className="micro-label" style={{ marginTop: 8, display: 'flex', gap: 6, alignItems: 'center', color: 'var(--text-2)' }}>
            <ThumbsUp size={12} strokeWidth={2} color="var(--brand)" /> {card.likes} student{card.likes === 1 ? '' : 's'} recommend{card.dislikes > 0 ? ` · ${card.dislikes} disliked` : ''}
          </div>
        )}
        <div className="card-row3">
          {(card.category === 'combo' || card.is_dynamic) && (
            <span className="badge" style={{ background: 'var(--brand-soft)', color: 'var(--brand)', fontWeight: 800 }}>
              COMBO PACK
            </span>
          )}
          {badges.map((b) => <Badge key={b}>{b}</Badge>)}
          {(card.allergens || []).map((a) => <Badge key={a}>HAS {String(a).toUpperCase()}</Badge>)}
          <Spice level={card.spice_level || 0} />
        </div>
        {card.description && <p style={{ color: 'var(--text-2)', fontSize: 14, margin: '10px 0 0', lineHeight: 1.5 }}>{card.description}</p>}
        {card.cross_contamination_warning && (
          <p style={{ color: 'var(--brand)', fontSize: 12, margin: '8px 0 0', display: 'flex', gap: 6, alignItems: 'center', fontWeight: 600 }}>
            <Wheat size={14} strokeWidth={2} /> {card.cross_contamination_warning}
          </p>
        )}
      </div>
      <div className="card-foot">
        <span style={{ display: 'flex', gap: 4 }}>
          <button className="why-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
            <Sparkles size={14} /> WHY THIS PICK <ChevronDown size={14} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
          </button>
          {!card.is_dynamic && (
            <button className="why-btn" onClick={openDetails} aria-label={`Full details for ${card.name}`}>
              DETAILS
            </button>
          )}
        </span>
        <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {onFavorite && !card.is_dynamic && (
            <button
              className="icon-btn" aria-label={`${isFavorite ? 'Remove' : 'Save'} ${card.name} ${isFavorite ? 'from' : 'to'} favorites`}
              onClick={() => onFavorite(card)} title={isFavorite ? 'Saved to favorites' : 'Save to favorites'}
              style={isFavorite ? { color: 'var(--brand)' } : undefined}
            >
              <Heart size={16} strokeWidth={1.8} fill={isFavorite ? 'currentColor' : 'none'} />
            </button>
          )}
          <button className="icon-btn" aria-label={`Like ${card.name}`} onClick={() => onFeedback && onFeedback(card, 1)} title="Thumbs Up">
            <ThumbsUp size={16} strokeWidth={1.8} />
          </button>
          <button className="icon-btn" aria-label={`Dislike ${card.name}`} onClick={() => onFeedback && onFeedback(card, -1)} title="Thumbs Down">
            <ThumbsDown size={16} strokeWidth={1.8} />
          </button>
          {soldOut ? (
            <button className="btn btn-danger" onClick={() => onAlternatives && onAlternatives(card)}>SEE ALTERNATIVES</button>
          ) : (
            <button className="btn-add" onClick={() => onAdd && onAdd(card)} aria-label={`Add ${card.name} to tray`}>
              + ADD
            </button>
          )}
        </span>
      </div>
      {open && card.explanation && <p className="why-text">{card.explanation}</p>}
      {!card.is_dynamic && (
        <div style={{ padding: '0 16px 12px' }}>
          <button className="why-btn" onClick={loadReviews} aria-expanded={showReviews} style={{ fontSize: 12 }}>
            <MessageSquare size={13} /> {showReviews ? 'HIDE REVIEWS' : `REVIEWS${reviews ? ` (${reviews.review_count})` : ''}`}
          </button>
          {showReviews && (
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {reviewsError && (
                <div style={{ fontSize: 12.5, color: 'var(--red-text)' }}>Could not load reviews — check connection and retry.</div>
              )}
              {!reviewsError && (reviews && reviews.comments && reviews.comments.length > 0 ? reviews.comments.slice(0, 3).map((r, i) => (
                <div key={`${r.at || 'norev'}-${i}`} style={{ fontSize: 12.5, color: 'var(--text-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '6px 10px' }}>
                  {r.rating > 0 ? '👍 ' : r.rating < 0 ? '👎 ' : ''}{r.comment}
                </div>
              )) : (
                <div style={{ fontSize: 12.5, color: 'var(--text-3)' }}>No written reviews yet — be the first with a comment below.</div>
              ))}
              <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <button
                  type="button" className="icon-btn" aria-label="Review as liked" title="Review as liked"
                  aria-pressed={reviewVote > 0} onClick={() => setReviewVote(1)}
                  style={reviewVote > 0 ? { color: 'var(--brand)' } : undefined}
                >
                  <ThumbsUp size={14} strokeWidth={1.8} />
                </button>
                <button
                  type="button" className="icon-btn" aria-label="Review as disliked" title="Review as disliked"
                  aria-pressed={reviewVote < 0} onClick={() => setReviewVote(-1)}
                  style={reviewVote < 0 ? { color: 'var(--brand)' } : undefined}
                >
                  <ThumbsDown size={14} strokeWidth={1.8} />
                </button>
                <input
                  aria-label={`Write a review for ${card.name}`}
                  placeholder="Add a quick review..."
                  value={reviewComment}
                  onChange={(e) => setReviewComment(e.target.value)}
                  style={{ flex: 1, background: 'var(--surface-2)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '8px 10px', color: 'var(--text-1)', fontSize: 12.5 }}
                />
                <button
                  className="btn btn-secondary" style={{ padding: '8px 12px', fontSize: 12 }}
                  onClick={() => { if (reviewComment.trim() && onFeedback) { onFeedback(card, reviewVote, reviewComment.trim()); setReviewComment(''); setReviews(null); setReviewsError(false); } }}
                >
                  Post
                </button>
              </span>
            </div>
          )}
        </div>
      )}
      {details && (
        <div
          role="dialog" aria-modal="true" aria-label={`${details.name || card.name} details`}
          onClick={(e) => { if (e.target === e.currentTarget) setDetails(null); }}
          style={{
            position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
          }}
        >
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 20,
            padding: 24, maxWidth: 440, width: '100%', maxHeight: '80vh', overflowY: 'auto',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <strong style={{ fontSize: 18 }}>{details.name || card.name}</strong>
              <button type="button" className="icon-btn" aria-label="Close details" onClick={() => setDetails(null)}>✕</button>
            </div>
            {details.error ? (
              <p style={{ color: 'var(--text-2)', fontSize: 14 }}>Could not load details — check connection.</p>
            ) : (
              <>
                <p style={{ color: 'var(--text-2)', fontSize: 13.5, lineHeight: 1.55 }}>{details.description}</p>
                <div className="micro-label mono" style={{ margin: '10px 0 4px' }}>
                  ₹{num(details.price).toFixed(0)} · {details.prep_time_minutes} MIN · {details.calories} KCAL · {details.protein_g ?? 0}G PROTEIN · {details.carbs_g ?? 0}G CARBS · {details.sugar_g ?? 0}G SUGAR · {details.fiber_g ?? 0}G FIBER · SPICE {details.spice_level}/3
                </div>
                {(details.ingredients || []).length > 0 && (
                  <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 6 }}>
                    <span className="micro-label">INGREDIENTS — </span>{details.ingredients.join(', ')}
                  </div>
                )}
                {(details.allergens || []).length > 0 && (
                  <div style={{ fontSize: 13, color: 'var(--brand)', marginTop: 6, fontWeight: 700 }}>
                    CONTAINS: {details.allergens.join(', ').toUpperCase()}
                  </div>
                )}
                <div style={{ fontSize: 12.5, color: 'var(--text-2)', marginTop: 6 }}>
                  {(details.dietary_tags || []).join(' · ').toUpperCase() || 'NO DIET TAGS'}
                  {(details.likes > 0 || details.dislikes > 0) && ` · ${details.likes} LIKED / ${details.dislikes} PASSED`}
                </div>
                {details.sold_out_note && (
                  <p style={{ color: 'var(--brand)', fontSize: 13, fontWeight: 700 }}>{details.sold_out_note}</p>
                )}
                {(details.alternatives || []).length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <div className="micro-label">CLOSEST ALTERNATIVES</div>
                    {details.alternatives.map((a) => (
                      <div key={a.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--hairline)', fontSize: 13 }}>
                        <span>{a.name} · ₹{num(a.price).toFixed(0)}</span>
                        <button className="btn-add" onClick={() => { onAdd && onAdd(a); setDetails(null); }}>+ ADD</button>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
