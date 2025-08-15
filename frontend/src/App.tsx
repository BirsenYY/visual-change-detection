import React, { useEffect, useMemo, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// A simple rectangle-drawing overlay on the BEFORE image
function RegionSelector({ imageUrl, rects, setRects }: { imageUrl: string | null, rects: any[], setRects: (r: any[]) => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const [drawing, setDrawing] = useState<boolean>(false)
  const [start, setStart] = useState<{x:number,y:number}|null>(null)
  const [current, setCurrent] = useState<{x:number,y:number}|null>(null)

  const getRel = (e: React.MouseEvent) => {
    const el = containerRef.current
    if (!el) return {x:0,y:0}
    const rect = el.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    return { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) }
  }

  const onDown = (e: React.MouseEvent) => { if (!imageUrl) return; setDrawing(true); const p = getRel(e); setStart(p); setCurrent(p); }
  const onMove = (e: React.MouseEvent) => { if (!drawing) return; setCurrent(getRel(e)); }
  const onUp = () => {
    if (drawing && start && current) {
      const x = Math.min(start.x, current.x)
      const y = Math.min(start.y, current.y)
      const w = Math.abs(current.x - start.x)
      const h = Math.abs(current.y - start.y)
      if (w > 0.005 && h > 0.005) setRects([...rects, { x, y, w, h }])
    }
    setDrawing(false); setStart(null); setCurrent(null)
  }

  return (
    <div style={{ position: 'relative', width: '100%', userSelect: 'none' }}>
      <div
        ref={containerRef}
        onMouseDown={onDown}
        onMouseMove={onMove}
        onMouseUp={onUp}
        onMouseLeave={onUp}
        style={{ position: 'relative', width: '100%', aspectRatio: '16/9', background: '#0f1624', borderRadius: 12, border: '1px solid #1f2937' }}>
        {imageUrl && (
          <img ref={imgRef} src={imageUrl} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', borderRadius: 12 }} />
        )}
        {/* existing rects */}
        {rects.map((r, i) => (
          <div key={i} style={{ position: 'absolute', left: `${r.x*100}%`, top: `${r.y*100}%`, width: `${r.w*100}%`, height: `${r.h*100}%`, border: '2px dashed #f59e0b', borderRadius: 8, boxShadow: '0 0 0 99999px rgba(255,165,0,0.05)' }} />
        ))}
        {/* current drag */}
        {drawing && start && current && (
          <div style={{ position: 'absolute', left: `${Math.min(start.x,current.x)*100}%`, top: `${Math.min(start.y,current.y)*100}%`, width: `${Math.abs(current.x-start.x)*100}%`, height: `${Math.abs(current.y-start.y)*100}%`, border: '2px dashed #f59e0b', borderRadius: 8, background: 'rgba(255,165,0,0.1)' }} />
        )}
      </div>
    </div>
  )
}

export default function App() {
  const [before, setBefore] = useState<File | null>(null)
  const [after, setAfter] = useState<File | null>(null)
  const [beforePreview, setBeforePreview] = useState<string | null>(null)
  const [afterPreview, setAfterPreview] = useState<string | null>(null)
  const [rects, setRects] = useState<any[]>([])

  const [sensitivityPct, setSensitivityPct] = useState<number>(10) // 0..100 -> 0..255
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [apiKey, setApiKey] = useState<string>("")
  const [history, setHistory] = useState<any[]>([])

  useEffect(() => {
    const saved = localStorage.getItem('x_api_key')
    if (saved) setApiKey(saved)
  }, [])

  useEffect(() => {
    if (apiKey) localStorage.setItem('x_api_key', apiKey)
  }, [apiKey])

  useEffect(() => {
    if (before) setBeforePreview(URL.createObjectURL(before))
    if (after) setAfterPreview(URL.createObjectURL(after))
  }, [before, after])

  const threshold = useMemo(() => Math.round((sensitivityPct / 100) * 255), [sensitivityPct])

  const headers: Record<string,string> = {}
  if (apiKey) headers['x-api-key'] = apiKey

  // Normalize API error messages to clean text (prefer JSON.detail)
  const extractError = async (res: Response): Promise<string> => {
    try {
      const ct = res.headers.get('content-type') || ''
      if (ct.includes('application/json')) {
        const j = await res.json()
        return (j as any).detail || (j as any).message || `HTTP ${res.status}`
      }
      const t = await res.text()
      try { const j = JSON.parse(t); return (j as any).detail || (j as any).message || t } catch { return t }
    } catch { return `HTTP ${res.status}` }
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!apiKey) { setError('API key is required.'); return }
    if (!before || !after) { setError('Please select both images.'); return }
    setLoading(true)
    try {
      const form = new FormData()
      form.append('before', before)
      form.append('after', after)
      form.append('threshold', String(threshold))
      form.append('ignore_json', JSON.stringify(rects))

      const res = await fetch(`${API_BASE}/comparison`, { method: 'POST', body: form, headers })
      if (!res.ok) {
        const msg = res.status === 401 ? 'Invalid or missing API key' : await extractError(res)
        throw new Error(msg)
      }
      const json = await res.json()
      setResult(json)
      await fetchHistory()
    } catch (err: any) {
      setError(err.message || 'Request failed')
    } finally { setLoading(false) }
  }

  const fetchHistory = async () => {
    if (!apiKey) return
    try {
      const res = await fetch(`${API_BASE}/comparisons?limit=10`, { headers })
      if (!res.ok) {
        if (res.status === 401) setError('Invalid or missing API key')
        return
      }
      const json = await res.json()
      setHistory(json.items || [])
    } catch {}
  }

  useEffect(() => { fetchHistory() }, [apiKey])

  const clearRects = () => setRects([])

  return (
    <div className="container">
      <h1>🔍 Visual Diff</h1>
      <p className="subtle">Upload two screenshots, optionally draw ignore regions on the <b>Before</b> image, and compare.</p>

      <form className="card" onSubmit={onSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <label className="label">API Key (required)</label>
            <input type="password" placeholder="X-API-Key" value={apiKey} onChange={e => setApiKey(e.target.value)} style={{ width: '100%', padding: 8, borderRadius: 8, background: '#0f1624', border: '1px solid #334155', color: 'white' }} />
          </div>
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <div>
            <label className="label">Before image</label>
            <input type="file" accept="image/*" onChange={e => setBefore(e.target.files?.[0] ?? null)} />
            <div style={{ marginTop: 8 }}>
              <RegionSelector imageUrl={beforePreview} rects={rects} setRects={setRects} />
              <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                <button type="button" onClick={clearRects}>Clear regions</button>
              </div>
            </div>
          </div>
          <div>
            <label className="label">After image</label>
            <input type="file" accept="image/*" onChange={e => setAfter(e.target.files?.[0] ?? null)} />
            {afterPreview && (
              <div style={{ marginTop: 8 }}>
                <img src={afterPreview} style={{ width: '100%', borderRadius: 12, border: '1px solid #1f2937' }} />
              </div>
            )}
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <label className="label">Sensitivity: {sensitivityPct}% (threshold {threshold})</label>
          <input className="slider" type="range" min={0} max={100} value={sensitivityPct} onChange={e => setSensitivityPct(Number(e.target.value))} />
        </div>

        <div style={{ marginTop: 16, display: 'flex', gap: 8, alignItems: 'center' }}>
          <button type="submit" disabled={loading || !apiKey}>{loading ? 'Comparing…' : 'Compare'}</button>
          {result?.id && (
            <a className="url" href={`${API_BASE}/comparison/${result.id}`} target="_blank">GET /comparison/{result.id}</a>
          )}
        </div>
      </form>

      {error && <div className="card" style={{ marginTop: 16, borderColor: '#7f1d1d', color: '#fecaca' }}>⚠️ {error}</div>}

      {result && (
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <div className="score">{result.difference_percent?.toFixed?.(2)}%</div>
            <div className="subtle">difference</div>
          </div>
          <div className="img-grid">
            <figure>
              <img src={`${API_BASE}${result.assets.before_url}`} alt="before" />
              <figcaption className="subtle">Before</figcaption>
            </figure>
            <figure>
              <img src={`${API_BASE}${result.assets.after_url}`} alt="after" />
              <figcaption className="subtle">After</figcaption>
            </figure>
            <figure>
              <img src={`${API_BASE}${result.assets.diff_url}`} alt="diff" />
              <figcaption className="subtle">Diff (red = change)</figcaption>
            </figure>
          </div>
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Recent comparisons</h3>
        {!apiKey && <div className="subtle">Enter API key to load history.</div>}
        {apiKey && history.length === 0 && <div className="subtle">No history yet.</div>}
        <div style={{ display: 'grid', gap: 8 }}>
          {history.map(item => (
            <div key={item.id} style={{ display: 'grid', gridTemplateColumns: '120px 1fr auto', gap: 12, alignItems: 'center' }}>
              <img src={`${API_BASE}${item.assets?.diff_url}`} style={{ width: 120, height: 72, objectFit: 'cover', borderRadius: 8, border: '1px solid #1f2937' }} />
              <div>
                <div className="url">{item.id}</div>
                <div className="subtle">{(item.difference_percent ?? 0).toFixed?.(2)}% • thr {item.threshold ?? '—'}</div>
              </div>
              <a className="url" href={`${API_BASE}/comparison/${item.id}`} target="_blank">View JSON</a>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}