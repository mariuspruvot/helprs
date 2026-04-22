/**
 * ActivityChart — simple SVG bar chart for session activity over 30 days.
 * No external charting library — just proportional <rect> elements.
 */

interface DailyCount {
  date: string
  count: number
}

interface ActivityChartProps {
  data: DailyCount[]
}

export default function ActivityChart({ data }: ActivityChartProps) {
  if (data.length === 0) {
    return (
      <div className="text-dim text-xs font-mono py-4 text-center">
        // no sessions in the last 30 days
      </div>
    )
  }

  const maxCount = Math.max(...data.map((d) => d.count), 1)
  const barCount = data.length
  const chartWidth = 100
  const chartHeight = 80
  const barGap = 1
  const barWidth = Math.max(1, (chartWidth - barGap * (barCount - 1)) / barCount)

  return (
    <svg
      viewBox={`0 0 ${chartWidth} ${chartHeight + 16}`}
      className="w-full"
      style={{ height: '100px' }}
      preserveAspectRatio="none"
    >
      {data.map((d, i) => {
        const barHeight = Math.max(1, (d.count / maxCount) * chartHeight)
        const x = i * (barWidth + barGap)
        const y = chartHeight - barHeight

        return (
          <g key={d.date}>
            <rect
              x={x}
              y={y}
              width={barWidth}
              height={barHeight}
              rx={0.5}
              fill="var(--color-accent)"
              opacity={0.65}
            >
              <title>{`${d.date}: ${d.count} session${d.count !== 1 ? 's' : ''}`}</title>
            </rect>
            {/* Show label every 7 bars */}
            {i % 7 === 0 && (
              <text
                x={x + barWidth / 2}
                y={chartHeight + 10}
                textAnchor="middle"
                fill="var(--color-dim)"
                fontSize="3"
                fontFamily="var(--font-family-mono)"
              >
                {new Date(d.date).toLocaleDateString('en', { month: 'short', day: 'numeric' })}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
