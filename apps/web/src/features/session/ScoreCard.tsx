/**
 * Story 4.1: inline score card rendered as the session's natural conclusion.
 *
 * Displays four horizontal dimension bars (Depth, Accuracy, Completeness,
 * Insight), a verdict badge, and a "Areas to deepen" gap summary. All
 * dimension values and the verdict have descriptive ARIA labels (UX-DR18).
 * An AI-produced disclaimer is shown (FR38).
 *
 * Layout: 24px padding (UX-DR8), verdict 16px/700, dimension labels 14px/500.
 */

import type { ScoreData } from './types'

interface ScoreCardProps {
  score: ScoreData
}

const DIMENSIONS = [
  { key: 'depth' as const, label: 'Depth', color: '#E2A039' },
  { key: 'accuracy' as const, label: 'Accuracy', color: '#30d158' },
  { key: 'completeness' as const, label: 'Completeness', color: '#ff9f0a' },
  { key: 'insight' as const, label: 'Insight', color: '#ff3b30' },
] as const

const VERDICT_COLORS: Record<string, string> = {
  exceptional: '#30d158',
  strong: '#E2A039',
  adequate: '#9a9898',
  weak: '#ff9f0a',
  insufficient: '#ff9f0a',
}

function verdictLabel(verdict: string): string {
  return verdict.charAt(0).toUpperCase() + verdict.slice(1)
}

export default function ScoreCard({ score }: ScoreCardProps) {
  const verdictColor = VERDICT_COLORS[score.verdict] ?? '#9a9898'

  return (
    <article
      data-testid="score-card"
      className="w-full text-text-primary"
      style={{
        padding: 24,
        borderRadius: 12,
        backgroundColor: '#252121',
        boxShadow: 'rgba(255,255,255,0.05) 0 0 0 1px',
      }}
    >
      {/* Screen-reader-only prefix */}
      <span className="sr-only">Comprehension score results:</span>

      {/* Verdict badge */}
      <div
        data-testid="score-verdict"
        aria-label={`Verdict: ${verdictLabel(score.verdict)}`}
        style={{
          display: 'inline-block',
          padding: '4px 12px',
          borderRadius: 16,
          backgroundColor: verdictColor,
          color: '#fff',
          fontSize: 16,
          fontWeight: 700,
          marginBottom: 16,
        }}
      >
        {verdictLabel(score.verdict)}
      </div>

      {/* Dimension bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
        {DIMENSIONS.map((dim) => {
          const value = score[dim.key]
          return (
            <div key={dim.key} data-testid={`score-dimension-${dim.key}`}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: 14,
                  fontWeight: 500,
                  marginBottom: 4,
                }}
              >
                <span>{dim.label}</span>
                <span aria-label={`${dim.label}: ${value} out of 10`}>{value}/10</span>
              </div>
              <div
                style={{
                  height: 8,
                  borderRadius: 4,
                  backgroundColor: 'rgba(255,255,255,0.1)',
                  overflow: 'hidden',
                }}
                role="progressbar"
                aria-valuenow={value}
                aria-valuemin={0}
                aria-valuemax={10}
                aria-label={`${dim.label} score: ${value} out of 10`}
              >
                <div
                  style={{
                    width: `${(value / 10) * 100}%`,
                    height: '100%',
                    borderRadius: 4,
                    backgroundColor: dim.color,
                    transition: 'width 0.6s ease-out',
                  }}
                />
              </div>
            </div>
          )
        })}
      </div>

      {/* Gap summary */}
      {score.gaps.length > 0 && (
        <div data-testid="score-gaps" style={{ marginBottom: 12 }}>
          <h4
            style={{
              fontSize: 14,
              fontWeight: 600,
              marginBottom: 8,
              color: '#aaa',
            }}
          >
            Areas to deepen
          </h4>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {score.gaps.map((gap, i) => (
              <li
                key={i}
                style={{ fontSize: 14, lineHeight: 1.6, color: '#ccc' }}
              >
                {gap}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* AI-produced disclaimer (FR38) */}
      <p
        data-testid="score-ai-label"
        style={{
          fontSize: 11,
          color: '#777',
          marginTop: 8,
          marginBottom: 0,
        }}
      >
        AI-generated — scores reflect an automated assessment, not a definitive evaluation.
      </p>
    </article>
  )
}
