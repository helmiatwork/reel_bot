import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildProcfile } from '../index.js'

test('lists the native long-running services, excludes docker-only and non-existent tools', () => {
  const pf = buildProcfile('linux')
  const names = pf.split('\n').filter(Boolean).map((l) => l.split(':')[0])
  // openclaw, cliproxy are referenced but docker-only or binary-only; included in Procfile to start
  // trends doesn't exist; video-analyzer, video-splitter, yt-pipeline are docker-only
  assert.deepEqual(names.sort(), ['arcreel', 'cliproxy', 'n8n', 'openclaw', 'pipeline-api', 'postgres'])
  assert.ok(!pf.includes('video-analyzer'))
  assert.ok(!pf.includes('yt-pipeline'))
  assert.ok(!pf.includes('trends'))
})

test('each entry carries its native start command with the right port', () => {
  const pf = buildProcfile('linux')
  assert.match(pf, /pipeline-api:.*uvicorn.*--port 8000/)
  assert.match(pf, /openclaw:.*--port 18789/)
  assert.match(pf, /n8n:.*n8n/)
})
