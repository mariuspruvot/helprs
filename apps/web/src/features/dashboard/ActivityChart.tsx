/**
 * ActivityChart — flex-based bar chart matching the R2 redesign mockup.
 * 30 bars with 3px gap, 120px height, accent color with active highlight.
 */

interface DailyCount {
  date: string
  count: number
}

interface ActivityChartProps {
  data: DailyCount[]
}

/** Fill sparse data to 30 consecutive days ending today. */
function fillToThirtyDays(data: DailyCount[]): DailyCount[] {
  const map = new Map(data.map((d) => [d.date.slice(0, 10), d.count]))
  const result: DailyCount[] = []
  const today = new Date()
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    const key = d.toISOString().slice(0, 10)
    result.push({ date: key, count: map.get(key) ?? 0 })
  }
  return result
}

export default function ActivityChart({ data }: ActivityChartProps) {
  const days = fillToThirtyDays(data)
  const maxCount = Math.max(...days.map((d) => d.count), 1)

  return (
    <div>
      <div className="flex items-end gap-[3px]" style={{ height: 120 }}>
        {days.map((d, i) => {
          const heightPx = d.count === 0 ? 2 : Math.max(4, (d.count / maxCount) * 110)
          const isRecent = i >= 23
          const isEmpty = d.count === 0

          return (
            <div
              key={d.date}
              className="flex-1 rounded-[2px] transition-opacity hover:opacity-100"
              style={{
                height: heightPx,
                backgroundColor: isEmpty
                  ? 'var(--color-rule)'
                  : isRecent
                    ? 'var(--color-accent)'
                    : 'rgba(226,160,57,0.35)',
                opacity: isEmpty ? 0.5 : isRecent ? 1 : 0.85,
              }}
              title={`${d.date}: ${d.count} session${d.count !== 1 ? 's' : ''}`}
            />
          )
        })}
      </div>
      <div className="flex justify-between mt-2 font-mono text-[10px] text-dim2 tracking-[0.12em]">
        <span>30D AGO</span>
        <span>15D</span>
        <span>7D</span>
        <span>TODAY</span>
      </div>
    </div>
  )
}
