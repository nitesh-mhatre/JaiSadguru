import { useCallback, useEffect, useRef, useState } from 'react'

export interface PollingState<T> {
  data: T | null
  error: string | null
  loading: boolean
  refreshing: boolean
  lastUpdated: Date | null
  refresh: () => Promise<void>
}

/**
 * Poll an async source on an interval.
 *
 * On a failed poll the previous data is **kept** rather than cleared. A dashboard that blanks out
 * every time the backend hiccups is less useful than one that shows slightly stale numbers next to
 * a visible error — and hiding the error would be worse than both.
 *
 * The fetcher is held in a ref so callers can pass an inline arrow function without restarting
 * the interval on every render.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number): PollingState<T> {
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const mounted = useRef(true)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    try {
      const result = await fetcherRef.current()
      if (!mounted.current) return
      setData(result)
      setError(null)
      setLastUpdated(new Date())
    } catch (err) {
      if (!mounted.current) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (mounted.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void refresh()
    const timer = window.setInterval(() => {
      void refresh()
    }, intervalMs)
    return () => {
      mounted.current = false
      window.clearInterval(timer)
    }
  }, [refresh, intervalMs])

  return { data, error, loading, refreshing, lastUpdated, refresh }
}
