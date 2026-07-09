// ponytail: views are cumulative (latest snapshot per video, summed by platform per day),
// so bucketing takes the last value in each period rather than summing.

/**
 * Filter parallel {labels, data[][]} by date range.
 * @param {string[]} labels - sorted ISO date strings
 * @param {Array[]} dataArr - parallel arrays of values (null for gaps)
 * @param {'7d'|'30d'|'90d'|'year'|'all'|'custom'} range
 * @param {string} customFrom - ISO date, used when range==='custom'
 * @param {string} customTo   - ISO date, used when range==='custom'
 * @returns {{ labels: string[], data: Array[] }}
 */
export function rangeFilter(labels, dataArr, range, customFrom, customTo) {
  const from = _rangeFrom(range, customFrom)
  const to = range === 'custom' ? (customTo || null) : null
  const mask = labels.map(l => (!from || l >= from) && (!to || l <= to))
  return {
    labels: labels.filter((_, i) => mask[i]),
    data: dataArr.map(d => d.filter((_, i) => mask[i])),
  }
}

/**
 * Bucket parallel {labels, data[][]} into monthly or quarterly periods.
 * @param {string[]} labels
 * @param {Array[]} dataArr
 * @param {'D'|'M'|'Q'} granularity
 * @returns {{ labels: string[], data: Array[] }}
 */
export function bucket(labels, dataArr, granularity) {
  if (granularity === 'D' || !labels.length) return { labels, data: dataArr }
  const keyOf = l => granularity === 'M' ? l.slice(0, 7) : _qKey(l)
  const keys = [...new Set(labels.map(keyOf))].sort()
  const data = dataArr.map(d => {
    const b = {}
    labels.forEach((l, i) => { if (d[i] != null) b[keyOf(l)] = d[i] })
    return keys.map(k => b[k] ?? null)
  })
  return { labels: keys, data }
}

function _rangeFrom(range, customFrom) {
  const d = new Date()
  if (range === '7d')    return _daysAgo(d, 6)
  if (range === '30d')   return _daysAgo(d, 29)
  if (range === '90d')   return _daysAgo(d, 89)
  if (range === 'year')  return `${d.getFullYear()}-01-01`
  if (range === 'custom') return customFrom || null
  return null  // 'all' → no lower bound
}

function _daysAgo(d, n) {
  const c = new Date(d); c.setDate(c.getDate() - n); return c.toISOString().slice(0, 10)
}

function _qKey(dateStr) {
  const [y, m] = dateStr.split('-').map(Number)
  return `${y}-Q${Math.ceil(m / 3)}`
}
