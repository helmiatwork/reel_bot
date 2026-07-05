import { test } from 'node:test'
import assert from 'node:assert/strict'
import { nativeEnv } from '../index.js'

test('rewrites docker service hostnames to localhost', () => {
  const out = nativeEnv([
    'CLIPROXY_URL=http://cliproxy:8317/v1',
    'OPENCLAW_URL=http://openclaw:18789',
    'PIPELINE_API_URL=http://pipeline-api:8000',
    'ARCREEL_URL=http://arcreel:1241',
    'TRENDS_URL=http://trends:8200',
    'DATABASE_URL=postgresql://admin:pw@postgres:5432/content_automation',
    'DB_POSTGRESDB_HOST=postgres'
  ].join('\n'))
  assert.match(out, /CLIPROXY_URL=http:\/\/localhost:8317\/v1/)
  assert.match(out, /OPENCLAW_URL=http:\/\/localhost:18789/)
  assert.match(out, /PIPELINE_API_URL=http:\/\/localhost:8000/)
  assert.match(out, /ARCREEL_URL=http:\/\/localhost:1241/)
  assert.match(out, /TRENDS_URL=http:\/\/localhost:8200/)
  assert.match(out, /DATABASE_URL=postgresql:\/\/admin:pw@localhost:5432\/content_automation/)
  assert.match(out, /DB_POSTGRESDB_HOST=localhost/)
})

test('leaves non-service values untouched', () => {
  const out = nativeEnv('GEMINI_API_KEY=abc123\nSTORAGE_TYPE=supabase')
  assert.match(out, /GEMINI_API_KEY=abc123/)
  assert.match(out, /STORAGE_TYPE=supabase/)
})

test('is idempotent — running twice changes nothing', () => {
  const once = nativeEnv('DB_POSTGRESDB_HOST=postgres')
  assert.equal(nativeEnv(once), once)
})
