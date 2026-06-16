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

export const api = {
  services: () => getJSON('/dash/services'),
  overview: () => getJSON('/dash/overview'),
  table: (name) => getJSON(`/dash/table/${name}`),
  agents: () => getJSON('/dash/agents'),
  formulaPerformance: () => getJSON('/dash/formula-performance'),
  cost: () => getJSON('/dash/cost'),
  runs: (limit = 20) => getJSON(`/pipeline/runs?limit=${limit}`),
  run: (id) => getJSON(`/pipeline/run/${id}`),
  artifact: (id) => getJSON(`/pipeline/run/${id}/artifact`),
  artifactDownloadUrl: (id) => `/pipeline/run/${id}/artifact?download=true`,
  discover: (niche, topic = '', top_n = 3) => postJSON('/pipeline/discover', { niche, topic, top_n }),
  research: (youtube_url, topic = '') => postJSON('/pipeline/research', { youtube_url, topic })
}

// helpers
export function fmtViews(n) {
  n = Number(n) || 0
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.0', '') + ' jt'
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace('.0', '') + ' rb'
  return String(n)
}
