import React, { useMemo, useState } from 'react'

type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

type JobInfo = {
  job_id: string
  status: JobStatus
  error?: string | null
  ticker?: string | null
  market_cap_mm?: number | null
  market_cap_meta?: any
}

type ResultPayload = {
  job_id: string
  html: string
  built: any
  ticker?: string | null
  market_cap_mm?: number | null
  market_cap_meta?: any
}

const API_BASE = import.meta.env.VITE_API_BASE || ''

function classNames(...xs: Array<string | false | undefined>) {
  return xs.filter(Boolean).join(' ')
}

export default function App() {
  const [balanceSheet, setBalanceSheet] = useState<File | null>(null)
  const [debtNote, setDebtNote] = useState<File | null>(null)
  const [leaseNote, setLeaseNote] = useState<File | null>(null)
  const [metadata, setMetadata] = useState<File | null>(null)

  // NEW: Ticker for auto-fetch market cap
  const [ticker, setTicker] = useState<string>('')

  // Market cap now optional override
  const [marketCap, setMarketCap] = useState<string>('')

  const [periodEndText, setPeriodEndText] = useState<string>('')

  const [job, setJob] = useState<JobInfo | null>(null)
  const [result, setResult] = useState<ResultPayload | null>(null)
  const [busy, setBusy] = useState(false)

  const missing = useMemo(() => {
    const m: string[] = []
    if (!balanceSheet) m.push('balance_sheet.json')
    if (!debtNote) m.push('debt_note.html')
    if (!leaseNote) m.push('lease_note.html')
    if (!metadata) m.push('metadata.json')

    const hasTicker = !!ticker.trim()
    const hasMarketCap = !!marketCap.trim()

    // Require at least one (ticker OR market cap)
    if (!hasTicker && !hasMarketCap) m.push('ticker OR market cap ($mm)')
    return m
  }, [balanceSheet, debtNote, leaseNote, metadata, ticker, marketCap])

  async function createJob() {
    setBusy(true)
    setResult(null)
    setJob(null)

    try {
      if (missing.length) {
        alert(`Missing: ${missing.join(', ')}`)
        return
      }

      const fd = new FormData()
      fd.append('balance_sheet', balanceSheet!)
      fd.append('debt_note', debtNote!)
      fd.append('lease_note', leaseNote!)
      fd.append('metadata', metadata!)

      // Send ticker if present (lets backend auto-fetch market cap)
      if (ticker.trim()) fd.append('ticker', ticker.trim().toUpperCase())

      // Send market cap ONLY if user provided override
      if (marketCap.trim()) fd.append('market_cap_mm', marketCap.trim())

      if (periodEndText.trim()) fd.append('period_end_text', periodEndText.trim())

      const resp = await fetch(`${API_BASE}/api/jobs`, { method: 'POST', body: fd })
      if (!resp.ok) {
        // backend sometimes returns JSON with {"detail": "..."}; fallback to text
        const errJson = await resp.json().catch(() => null)
        const errText = errJson?.detail ? String(errJson.detail) : await resp.text().catch(() => '')
        throw new Error(errText || `Failed creating job (${resp.status})`)
      }

      const data = await resp.json()
      const jobInfo: JobInfo = { job_id: data.job_id, status: data.status }
      setJob(jobInfo)
      await pollUntilDone(jobInfo.job_id)

    } catch (e: any) {
      alert(e?.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  async function pollUntilDone(jobId: string) {
    while (true) {
      const resp = await fetch(`${API_BASE}/api/jobs/${jobId}`)
      if (!resp.ok) throw new Error(`Failed polling job (${resp.status})`)
      const info = await resp.json()
      setJob(info)

      if (info.status === 'failed') {
        throw new Error(info.error || 'Job failed')
      }
      if (info.status === 'succeeded') {
        const r = await fetch(`${API_BASE}/api/jobs/${jobId}/result`)
        if (!r.ok) {
          const err = await r.json().catch(() => ({}))
          throw new Error(err.detail || `Failed fetching result (${r.status})`)
        }
        const payload = await r.json()
        setResult(payload)
        return
      }

      await new Promise((res) => setTimeout(res, 1200))
    }
  }

  function reset() {
    setJob(null)
    setResult(null)
    setBusy(false)
  }

  const statusBadge = (status?: JobStatus) => {
    if (!status) return null
    const styles: Record<JobStatus, string> = {
      queued: 'bg-gray-100 text-gray-700 border-gray-200',
      running: 'bg-blue-50 text-blue-700 border-blue-200',
      succeeded: 'bg-green-50 text-green-700 border-green-200',
      failed: 'bg-red-50 text-red-700 border-red-200',
    }
    return (
      <span className={classNames('inline-flex items-center rounded-full border px-2 py-1 text-xs font-medium', styles[status])}>
        {status}
      </span>
    )
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: 20 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>Capital Structure Extractor</h1>
          <p style={{ margin: '6px 0 0', color: '#555' }}>
            Upload filing inputs → run pipeline → preview HTML output.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {statusBadge(job?.status)}
          {(job || result) && (
            <button onClick={reset} disabled={busy}
              style={{ padding: '10px 12px', borderRadius: 10, border: '1px solid #ddd', background: 'white', cursor: 'pointer' }}>
              Reset
            </button>
          )}
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 14, marginTop: 16 }}>
        <section style={{ background: 'white', border: '1px solid #e6e6ef', borderRadius: 16, padding: 16 }}>
          <h2 style={{ margin: 0, fontSize: 16 }}>Inputs</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
            <FileField label="Balance Sheet (balance_sheet.json)" accept="application/json" onChange={setBalanceSheet} />
            <FileField label="Metadata (metadata.json)" accept="application/json" onChange={setMetadata} />
            <FileField label="Debt Footnote (debt_note.html)" accept="text/html" onChange={setDebtNote} />
            <FileField label="Lease Footnote (lease_note.html)" accept="text/html" onChange={setLeaseNote} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
            <div>
              <label style={{ fontSize: 13, color: '#444' }}>Ticker (optional, auto-fetch Market Cap)</label>
              <input
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                placeholder='e.g. "AAP"'
                style={inputStyle}
              />
              <div style={{ fontSize: 12, color: '#777', marginTop: 6 }}>
                If Market Cap is blank, backend will fetch it from ticker (bonus points).
              </div>
            </div>

            <div>
              <label style={{ fontSize: 13, color: '#444' }}>Market Cap ($mm) (optional override)</label>
              <input
                value={marketCap}
                onChange={(e) => setMarketCap(e.target.value)}
                placeholder="e.g. 2592"
                inputMode="decimal"
                style={inputStyle}
              />
              <div style={{ fontSize: 12, color: '#777', marginTop: 6 }}>
                If provided, this overrides ticker fetch.
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12, marginTop: 12 }}>
            <div>
              <label style={{ fontSize: 13, color: '#444' }}>Period End Text (optional override)</label>
              <input
                value={periodEndText}
                onChange={(e) => setPeriodEndText(e.target.value)}
                placeholder='e.g. "December 28, 2024"'
                style={inputStyle}
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 14, alignItems: 'center' }}>
            <button
              onClick={createJob}
              disabled={busy || missing.length > 0}
              style={{
                padding: '10px 14px',
                borderRadius: 12,
                border: '1px solid #1b1b1f',
                background: busy || missing.length ? '#ddd' : '#1b1b1f',
                color: busy || missing.length ? '#555' : 'white',
                cursor: busy || missing.length ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
            >
              {busy ? 'Running…' : 'Generate'}
            </button>
            {missing.length > 0 && (
              <span style={{ fontSize: 12, color: '#a33' }}>Missing: {missing.join(', ')}</span>
            )}
          </div>

          {job?.status === 'failed' && (
            <pre style={{ marginTop: 12, padding: 12, background: '#fff5f5', border: '1px solid #ffd6d6', borderRadius: 12, overflow: 'auto' }}>
              {job.error}
            </pre>
          )}
        </section>

        <section style={{ background: 'white', border: '1px solid #e6e6ef', borderRadius: 16, padding: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
            <h2 style={{ margin: 0, fontSize: 16 }}>Output Preview</h2>
            {job?.status === 'succeeded' && job?.job_id && (
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <a
                  href={`${API_BASE}/api/jobs/${job.job_id}/download/html`}
                  style={linkStyle}
                  target="_blank"
                  rel="noreferrer"
                >
                  Download HTML
                </a>
                <a
                  href={`${API_BASE}/api/jobs/${job.job_id}/download/json`}
                  style={linkStyle}
                  target="_blank"
                  rel="noreferrer"
                >
                  Download JSON
                </a>
              </div>
            )}
          </div>

          {!result?.html ? (
            <div style={{ marginTop: 12, padding: 16, borderRadius: 12, border: '1px dashed #ccc', color: '#666' }}>
              When the job finishes, the rendered capital structure HTML will appear here.
            </div>
          ) : (
            <div style={{ marginTop: 12 }}>
              <iframe
                title="Capital Structure Output"
                style={{ width: '100%', height: 720, border: '1px solid #ddd', borderRadius: 12, background: 'white' }}
                srcDoc={result.html}
              />
            </div>
          )}
        </section>
      </div>

      <footer style={{ marginTop: 18, color: '#666', fontSize: 12 }}>
        API: <code>{API_BASE || '(same origin)'}</code>
      </footer>
    </div>
  )
}

function FileField(props: { label: string; accept: string; onChange: (f: File | null) => void }) {
  return (
    <div>
      <label style={{ fontSize: 13, color: '#444' }}>{props.label}</label>
      <input
        type="file"
        accept={props.accept}
        onChange={(e) => props.onChange(e.target.files?.[0] || null)}
        style={{ display: 'block', marginTop: 6 }}
      />
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  marginTop: 6,
  padding: '10px 12px',
  borderRadius: 12,
  border: '1px solid #ddd',
  outline: 'none',
}

const linkStyle: React.CSSProperties = {
  fontSize: 12,
  padding: '8px 10px',
  borderRadius: 10,
  border: '1px solid #ddd',
  textDecoration: 'none',
}