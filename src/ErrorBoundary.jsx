import { Component } from 'react';

/**
 * Last-resort UI guard. If a render throws, show a minimal panel that lets
 * the user keep using the rest of the app instead of seeing a blank screen.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info?.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{
        padding: '2rem',
        fontFamily: 'ui-monospace, monospace',
        background: 'var(--bg, #0c0e12)',
        color: 'var(--txt, #e6edf3)',
        minHeight: '100vh',
      }}>
        <h2 style={{ fontSize: '1rem', marginBottom: '.5rem' }}>Something went wrong rendering this page.</h2>
        <pre style={{ fontSize: '.78rem', whiteSpace: 'pre-wrap', opacity: .8 }}>{String(this.state.error)}</pre>
        <button
          onClick={this.reset}
          style={{
            marginTop: '1rem',
            padding: '.4rem .8rem',
            border: '1px solid var(--bord, #4a4f57)',
            background: 'transparent',
            color: 'inherit',
            cursor: 'pointer',
            font: 'inherit',
          }}
        >Retry</button>
      </div>
    );
  }
}
