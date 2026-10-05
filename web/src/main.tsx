import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'
import { canonicalRedirect } from './lib/canonicalHost'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
})

const redirectTo = canonicalRedirect(window.location)
if (redirectTo) window.location.replace(redirectTo)
else createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* The app is canonically served under /app (vires-ops#61). basename on
          the router — NOT Vite `base` — so the PWA service worker keeps its
          existing `/` scope (already-installed PWAs don't migrate scopes). */}
      <BrowserRouter basename="/app">
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
