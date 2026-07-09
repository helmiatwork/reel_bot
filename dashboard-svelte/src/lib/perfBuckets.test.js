import assert from 'assert'
import { rangeFilter, bucket } from './perfBuckets.js'

// -- rangeFilter custom (deterministic, no clock dependency) -------------------
{
  const labels = ['2026-07-01','2026-07-02','2026-07-03','2026-07-04','2026-07-05']
  const data   = [[100,120,130,140,150],[10,15,20,25,30]]
  const { labels: fl, data: fd } = rangeFilter(labels, data, 'custom', '2026-07-02', '2026-07-04')
  assert.deepEqual(fl, ['2026-07-02','2026-07-03','2026-07-04'])
  assert.deepEqual(fd[0], [120,130,140])
  assert.deepEqual(fd[1], [15,20,25])
  console.log('  ✓ rangeFilter custom')
}

// -- rangeFilter 'all' → identity ---------------------------------------------
{
  const labels = ['2026-07-01','2026-07-05']
  const data   = [[100,150]]
  const { labels: fl, data: fd } = rangeFilter(labels, data, 'all', null, null)
  assert.deepEqual(fl, labels)
  assert.deepEqual(fd, data)
  console.log('  ✓ rangeFilter all')
}

// -- rangeFilter preserves nulls (gap data) ------------------------------------
{
  const labels = ['2026-07-01','2026-07-02','2026-07-03']
  const data   = [[100,null,130]]
  const { labels: fl, data: fd } = rangeFilter(labels, data, 'custom', '2026-07-01', '2026-07-02')
  assert.deepEqual(fl, ['2026-07-01','2026-07-02'])
  assert.deepEqual(fd[0], [100,null])
  console.log('  ✓ rangeFilter preserves nulls')
}

// -- bucket monthly (last value per month) ------------------------------------
{
  const labels = ['2026-06-15','2026-06-28','2026-07-05','2026-07-07']
  const data   = [[100,200,300,350],[10,20,30,40]]
  const { labels: bl, data: bd } = bucket(labels, data, 'M')
  assert.deepEqual(bl, ['2026-06','2026-07'])
  assert.deepEqual(bd[0], [200,350])
  assert.deepEqual(bd[1], [20,40])
  console.log('  ✓ bucket monthly')
}

// -- bucket quarterly (last value per quarter) ---------------------------------
{
  const labels = ['2026-01-15','2026-02-28','2026-04-05','2026-07-07']
  const data   = [[100,200,300,350],[10,20,30,40]]
  const { labels: bl, data: bd } = bucket(labels, data, 'Q')
  assert.deepEqual(bl, ['2026-Q1','2026-Q2','2026-Q3'])
  assert.deepEqual(bd[0], [200,300,350])
  assert.deepEqual(bd[1], [20,30,40])
  console.log('  ✓ bucket quarterly')
}

// -- bucket 'D' → identity ----------------------------------------------------
{
  const labels = ['2026-07-01','2026-07-02']
  const data   = [[100,150],[10,20]]
  const { labels: bl, data: bd } = bucket(labels, data, 'D')
  assert.deepEqual(bl, labels)
  assert.deepEqual(bd, data)
  console.log('  ✓ bucket daily (identity)')
}

console.log('perfBuckets: all 6 tests pass')
