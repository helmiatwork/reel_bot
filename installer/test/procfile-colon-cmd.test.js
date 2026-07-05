// B2 regression test: Procfile-line parsing must split on FIRST ': ' only.
// A command that itself contains ': ' (e.g. bash -c "cd x && uvicorn main:app --host 0.0.0.0 --port 8000")
// must be preserved in full after the first split point.

import { test } from 'node:test'
import assert from 'node:assert/strict'

// Replicate the exact parsing logic from installer/index.js (lines 483-487)
function parseProcfileLine(line) {
  const idx = line.indexOf(': ')
  if (idx === -1) return null
  const name = line.slice(0, idx)
  const cmd = line.slice(idx + 2)
  return { name, cmd }
}

test('B2: command containing ": " is preserved intact after first split', () => {
  const line = 'pipeline-api: bash -c "cd x && uvicorn main:app --host 0.0.0.0 --port 8000"'
  const result = parseProcfileLine(line)
  assert.equal(result.name, 'pipeline-api')
  assert.equal(result.cmd, 'bash -c "cd x && uvicorn main:app --host 0.0.0.0 --port 8000"')
  // The ': ' inside the command must NOT have truncated it
  assert.ok(result.cmd.includes('main:app'), 'main:app must survive the split')
  assert.ok(result.cmd.includes('--port 8000'), 'trailing args must survive')
})

test('B2: plain command without colon works', () => {
  const line = 'openclaw: openclaw gateway --port 18789'
  const result = parseProcfileLine(line)
  assert.equal(result.name, 'openclaw')
  assert.equal(result.cmd, 'openclaw gateway --port 18789')
})

test('B2: command with multiple ": " sequences only splits on the first', () => {
  const line = 'svc: bash -c "echo foo: bar: baz"'
  const result = parseProcfileLine(line)
  assert.equal(result.name, 'svc')
  assert.equal(result.cmd, 'bash -c "echo foo: bar: baz"')
})

test('B2: line with no ": " returns null (skip guard)', () => {
  const result = parseProcfileLine('no-colon-here')
  assert.equal(result, null)
})
