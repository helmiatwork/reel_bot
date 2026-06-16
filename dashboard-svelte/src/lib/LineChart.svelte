<script>
  import { onDestroy } from 'svelte'
  import Chart from 'chart.js/auto'

  let { labels = [], datasets = [], height = 118 } = $props()
  let canvas
  let chart

  $effect(() => {
    // re-read so the effect tracks data changes
    const lbl = labels
    const ds = datasets
    if (!canvas) return
    if (chart) chart.destroy()
    chart = new Chart(canvas, {
      type: 'line',
      data: { labels: lbl, datasets: ds },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#8b97ab', boxWidth: 12, font: { size: 11 } } } },
        scales: {
          x: { ticks: { color: '#8b97ab', font: { size: 11 } }, grid: { color: '#1f2937' } },
          y: {
            ticks: { color: '#8b97ab', font: { size: 11 }, callback: (v) => (v / 1e6).toFixed(1) + 'jt' },
            grid: { color: '#1f2937' }
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
