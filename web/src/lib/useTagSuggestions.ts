import { useQuery } from '@tanstack/react-query'
import { api } from './api'

/** Every tag the user has ever applied to a session, most-used first — powers
 * the quick-complete chips in `TagsEditor`. Empty array while loading. */
export function useTagSuggestions(): string[] {
  const { data } = useQuery({
    queryKey: ['workout-tags'],
    queryFn: api.listWorkoutTags,
    staleTime: 60_000,
  })
  return data ?? []
}
