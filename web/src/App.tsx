import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import WorkoutPage from './pages/WorkoutPage'
import TemplatesPage from './pages/TemplatesPage'
import HistoryPage from './pages/HistoryPage'
import ExercisesPage from './pages/ExercisesPage'

const tabs = [
  { to: '/train', label: 'Train', icon: '🏋️' },
  { to: '/routines', label: 'Routines', icon: '📋' },
  { to: '/history', label: 'History', icon: '📈' },
  { to: '/library', label: 'Library', icon: '🔍' },
]

export default function App() {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col">
      <main className="flex-1 overflow-y-auto px-4 pb-24 pt-4 safe-top">
        <Routes>
          <Route path="/" element={<Navigate to="/train" replace />} />
          <Route path="/train" element={<WorkoutPage />} />
          <Route path="/routines" element={<TemplatesPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/library" element={<ExercisesPage />} />
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
