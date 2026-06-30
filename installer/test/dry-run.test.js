import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'

test('--dry-run --native prints the plan and exits 0 without touching the system', () => {
  const r = spawnSync(process.execPath, ['installer/index.js', '--native', '--dry-run', '--skip-up'], { encoding: 'utf8' })
  assert.equal(r.status, 0, r.stderr)
  assert.match(r.stdout, /\[dry-run\]/)
  assert.match(r.stdout, /Procfile/)
  assert.doesNotMatch(r.stdout, /docker compose up/)
})
