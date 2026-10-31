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

// ATM calls need the HTTP status (409 = reference not analyzed yet), so they return {ok, status, data}.
async function atmReq(method, path, body, raw = false) {
  try {
    const r = await fetch(path, {
      method,
      headers: body === undefined || raw ? {} : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : raw ? body : JSON.stringify(body)
    })
    let data = null
    try { data = await r.json() } catch (e) {}
    return { ok: r.ok, status: r.status, data }
  } catch (e) {
    return { ok: false, status: 0, data: null }
  }
}

export const api = {
  services: () => getJSON('/dash/services'),
  restartService: (name) => postJSON(`/dash/restart/${name}`, {}),
  restartAll: () => postJSON('/dash/restart-all', {}),
  table: (name, limit = 25, offset = 0) => getJSON(`/dash/table/${name}?limit=${limit}&offset=${offset}`),
  analysis: (limit = 25, offset = 0) => getJSON('/dash/analysis?limit=' + limit + '&offset=' + offset),
  clipFinds: (limit = 25, offset = 0) => getJSON('/dash/clip-finds?limit=' + limit + '&offset=' + offset),
  findClips: (youtube_url, max_clips = 8) => postJSON('/clips/find-claude', { youtube_url, max_clips }),
  discover: (niche, topic = '', top_n = 3) => postJSON('/pipeline/discover', { niche, topic, top_n }),
  research: (youtube_url, topic = '') => postJSON('/pipeline/research', { youtube_url, topic }),

  // Songs — audio extracted from analyzed videos + user imports
  getSongs: (limit = 25, offset = 0, tag = '', mood = '', kind = '') => {
    const p = new URLSearchParams({ limit, offset })
    if (tag) p.set('tag', tag)
    if (mood) p.set('mood', mood)
    if (kind) p.set('kind', kind)
    return getJSON(`/songs?${p}`)
  },
  songImport: async (file, { title = '', tags = [], mood = '', genre = '', kind = 'song' } = {}) => {
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('title', title)
      fd.append('tags', JSON.stringify(tags))
      fd.append('mood', mood)
      fd.append('genre', genre)
      fd.append('kind', kind)
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
  notifications: () => getJSON('/notifications'),
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

  seoAnalyze: (topic, platform = 'youtube', niche = '') => postJSON('/seo/analyze', { topic, platform, niche }),

  // Prep Bundle — aggregate assets for CapCut finishing
  prepList: () => getJSON('/prep/list'),
  prepGet: (id) => getJSON('/prep/' + id),
  prepSetBgm: (id, bgm_song_id) => patchJSON('/prep/' + id, { bgm_song_id }),
  prepRoughcut: (id) => postJSON('/prep/' + id + '/roughcut', {}),
  prepZipUrl: (id) => '/prep/' + id + '/zip',

  // ATM creator studio
  atmMine: (channel_url, limit = 20) => atmReq('POST', '/atm/mine', { channel_url, limit }),
  atmMineImport: (urls, niche = '', titles = {}) => atmReq('POST', '/atm/mine/import', { urls, niche, titles }),
  atmItems: (status = '') => atmReq('GET', '/atm/items' + (status ? '?status=' + status : '')),
  atmItemCreate: (body) => atmReq('POST', '/atm/items', body),
  atmItem: (id) => atmReq('GET', '/atm/items/' + id),
  atmItemPatch: (id, body) => atmReq('PATCH', '/atm/items/' + id, body),
  atmItemDelete: (id) => atmReq('DELETE', '/atm/items/' + id),
  atmSettings: () => atmReq('GET', '/atm/settings'),
  atmModels: () => atmReq('GET', '/atm/models'),
  atmSettingsSave: (body) => atmReq('PUT', '/atm/settings', body),
  atmBlueprint: (id, section) => atmReq('POST', '/atm/items/' + id + '/blueprint', section ? { section } : {}),
  atmVoiceEstimate: (id) => atmReq('GET', '/atm/items/' + id + '/voice/estimate'),
  atmVoice: (id, beat) => atmReq('POST', '/atm/items/' + id + '/voice', beat ? { beat } : {}),
  atmDraftUpload: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return atmReq('POST', '/atm/items/' + id + '/draft', fd, true)
  },
  atmEvaluate: (id) => atmReq('POST', '/atm/items/' + id + '/evaluate', {}),
  atmEvaluations: (id) => atmReq('GET', '/atm/items/' + id + '/evaluations'),
  atmEvalNotes: (evalId, notes) => atmReq('PATCH', '/atm/evaluations/' + evalId + '/notes', { notes }),
  atmToday: () => atmReq('GET', '/atm/today'),
  atmAutofill: () => atmReq('POST', '/atm/schedule/autofill', {}),
  atmMonitor: (id) => atmReq('GET', '/atm/items/' + id + '/monitor'),
  atmLearn: (niche = '') => atmReq('GET', '/atm/learn' + (niche ? '?niche=' + encodeURIComponent(niche) : '')),
  atmLearningDelete: (id) => atmReq('DELETE', '/atm/learnings/' + id),

  decompose: (youtube_url) => postJSON('/decompose', { youtube_url }),
  decomposeNoAI: (youtube_url) => postJSON('/decompose', { youtube_url, group_clips: false, split_files: true }),
  decomposePerMinute: (youtube_url) => postJSON('/decompose', { youtube_url, group_clips: false, split_files: true, interval_sec: 60 }),
  decomposeStatus: (run_id) => getJSON('/decompose/status/' + encodeURIComponent(run_id)),
  sourceSegments: (source_id) => getJSON('/sources/' + source_id + '/segments'),
  sourceAnalysis: (source_id) => getJSON('/sources/' + source_id + '/analysis'),
  sourceExists: (youtube_url) => getJSON('/sources/exists?youtube_url=' + encodeURIComponent(youtube_url)),
  deleteSource: (source_id) => delJSON('/sources/' + source_id),
  storyboardStatus: (youtube_url) => getJSON('/analyze/storyboard-status?youtube_url=' + encodeURIComponent(youtube_url)),
  getGeminiBrief: (youtube_url, { audio_start, audio_end } = {}) => {
    const params = new URLSearchParams({ youtube_url })
    if (audio_start !== undefined && audio_start !== null) params.set('audio_start', audio_start)
    if (audio_end !== undefined && audio_end !== null) params.set('audio_end', audio_end)
    return getJSON('/analyze/gemini-brief?' + params.toString())
  },
  getGeminiIdeas: (youtube_url) => getJSON('/analyze/gemini-ideas?youtube_url=' + encodeURIComponent(youtube_url)),
  getGeminiEffects: (youtube_url) => getJSON('/analyze/gemini-effects?youtube_url=' + encodeURIComponent(youtube_url)),
  getEffectsStatus: (youtube_url) => getJSON('/analyze/effects-status?youtube_url=' + encodeURIComponent(youtube_url)),
  getIdeasStatus: (youtube_url) => getJSON('/analyze/ideas-status?youtube_url=' + encodeURIComponent(youtube_url)),
  selectIdea: (youtube_url, index) => postJSON('/analyze/ideas/select', { youtube_url, index }),
  getIdeaDetail: (youtube_url, index) => getJSON('/analyze/gemini-idea-detail?youtube_url=' + encodeURIComponent(youtube_url) + '&index=' + index),
  importStoryboard: (youtube_url, storyboard) => postJSON('/analyze/import', { youtube_url, storyboard }),
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
