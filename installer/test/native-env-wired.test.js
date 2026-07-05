import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'

test('native dry-run includes the .env localhost rewrite step', () => {
  const r = spawnSync(process.execPath, ['installer/index.js', '--native', '--dry-run', '--skip-up'], { encoding: 'utf8' })
  assert.equal(r.status, 0, r.stderr)
  assert.match(r.stdout, /\.env.*localhost/i)
})
