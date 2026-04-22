/**
 * ScorecardDisplay — renders a parsed helprs-scorecard as dimension bars + summary.
 * Used in the session rail (compact) and in the post-session expanded view.
 */

import type { ScorecardResponse } from './containerApi'

interface ScorecardDisplayProps {
  scorecard: ScorecardResponse
  expanded?: boolean
}

function DimensionBar({ name, value }: { name: string; value: number }) {
  const percentage = Math.min(100, Math.max(0, (value / 10) * 100))
  const color =
    value >= 7 ? 'var(--color-ok)' :
    value >= 4 ? 'var(--color-accent)' :
    'var(--color-danger)'

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] text-dim uppercase tracking-[0.12em]">{name}</span>
        <span className="font-mono text-[13px] font-bold" style={{ color }}>{value}</span>
      </div>
      <div className="h-1.5 bg-rule rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${percentage}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}

export default function ScorecardDisplay({ scorecard, expanded = false }: ScorecardDisplayProps) {
  const dimensions = Object.entries(scorecard.dimensions)
  const avg = dimensions.length > 0
    ? Math.round((dimensions.reduce((sum, [, v]) => sum + v, 0) / dimensions.length) * 10) / 10
    : 0

  return (
    <div>
      {/* Overall score */}
      <div className="flex items-baseline gap-2 mb-4">
        <span className="font-mono text-3xl font-bold text-ink">{avg}</span>
        <span className="font-mono text-sm text-dim">/ 10</span>
      </div>

      {/* Dimension bars */}
      <div className="space-y-3 mb-4">
        {dimensions.map(([name, value]) => (
          <DimensionBar key={name} name={name} value={value} />
        ))}
      </div>

      {/* Summary */}
      {scorecard.summary && (
        <p className="text-ink2 text-sm font-sans leading-relaxed mb-3">
          {scorecard.summary}
        </p>
      )}

      {/* Highlights (expanded only) */}
      {expanded && scorecard.highlights && scorecard.highlights.length > 0 && (
        <div className="mt-4 pt-4 border-t border-rule">
          <span className="font-mono text-[10px] text-dim uppercase tracking-[0.16em]">Highlights</span>
          <ul className="mt-2 space-y-1">
            {scorecard.highlights.map((h, i) => (
              <li key={i} className="text-ink2 text-xs font-sans flex gap-2">
                <span className="text-accent shrink-0">{'\u25b8'}</span>
                {h}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Meta (expanded only) */}
      {expanded && scorecard.questions_asked !== undefined && (
        <div className="mt-3 text-dim text-xs font-mono">
          {scorecard.questions_answered ?? 0}/{scorecard.questions_asked} questions answered
        </div>
      )}
    </div>
  )
}

