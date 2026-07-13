// Minimal dependency-free SVG line chart. The project has no charting library
// (recharts/visx/etc. would add ~90-100KB + a new API surface); a hand-rolled
// polyline is plenty for a couple of simple per-exercise trend lines and keeps
// the bundle/dependency surface untouched.
export interface TrendPoint {
  x: string // short axis label, e.g. "6/20"
  value: number // numeric value used for the point's vertical position
  displayValue: string // formatted label shown above the point (e.g. "185" or "1:05")
  tooltip: string // native <title> text (session name + full date)
}

const W = 600
const H = 200
const PAD_X = 24
const PAD_Y = 26

export function TrendChart({ points }: { points: TrendPoint[] }) {
  if (points.length === 0) return null

  const values = points.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const innerW = W - PAD_X * 2
  const innerH = H - PAD_Y * 2

  const coords = points.map((p, i) => ({
    ...p,
    cx: points.length === 1 ? PAD_X + innerW / 2 : PAD_X + (i / (points.length - 1)) * innerW,
    cy: PAD_Y + innerH * (1 - (p.value - min) / range),
  }))

  const path = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.cx.toFixed(1)} ${c.cy.toFixed(1)}`).join(' ')

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      role="img"
      aria-label={`Trend across ${points.length} session${points.length === 1 ? '' : 's'}, from ${points[0].displayValue} to ${points[points.length - 1].displayValue}`}
    >
      <path d={path} fill="none" stroke="#fbbf24" strokeWidth={2} />
      {coords.map((c, i) => (
        <g key={i}>
          <title>{c.tooltip}</title>
          <circle cx={c.cx} cy={c.cy} r={4} fill="#fbbf24" />
          <text x={c.cx} y={Math.max(10, c.cy - 10)} textAnchor="middle" className="fill-slate-300 text-[9px]">
            {c.displayValue}
          </text>
        </g>
      ))}
      <text x={coords[0].cx} y={H - 6} textAnchor="start" className="fill-slate-500 text-[9px]">
        {points[0].x}
      </text>
      {points.length > 1 && (
        <text
          x={coords[coords.length - 1].cx}
          y={H - 6}
          textAnchor="end"
          className="fill-slate-500 text-[9px]"
        >
          {points[points.length - 1].x}
        </text>
      )}
    </svg>
  )
}
