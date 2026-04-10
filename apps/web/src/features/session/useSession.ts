import { useQuery } from '@tanstack/react-query'
import { fetchSession, SessionFetchError } from './api'

export function useSession(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => fetchSession(sessionId!),
    enabled: Boolean(sessionId),
    staleTime: 60_000, // the diff rarely changes mid-session
    retry: (failureCount, error) => {
      // Do NOT retry 4xx — auth/missing-resource errors will not recover on retry.
      if (error instanceof SessionFetchError && error.status >= 400 && error.status < 500) {
        return false
      }
      return failureCount < 2
    },
  })
}
