import { useState, useEffect, useCallback } from 'react'
import { QuotaInfo, QuotaBar, QuotaSkeleton } from '../App'

export default function StatsPage() {
  const [quota, setQuota] = useState<QuotaInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchQuota = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await fetch('/api/quota')
      if (res.ok) {
        setQuota(await res.json())
      } else {
        setError(true)
      }
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchQuota() }, [fetchQuota])

  return (
    <div className="page">
      <main className="card">
        <header className="card-header">
          <div className="logo" aria-hidden="true">📊</div>
          <h1 className="card-title">Demo Stats</h1>
          <p className="card-subtitle">Live signup capacity</p>
        </header>

        <div className="stats-body">
          {loading ? (
            <QuotaSkeleton />
          ) : error ? (
            <div className="banner banner--error" role="alert">
              Could not load stats. Check API connectivity.
            </div>
          ) : quota ? (
            <>
              <QuotaBar quota={quota} />

              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-value">{quota.used}</span>
                  <span className="stat-label">Signed up</span>
                </div>
                <div className="stat-item">
                  <span className="stat-value stat-value--available">{quota.available}</span>
                  <span className="stat-label">Available</span>
                </div>
                <div className="stat-item">
                  <span className="stat-value">{quota.quota}</span>
                  <span className="stat-label">Total slots</span>
                </div>
              </div>
            </>
          ) : null}
        </div>

        <div className="stats-footer">
          <button className="btn btn-primary btn-refresh" onClick={fetchQuota} disabled={loading}>
            {loading ? (
              <span className="spinner-wrap"><span className="spinner" aria-hidden="true" /> Refreshing…</span>
            ) : (
              'Refresh'
            )}
          </button>
        </div>
      </main>
    </div>
  )
}
