// Thin client over pipeline-api. Same origin in prod (served at :8000),
// proxied in dev via vite.config.js. Every call fails soft → null.
async function getJSON(path) {
  try {
    const r = await fetch(path)
    if (!r.ok) throw new Error(`${r.status}`)
    return await r.json()
  } catch (e) {
    return null
  }
}
async function postJSON(path, body) {
  try {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    })
    return await r.json()
  } catch (e) {
    return null
  }
}
async function delJSON(path) {
  try {
    const r = await fetch(path, { method: 'DELETE' })
    return await r.json()
  } catch (e) {
    return null
  }
}

export const api = {
  services: () => getJSON('/dash/services'),
  restartService: (name) => postJSON(`/dash/restart/${name}`, {}),
  restartAll: () => postJSON('/dash/restart-all', {}),
  overview: () => getJSON('/dash/overview'),
  table: (name, limit = 25, offset = 0) => getJSON(`/dash/table/${name}?limit=${limit}&offset=${offset}`),
  agents: () => getJSON('/dash/agents'),
  formulaPerformance: () => getJSON('/dash/formula-performance'),
  cost: () => getJSON('/dash/cost'),
  tokenUsage: () => getJSON('/dash/token-usage'),
  analysis: (limit = 25, offset = 0) => getJSON('/dash/analysis?limit=' + limit + '&offset=' + offset),
  clipFinds: (limit = 25, offset = 0) => getJSON('/dash/clip-finds?limit=' + limit + '&offset=' + offset),
  findClips: (youtube_url, max_clips = 8) => postJSON('/clips/find-claude', { youtube_url, max_clips }),
  runs: (limit = 20) => getJSON(`/pipeline/runs?limit=${limit}`),
  run: (id) => getJSON(`/pipeline/run/${id}`),
  artifact: (id) => getJSON(`/pipeline/run/${id}/artifact`),
  artifactDownloadUrl: (id) => `/pipeline/run/${id}/artifact?download=true`,
  discover: (niche, topic = '', top_n = 3) => postJSON('/pipeline/discover', { niche, topic, top_n }),
  research: (youtube_url, topic = '') => postJSON('/pipeline/research', { youtube_url, topic }),

  // Songs — audio extracted from analyzed videos
  getSongs: (limit = 25, offset = 0) => getJSON(`/songs?limit=${limit}&offset=${offset}`),
  getCreators: (limit = 25, offset = 0) => getJSON(`/creators?limit=${limit}&offset=${offset}`),

  // Frames persisted from analysis
  sourceFrames: (youtube_url) => getJSON('/sources/frames?youtube_url=' + encodeURIComponent(youtube_url)),

  // YouTube Data API v3 endpoints
  youtubeSearch: (q, max_results = 20, order = '', videoDuration = '') => {
    const p = new URLSearchParams({ q, max_results })
    if (order) p.set('order', order)
    if (videoDuration) p.set('videoDuration', videoDuration)
    return getJSON(`/youtube/search?${p}`)
  },
  youtubeTrending: (region = 'US', max_results = 20) =>
    getJSON(`/youtube/trending?region=${region}&max_results=${max_results}`),
  youtubeChannelUploads: (channel_id, max_results = 20) =>
    getJSON(`/youtube/channel/${encodeURIComponent(channel_id)}/uploads?max_results=${max_results}`),
  youtubeVideo: (video_id) => getJSON(`/youtube/video/${encodeURIComponent(video_id)}`),
  youtubeQuota: () => getJSON('/youtube/quota'),
  clipThis: (video_id) => postJSON('/youtube/clip-this', { video_id }),

  cookiesStatus: () => getJSON('/cookies'),
  saveCookies: (platform, content) => postJSON('/cookies/' + platform, { content }),
  deleteCookies: (platform) => delJSON('/cookies/' + platform),

  generateScript: (topic, niche = '', top_n = 5) => postJSON('/generate/script', { topic, niche, top_n }),
  discoverCorpus: (niche, count = 5) => postJSON('/discover/corpus', { niche, count }),
  discoverCorpusStatus: (run_id) => getJSON('/discover/corpus/status/' + run_id),
  analyzeClaude: (youtube_url, force = false) => postJSON('/analyze/claude', { youtube_url, force }),

  decompose: (youtube_url) => postJSON('/decompose', { youtube_url }),
  decomposeStatus: (run_id) => getJSON('/decompose/status/' + encodeURIComponent(run_id)),
  sourceSegments: (source_id) => getJSON('/sources/' + source_id + '/segments'),
  sourceAnalysis: (source_id) => getJSON('/sources/' + source_id + '/analysis'),

  chatSessions: () => getJSON('/dash/chat/sessions'),
  chatSession: (sid) => getJSON(`/dash/chat/session/${encodeURIComponent(sid)}`),
  chatSessionDelete: async (sid) => {
    try {
      const r = await fetch(`/dash/chat/session/${encodeURIComponent(sid)}`, { method: 'DELETE' })
      return await r.json()
    } catch (e) {
      return null
    }
  },

  // Stream the agent's reply (SSE) from /dash/chat. Calls onDelta(textChunk)
  // per token, onError(msg) on failure, onDone() at end. Returns an abort fn.
  // When session_key is provided, history is ignored (OpenClaw manages it).
  streamChat(message, history, { onDelta, onError, onDone }, session_key) {
    const ctrl = new AbortController()
    ;(async () => {
      try {
        const body = session_key
          ? { message, session_key }
          : { message, history }
        const r = await fetch('/dash/chat', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(body),
          signal: ctrl.signal
        })
        if (!r.ok || !r.body) {
          onError && onError(`HTTP ${r.status}`)
          return
        }
        const reader = r.body.getReader()
        const dec = new TextDecoder()
        let buf = ''
        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buf += dec.decode(value, { stream: true })
          let nl
          while ((nl = buf.indexOf('\n')) >= 0) {
            const line = buf.slice(0, nl).trim()
            buf = buf.slice(nl + 1)
            if (!line.startsWith('data:')) continue
            const data = line.slice(5).trim()
            if (data === '[DONE]') { onDone && onDone(); return }
            try {
              const j = JSON.parse(data)
              if (j.error) { onError && onError(j.error); return }
              const piece = j.choices?.[0]?.delta?.content
              if (piece) onDelta && onDelta(piece)
            } catch (_) {
              /* ignore non-JSON keepalive lines */
            }
          }
        }
        onDone && onDone()
      } catch (e) {
        if (e.name !== 'AbortError') onError && onError(String(e))
      }
    })()
    return () => ctrl.abort()
  }
}

// Pull the first UUID (a pipeline run_id) out of free-form agent text, if any.
export function extractRunId(text) {
  const m = String(text || '').match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i)
  return m ? m[0] : null
}

// helpers
export function fmtViews(n) {
  n = Number(n) || 0
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.0', '') + ' jt'
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace('.0', '') + ' rb'
  return String(n)
}
