import React from 'react';

export function MessageBubble({ role, text, time }) {
  const stamp = time || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return (
    <div className={`msg-row ${role}`}>
      <div className={`bubble ${role}`}>
        <div style={{ whiteSpace: 'pre-wrap' }}>{text}</div>
      </div>
      <div className="stamp">{stamp}</div>
    </div>
  );
}

export function TypingBubble() {
  return (
    <div className="msg-row bot">
      <div className="bubble bot">
        <span className="typing" aria-label="Assistant is responding">
          <span className="tdot" /><span className="tdot" /><span className="tdot" />
          <span className="micro-label" style={{ marginLeft: 8 }}>RECOMMENDING</span>
        </span>
      </div>
    </div>
  );
}

export function ChatWindow({ messages, loading, children }) {
  return (
    <section aria-label="Chat" className="chat-log" aria-live="polite">
      {messages.map((m, i) => (
        <MessageBubble key={i} role={m.role} text={m.text} time={m.time} />
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
      {chips.map((c) => (
        <button key={c} className="chip" onClick={() => onPick(c)}>{c}</button>
      ))}
    </div>
  );
}
