// Small dependency-free SVG charts for the operations console.

interface DailyPoint {
  date: string
  units: number
  moving_average_7d: number
}

/** Bars for units sold each day with the 7-day moving average drawn over them. */
export function DemandChart({ daily }: { daily: DailyPoint[] }) {
  const width = 640
  const height = 200
  const pad = { top: 10, right: 8, bottom: 22, left: 30 }
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom
  const max = Math.max(1, ...daily.map((d) => Math.max(d.units, d.moving_average_7d)))
  const step = innerW / Math.max(1, daily.length)
  const y = (value: number) => pad.top + innerH - (value / max) * innerH

  const line = daily
    .map((d, i) => `${i === 0 ? 'M' : 'L'}${(pad.left + i * step + step / 2).toFixed(1)},${y(d.moving_average_7d).toFixed(1)}`)
    .join(' ')

  // A set, because with a tiny maximum the middle and top ticks are the same number.
  const ticks = [...new Set([0, Math.ceil(max / 2), Math.ceil(max)])]

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="demand-chart" role="img" aria-label="Units sold per day with 7-day moving average">
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} className="chart-grid" />
          <text x={pad.left - 4} y={y(tick) + 3} textAnchor="end" className="chart-axis">
            {tick}
          </text>
        </g>
      ))}
      {daily.map((d, i) => (
        <rect key={d.date} x={pad.left + i * step + 0.5} y={y(d.units)} width={Math.max(1, step - 1)} height={pad.top + innerH - y(d.units)} className="chart-bar">
          <title>
            {d.date}: {d.units} units
          </title>
        </rect>
      ))}
      <path d={line} className="chart-line" fill="none" />
      <text x={pad.left} y={height - 6} className="chart-axis">
        {daily[0]?.date}
      </text>
      <text x={width - pad.right} y={height - 6} textAnchor="end" className="chart-axis">
        {daily[daily.length - 1]?.date}
      </text>
    </svg>
  )
}

interface Period {
  period: string
  units: number
}

/** Plain bars for weekly or monthly totals. */
export function PeriodBars({ periods, label }: { periods: Period[]; label: (period: string) => string }) {
  if (periods.length === 0) return <p className="muted">No sales in this period.</p>
  const max = Math.max(1, ...periods.map((p) => p.units))
  return (
    <div className="period-bars">
      {periods.map((p) => (
        <div key={p.period} className="period-bar" title={`${label(p.period)}: ${p.units} units`}>
          <span className="period-value">{p.units}</span>
          <div className="period-fill" style={{ height: `${(p.units / max) * 100}%` }} />
          <span className="period-label">{label(p.period)}</span>
        </div>
      ))}
    </div>
  )
}

interface BarListItem {
  label: string
  value: number
}

/** Horizontal bars, used by the Analytics page. */
export function BarList({ items, formatValue }: { items: BarListItem[]; formatValue?: (value: number) => string }) {
  if (items.length === 0) return <p className="muted">No data yet.</p>
  const max = Math.max(...items.map((i) => i.value), 1)
  return (
    <div className="bar-list">
      {items.map((item) => (
        <div className="bar-row" key={item.label}>
          <span className="bar-label">{item.label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(item.value / max) * 100}%` }} />
          </div>
          <span className="bar-value">{formatValue ? formatValue(item.value) : item.value}</span>
        </div>
      ))}
    </div>
  )
}
