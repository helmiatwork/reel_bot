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
async function patchJSON(path, body) {
  try {
    const r = await fetch(path, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    })
    if (!r.ok) throw new Error(`${r.status}`)
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

  // Songs — audio extracted from analyzed videos + user imports
  getSongs: (limit = 25, offset = 0, tag = '', mood = '') => {
    const p = new URLSearchParams({ limit, offset })
    if (tag) p.set('tag', tag)
    if (mood) p.set('mood', mood)
    return getJSON(`/songs?${p}`)
  },
  songImport: async (file, { title = '', tags = [], mood = '', genre = '' } = {}) => {
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('title', title)
      fd.append('tags', JSON.stringify(tags))
      fd.append('mood', mood)
      fd.append('genre', genre)
      const r = await fetch('/songs/import', { method: 'POST', body: fd })
      return await r.json()
    } catch (e) {
      return null
    }
  },
  songUpdate: (id, body) => patchJSON(`/songs/${id}`, body),
  getCreators: (limit = 25, offset = 0) => getJSON(`/creators?limit=${limit}&offset=${offset}`),

  // Frames persisted from analysis
  sourceFrames: (youtube_url) => getJSON('/sources/frames?youtube_url=' + encodeURIComponent(youtube_url)),

  // Upload source video file
  uploadSource: async (file, { intent = '', output_format = 'none' } = {}) => {
    try {
      const fd = new FormData()
      fd.append('file', file)
      if (intent) fd.append('intent', intent)
      if (output_format) fd.append('output_format', output_format)
      const r = await fetch('/sources/upload', { method: 'POST', body: fd })
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data.detail || ('HTTP ' + r.status))
      return data
    } catch (e) {
      throw e
    }
  },

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

  // Brands (product grouping)
  brands: () => getJSON('/brands'),
  brand: (id) => getJSON(`/brands/${id}`),
  brandCreate: (body) => postJSON('/brands', body),  // pass { name, description? }
  brandUpdate: (id, body) => patchJSON(`/brands/${id}`, body),
  brandDelete: (id) => delJSON(`/brands/${id}`),

  // Accounts
  accounts: (platform, role, brandId) => {
    const q = [platform && `platform=${platform}`, role && `role=${role}`, brandId && `brand_id=${brandId}`].filter(Boolean).join('&')
    return getJSON('/accounts' + (q ? '?' + q : ''))
  },
  accountCreate: (body) => postJSON('/accounts', body),   // pass { role: 'scrape'|'publish', brand_id? } in body
  accountUpdate: (id, body) => patchJSON(`/accounts/${id}`, body),  // pass { role, brand_id } to change
  accountDelete: (id) => delJSON(`/accounts/${id}`),
  accountSaveCookies: (id, content) => postJSON(`/accounts/${id}/cookies`, { content }),
  accountDeleteCookies: (id) => delJSON(`/accounts/${id}/cookies`),
  accountConnectYoutube: (id) => postJSON(`/accounts/${id}/connect-youtube`, {}),

  generateScript: (topic, niche = '', top_n = 5) => postJSON('/generate/script', { topic, niche, top_n }),
  discoverCorpus: (niche, count = 5) => postJSON('/discover/corpus', { niche, count }),
  discoverCorpusStatus: (run_id) => getJSON('/discover/corpus/status/' + run_id),
  analyzeClaude: (youtube_url, { intent = '', force = false, output_format = 'none' } = {}) => postJSON('/analyze/claude', { youtube_url, intent, force, output_format }),
  analyzeClaudeAsync: (youtube_url, { intent = '', force = false, output_format = 'none', stages = 'full', include_audio = false, audio_start, audio_end } = {}) => {
    const body = { youtube_url, intent, force, output_format, stages, include_audio }
    if (audio_start !== undefined && audio_start !== null) body.audio_start = audio_start
    if (audio_end !== undefined && audio_end !== null) body.audio_end = audio_end
    return postJSON('/analyze/claude/async', body)
  },
  analyzeClaudeStatus: (run_id) => getJSON('/analyze/claude/status/' + run_id),
  analyzeRuns: (limit = 20) => getJSON('/analyze/claude/runs?limit=' + limit),
  uploadSourceAsync: async (file, { intent = '', output_format = 'none', include_audio = false, audio_start, audio_end } = {}) => {
    try {
      const fd = new FormData()
      fd.append('file', file)
      if (intent) fd.append('intent', intent)
      if (output_format) fd.append('output_format', output_format)
      fd.append('include_audio', include_audio ? 'true' : 'false')
      if (audio_start !== undefined && audio_start !== null) fd.append('audio_start', String(audio_start))
      if (audio_end !== undefined && audio_end !== null) fd.append('audio_end', String(audio_end))
      const r = await fetch('/sources/upload/async', { method: 'POST', body: fd })
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data.detail || ('HTTP ' + r.status))
      return data
    } catch (e) {
      throw e
    }
  },

  // Scheduled posts
  scheduleList: () => getJSON('/schedule'),
  scheduleCreate: (data) => postJSON('/schedule', data),
  scheduleUpdate: (id, data) => patchJSON(`/schedule/${id}`, data),
  scheduleDelete: (id) => delJSON(`/schedule/${id}`),
  scheduleCorpus: () => getJSON('/schedule/corpus'),

  // Performance tracking — own posted videos
  performance: () => getJSON('/performance'),
  performanceRefresh: () => postJSON('/performance/refresh', {}),

  // Revenue + RPM tracking (manual entry per posted video)
  revenueList: (params = {}) => {
    const p = new URLSearchParams()
    if (params.platform) p.set('platform', params.platform)
    if (params.start) p.set('start', params.start)
    if (params.end) p.set('end', params.end)
    const qs = p.toString()
    return getJSON('/revenue' + (qs ? '?' + qs : ''))
  },
  revenueSummary: () => getJSON('/revenue/summary'),
  revenueCreate: (payload) => postJSON('/revenue', payload),
  revenueUpdate: (id, payload) => patchJSON(`/revenue/${id}`, payload),
  revenueDelete: (id) => delJSON(`/revenue/${id}`),

  seoAnalyze: (topic, platform = 'youtube', niche = '') => postJSON('/seo/analyze', { topic, platform, niche }),

  // Prep Bundle — aggregate assets for CapCut finishing
  prepList: () => getJSON('/prep/list'),
  prepGet: (id) => getJSON('/prep/' + id),
  prepSetBgm: (id, bgm_song_id) => patchJSON('/prep/' + id, { bgm_song_id }),
  prepRoughcut: (id) => postJSON('/prep/' + id + '/roughcut', {}),
  prepZipUrl: (id) => '/prep/' + id + '/zip',

  // Studio — batch generation + Kanban board
  generateBatch: (niche, topic, count) => postJSON('/generate/batch', { niche, topic: topic || undefined, count }),
  generateBatchStatus: (run_id) => getJSON('/generate/batch/status/' + run_id),
  studioBoard: () => getJSON('/studio/board'),
  studioGet: (id) => getJSON('/studio/' + id),
  studioCreate: (payload) => postJSON('/studio', payload),
  studioUpdate: (id, payload) => patchJSON('/studio/' + id, payload),
  studioDelete: (id) => delJSON('/studio/' + id),

  // Winner clone — top performers + variation script generation
  winners: () => getJSON('/winners'),
  winnersClone: (payload) => postJSON('/winners/clone', payload),
  winnersCloneStatus: (run_id) => getJSON('/winners/clone/status/' + run_id),

  decompose: (youtube_url) => postJSON('/decompose', { youtube_url }),
  decomposeNoAI: (youtube_url) => postJSON('/decompose', { youtube_url, group_clips: false, split_files: true }),
  decomposePerMinute: (youtube_url) => postJSON('/decompose', { youtube_url, group_clips: false, split_files: true, interval_sec: 60 }),
  decomposeStatus: (run_id) => getJSON('/decompose/status/' + encodeURIComponent(run_id)),
  sourceSegments: (source_id) => getJSON('/sources/' + source_id + '/segments'),
  sourceAnalysis: (source_id) => getJSON('/sources/' + source_id + '/analysis'),
  storyboardStatus: (youtube_url) => getJSON('/analyze/storyboard-status?youtube_url=' + encodeURIComponent(youtube_url)),
  getGeminiBrief: (youtube_url, { audio_start, audio_end } = {}) => {
    const params = new URLSearchParams({ youtube_url })
    if (audio_start !== undefined && audio_start !== null) params.set('audio_start', audio_start)
    if (audio_end !== undefined && audio_end !== null) params.set('audio_end', audio_end)
    return getJSON('/analyze/gemini-brief?' + params.toString())
  },
  importStoryboard: (youtube_url, storyboard) => postJSON('/analyze/import', { youtube_url, storyboard }),

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

// Job status helper: a job is "active running" if:
// - For analyze_source: status=running AND created < 30 min ago
// - For decompose: status is one of the active stages (not done/error) AND created < 30 min ago
// Real analyze jobs finish in minutes; anything running >30 min is stale/crashed/test.
export function isActiveRunning(job) {
  const now = Date.now() / 1000
  const age = now - job.created
  if (age >= 1800) return false  // 30 minutes in seconds

  // Analyze runs: status must be 'running'
  if (job.kind === 'analyze_source' || !job.kind) {
    return job.status === 'running'
  }

  // Decompose runs: status must be one of the active stages
  if (job.kind === 'decompose') {
    const activeStages = ['downloading', 'detecting', 'grouping', 'splitting', 'finding', 'saving']
    return activeStages.includes(job.status)
  }

  return false
}
