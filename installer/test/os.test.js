import { test } from 'node:test'
import assert from 'node:assert/strict'
import { detectOS, PREREQS } from '../index.js'

test('maps node platform strings to os keys', () => {
  assert.equal(detectOS('darwin'), 'mac')
  assert.equal(detectOS('linux'), 'linux')
  assert.equal(detectOS('win32'), 'windows')
})

test('every os has a manager and the core packages', () => {
  for (const os of ['mac', 'linux', 'windows']) {
    assert.ok(PREREQS[os].manager)
    const pkgs = PREREQS[os].packages.join(' ')
    for (const need of ['node', 'python', 'ffmpeg', 'postgres']) {
      assert.match(pkgs.toLowerCase(), new RegExp(need))
    }
  }
})
