import { test } from 'node:test'
import assert from 'node:assert/strict'
import { conflictingPorts } from '../index.js'

test('returns ports reported busy by the probe', () => {
  const probe = (p) => p === 8000
  assert.deepEqual(conflictingPorts([5432, 8000, 1241], probe), [8000])
})
