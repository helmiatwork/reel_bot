import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildProcfile } from '../index.js'

test('lists exactly the 7 long-running services, excludes on-demand tools', () => {
  const pf = buildProcfile('linux')
  const names = pf.split('\n').filter(Boolean).map((l) => l.split(':')[0])
  assert.deepEqual(names.sort(), ['arcreel', 'cliproxy', 'n8n', 'openclaw', 'pipeline-api', 'postgres', 'trends'])
  assert.ok(!pf.includes('video-analyzer'))
  assert.ok(!pf.includes('yt-pipeline'))
})

test('each entry carries its native start command with the right port', () => {
  const pf = buildProcfile('linux')
  assert.match(pf, /pipeline-api:.*uvicorn.*--port 8000/)
  assert.match(pf, /trends:.*--port 8200/)
  assert.match(pf, /n8n:.*n8n/)
})
