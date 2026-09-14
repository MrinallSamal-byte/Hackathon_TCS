import React from 'react';
import { Sparkles, User } from 'lucide-react';

export function MessageBubble({ role, text, time }) {
  const stamp = time || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const isUser = role === 'user';

  return (
    <div className={`msg-row ${role}`}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, maxWidth: '100%', flexDirection: isUser ? 'row-reverse' : 'row' }}>
        <div style={{
          width: 30, height: 30, borderRadius: '50%',
          background: isUser ? 'var(--brand)' : 'var(--brand-soft)',
          color: isUser ? '#FFF' : 'var(--brand)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          boxShadow: '0 4px 12px rgba(255, 107, 87, 0.15)'
        }}>
          {isUser ? <User size={15} /> : <Sparkles size={15} />}
        </div>
        <div className={`bubble ${role}`}>
          <div style={{ whiteSpace: 'pre-wrap' }}>{text}</div>
        </div>
      </div>
      <div className="stamp" style={{ textAlign: isUser ? 'right' : 'left', padding: '4px 38px 0' }}>{stamp}</div>
    </div>
  );
}

export function TypingBubble() {
  return (
    <div className="msg-row bot">
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
        <div style={{
          width: 30, height: 30, borderRadius: '50%',
          background: 'var(--brand-soft)', color: 'var(--brand)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
        }}>
          <Sparkles size={15} />
        </div>
        <div className="bubble bot">
          <span className="typing" aria-label="Assistant is responding">
            <span className="tdot" /><span className="tdot" /><span className="tdot" />
            <span className="micro-label" style={{ marginLeft: 8, color: 'var(--brand)' }}>FINDING CANTEEN MATCHES</span>
          </span>
        </div>
      </div>
    </div>
  );
}

export function ChatWindow({ messages, loading, children }) {
  return (
    <section aria-label="Chat" className="chat-log" aria-live="polite">
      {messages.map((m, i) => (
        <MessageBubble key={m.id ?? `${m.role}-${i}`} role={m.role} text={m.text} time={m.time} />
      ))}
      {loading && <TypingBubble />}
      {children}
    </section>
  );
}

export function QuickChipRow({ chips, onPick }) {
  if (!chips || !chips.length) return null;
  return (
    <div className="chip-row" role="group" aria-label="Quick replies">
      {chips.map((c, i) => (
        <button key={`${c}-${i}`} className="chip" onClick={() => onPick(c)}>{c}</button>
      ))}
    </div>
  );
}
