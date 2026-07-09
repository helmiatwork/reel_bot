<script>
  import { onDestroy } from 'svelte'
  import Chart from 'chart.js/auto'

  let { labels = [], datasets = [], height = 118, chartType = 'line' } = $props()
  let canvas
  let chart

  $effect(() => {
    // Snapshot to plain objects — Chart.js calls Object.defineProperty on the
    // dataset objects, which a $state proxy rejects (state_descriptors_fixed),
    // throwing during init and corrupting the whole app's reactivity flush.
    const lbl = $state.snapshot(labels)
    const rawDs = $state.snapshot(datasets)
    if (!canvas) return
    if (chart) chart.destroy()
    // Read CSS vars at chart creation time so both light and dark themes render correctly
    const style = getComputedStyle(document.documentElement)
    const gridColor = style.getPropertyValue('--line').trim() || '#1f2937'
    const mutColor  = style.getPropertyValue('--mut').trim()  || '#878a99'

    const type = chartType === 'bar' ? 'bar' : 'line'
    const ds = rawDs.map(d => {
      const out = { ...d }
      if (type === 'line') {
        out.tension = 0
        out.cubicInterpolationMode = 'monotone'
      }
      if (chartType === 'area') out.fill = 'origin'
      if (type === 'bar') {
        // ponytail: derive opaque bar fill from series line color
        out.backgroundColor = (d.borderColor || '#6ea8fe') + 'bb'
        delete out.borderDash
        delete out.pointRadius
        delete out.tension
      }
      return out
    })

    chart = new Chart(canvas, {
      type,
      data: { labels: lbl, datasets: ds },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: mutColor, boxWidth: 12, font: { size: 11 } } } },
        scales: {
          x: { ticks: { color: mutColor, font: { size: 11 } }, grid: { color: gridColor } },
          y: {
            ticks: { color: mutColor, font: { size: 11 }, callback: (v) => (v / 1e6).toFixed(1) + 'jt' },
            grid: { color: gridColor }
          }
        }
      }
    })
  })

  onDestroy(() => chart && chart.destroy())
</script>

<div style="height:{height}px;position:relative">
  <canvas bind:this={canvas}></canvas>
</div>
