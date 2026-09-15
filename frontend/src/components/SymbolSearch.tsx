import { useRef, useState } from 'react'
import type { SearchResult } from '../types'
import { api, ApiError } from '../api'
import { ClassTag } from './Badge'

/**
 * Watchlist search: type a name or ticker ("bitcoin", "reliance", "BTC-USD"), pick a hit,
 * and the backend starts tracking it — validated by actually fetching a bar before it is
 * stored, so an unpriceable symbol is rejected once, loudly, instead of skipped every cycle.
 */
export function SymbolSearch({ onAdded }: { onAdded: (symbol: string) => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [adding, setAdding] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null)

  async function runSearch(nextQuery: string) {
    const trimmed = nextQuery.trim()
    if (trimmed.length < 2) {
      setResults(null)
      setError(null)
      return
    }
    setSearching(true)
    setError(null)
    try {
      setResults(await api.searchSymbols(trimmed, 10))
    } catch (err) {
      setResults(null)
      setError(err instanceof ApiError || err instanceof Error ? err.message : String(err))
    } finally {
      setSearching(false)
    }
  }

  function onInput(value: string) {
    setQuery(value)
    if (debounce.current) clearTimeout(debounce.current)
    debounce.current = setTimeout(() => void runSearch(value), 350)
  }

  async function handleAdd(hit: SearchResult) {
    setAdding(hit.symbol)
    setError(null)
    try {
      await api.addWatchlistEntry(hit.symbol, hit.name, hit.asset_class)
      setResults(
        (prev) =>
          prev?.map((item) =>
            item.symbol === hit.symbol ? { ...item, on_watchlist: true } : item,
          ) ?? null,
      )
      onAdded(hit.symbol)
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : String(err))
    } finally {
      setAdding(null)
    }
  }

  const noResults = !searching && results !== null && results.length === 0 && query.trim().length >= 2

  return (
    <div className="symbol-search">
      <input
        className="search-input"
        type="text"
        value={query}
        onChange={(event) => onInput(event.target.value)}
        placeholder="Search crypto or stocks — bitcoin, reliance, ^NSEI…"
        aria-label="Search symbols to add to the watchlist"
        autoComplete="off"
      />
      {searching && <span className="tiny muted search-status">searching…</span>}
      {error && <span className="tiny warn-text search-status">{error}</span>}
      {noResults && (
        <div className="tiny muted search-status">No tradeable symbols matched “{query.trim()}”.</div>
      )}
      {results && results.length > 0 && (
        <ul className="search-results">
          {results.map((hit) => (
            <li key={hit.symbol} className="search-result">
              <div className="search-result-main">
                <span className="symbol-ticker mono">{hit.symbol}</span>
                <span className="muted">{hit.name}</span>
                <ClassTag value={hit.asset_class} />
                <span className="tiny muted">{hit.exchange}</span>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => void handleAdd(hit)}
                disabled={hit.on_watchlist || adding !== null}
                title={hit.on_watchlist ? 'Already on the watchlist' : 'Track this symbol'}
              >
                {hit.on_watchlist ? 'Tracked' : adding === hit.symbol ? 'Adding…' : 'Add'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
