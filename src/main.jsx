import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'

createRoot(document.getElementById('root')).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
)

// Tell index.html the app shell has painted so the neural-bg gate can
// release (Track C: kill pre-mount flash).
requestAnimationFrame(() => {
  window.dispatchEvent(new CustomEvent('claude-tracker:app-ready'))
})
