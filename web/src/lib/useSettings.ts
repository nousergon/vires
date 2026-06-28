import { useQuery } from '@tanstack/react-query'
import { api, type Settings } from './api'

export const DEFAULT_SETTINGS: Settings = {
  weight_unit: 'lb',
  default_rest_seconds: 90,
  default_sets: 3,
  default_reps: 8,
  timer_sound: true,
  timer_vibration: true,
  timer_notification: false,
  timer_keep_awake: true,
}

/** Current user settings, with defaults applied while loading. Never undefined. */
export function useSettings(): Settings {
  const { data } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
    staleTime: 5 * 60_000,
  })
  return data ?? DEFAULT_SETTINGS
}
