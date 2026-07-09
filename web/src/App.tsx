import { useEffect } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { installOnlineReplay } from './lib/setSync'
import WorkoutPage from './pages/WorkoutPage'
import TemplatesPage from './pages/TemplatesPage'
import PlanPage from './pages/PlanPage'
import HistoryPage from './pages/HistoryPage'
import ExercisesPage from './pages/ExercisesPage'
import SettingsPage from './pages/SettingsPage'

const tabs = [
  { to: '/train', label: 'Train', icon: '🏋️' },
  { to: '/routines', label: 'Routines', icon: '📋' },
  { to: '/plan', label: 'Plan', icon: '📅' },
  { to: '/history', label: 'History', icon: '📈' },
  { to: '/library', label: 'Library', icon: '🔍' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function App() {
  // `registerType: 'autoUpdate'` (vite.config.ts) only auto-reloads on a new
  // deploy if something actually wires the update listener — `immediate`
  // registers on load; the reload itself is silent (no prompt), matching
  // the "auto" in autoUpdate.
  useRegisterSW({ immediate: true })

  // Fallback replay for browsers without the Background Sync API: drain the
  // offline set-log queue whenever the tab regains connectivity (vires-ops#48).
  // Idempotent — safe to call on every mount.
  useEffect(() => {
    installOnlineReplay()
  }, [])

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col">
      <main className="flex-1 overflow-y-auto px-4 pb-24 pt-4 safe-top">
        <Routes>
          <Route path="/" element={<Navigate to="/train" replace />} />
          <Route path="/train" element={<WorkoutPage />} />
          <Route path="/routines" element={<TemplatesPage />} />
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/library" element={<ExercisesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/train" replace />} />
        </Routes>
      </main>

      <nav className="fixed inset-x-0 bottom-0 mx-auto max-w-2xl border-t border-slate-800 bg-slate-900/95 backdrop-blur safe-bottom">
        <div className="flex">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                `flex flex-1 flex-col items-center gap-0.5 py-2.5 text-xs font-medium ${
                  isActive ? 'text-amber-400' : 'text-slate-400'
                }`
              }
            >
              <span className="text-lg leading-none">{t.icon}</span>
              {t.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
