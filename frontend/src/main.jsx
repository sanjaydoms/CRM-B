import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'
import { LanguageProvider } from './i18n/LanguageContext.jsx'

// Outside LanguageProvider on purpose: if the provider is what threw, a
// boundary inside it goes down with it and the user is back to a white page.
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <LanguageProvider>
        <App />
      </LanguageProvider>
    </ErrorBoundary>
  </StrictMode>,
)

