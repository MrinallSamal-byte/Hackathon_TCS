import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/tokens.css';
import './styles/app.css';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, fontFamily: 'monospace', color: '#B91C1C', background: '#FEF2F2' }}>
          <h2>Application Render Error</h2>
          <pre style={{ whiteSpace: 'pre-wrap', marginTop: 16 }}>{String(this.state.error?.stack || this.state.error)}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

try {
  const root = document.getElementById('root');
  if (root) {
    createRoot(root).render(
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    );
  } else {
    document.body.innerHTML = '<h2 style="color:red">Missing #root in DOM</h2>';
  }
} catch (err) {
  document.body.innerHTML = `<h2 style="color:red">Bootstrap Error: ${err.message}</h2><pre>${err.stack}</pre>`;
}
