// 把后端 ai_data 里的图表 dict（{type, labels, data, title}）转成 ECharts option。

const BRAND = '#1E3A8A'
const PALETTE = ['#1E3A8A', '#22A06B', '#E09A2B', '#D6455A', '#5B8DEF', '#7C5BE0', '#3FB6C9', '#C778C9']
const FONT = 'Plus Jakarta Sans, PingFang SC, Microsoft YaHei, sans-serif'

export function chartToOption(chart) {
  if (!chart || typeof chart !== 'object') return null
  const ctype = (chart.type || 'line').toLowerCase()
  const labels = chart.labels || []
  const data = chart.data || []
  if (!data.length) return null

  const base = {
    grid: { left: 44, right: 16, top: 36, bottom: 28 },
    textStyle: { fontFamily: FONT, color: '#747C92' },
    tooltip: { trigger: ctype === 'pie' ? 'item' : 'axis' },
  }

  if (ctype === 'pie') {
    return {
      ...base,
      legend: { orient: 'vertical', right: 8, top: 'middle', textStyle: { color: '#747C92' } },
      series: [
        {
          type: 'pie',
          radius: ['45%', '72%'],
          center: ['40%', '50%'],
          data: labels.map((l, i) => ({ name: l, value: data[i] ?? 0 })),
          color: PALETTE,
          label: { color: '#747C92', fontSize: 12 },
        },
      ],
    }
  }

  const catAxis = { type: 'category', data: labels, axisLine: { lineStyle: { color: '#D7DCE8' } }, axisLabel: { color: '#747C92' } }
  const valAxis = { type: 'value', axisLabel: { color: '#747C92' }, splitLine: { lineStyle: { color: '#ECEFF6' } } }

  if (ctype === 'bar') {
    return {
      ...base,
      xAxis: catAxis,
      yAxis: valAxis,
      series: [{ type: 'bar', data, itemStyle: { color: BRAND, borderRadius: [6, 6, 0, 0] } }],
    }
  }
  if (ctype === 'area') {
    return {
      ...base,
      xAxis: catAxis,
      yAxis: valAxis,
      series: [
        {
          type: 'line', data, smooth: true,
          lineStyle: { color: BRAND, width: 2.5 },
          itemStyle: { color: BRAND },
          areaStyle: { color: BRAND, opacity: 0.12 },
        },
      ],
    }
  }
  // line（默认）
  return {
    ...base,
    xAxis: catAxis,
    yAxis: valAxis,
    series: [
      {
        type: 'line', data, smooth: true,
        lineStyle: { color: BRAND, width: 2.5 },
        itemStyle: { color: BRAND },
      },
    ],
  }
}
