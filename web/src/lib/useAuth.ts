import { useQuery } from '@tanstack/react-query'
import { api } from './api'

/** Current logged-in identity, or `null` once resolved-and-unauthenticated.
 * `isLoading` distinguishes "haven't checked yet" from "checked, logged
 * out" — `RequireAuth` only redirects once loading is false. */
export function useAuth() {
  const { data, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: api.getMe,
    retry: false,
    staleTime: 60_000,
  })
  return { me: data ?? null, isLoading }
}
