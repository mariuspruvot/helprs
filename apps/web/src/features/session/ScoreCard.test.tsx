import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'
import ScoreCard from './ScoreCard'
import type { ScoreData } from './types'

afterEach(() => cleanup())

const STRONG_SCORE: ScoreData = {
  depth: 7,
  accuracy: 8,
  completeness: 6,
  insight: 9,
  verdict: 'strong',
  gaps: ['Explore error handling patterns', 'Review concurrency edge cases'],
}

describe('ScoreCard', () => {
  test('renders all four dimension bars', () => {
    render(<ScoreCard score={STRONG_SCORE} />)
    expect(screen.getByTestId('score-dimension-depth')).toBeTruthy()
    expect(screen.getByTestId('score-dimension-accuracy')).toBeTruthy()
    expect(screen.getByTestId('score-dimension-completeness')).toBeTruthy()
    expect(screen.getByTestId('score-dimension-insight')).toBeTruthy()
  })

  test('renders verdict badge with correct text', () => {
    render(<ScoreCard score={STRONG_SCORE} />)
    expect(screen.getByTestId('score-verdict').textContent).toBe('Strong')
  })

  test('renders gap summary items', () => {
    render(<ScoreCard score={STRONG_SCORE} />)
    const gaps = screen.getByTestId('score-gaps')
    expect(gaps.querySelectorAll('li')).toHaveLength(2)
  })

  test('renders AI disclaimer (FR38)', () => {
    render(<ScoreCard score={STRONG_SCORE} />)
    const label = screen.getByTestId('score-ai-label')
    expect(label.textContent).toContain('AI-generated')
  })

  test('provides ARIA labels for dimensions', () => {
    render(<ScoreCard score={STRONG_SCORE} />)
    expect(screen.getByLabelText('Depth score: 7 out of 10')).toBeTruthy()
    expect(screen.getByLabelText('Accuracy score: 8 out of 10')).toBeTruthy()
    expect(screen.getByLabelText('Completeness score: 6 out of 10')).toBeTruthy()
    expect(screen.getByLabelText('Insight score: 9 out of 10')).toBeTruthy()
  })

  test('provides ARIA label for verdict', () => {
    render(<ScoreCard score={STRONG_SCORE} />)
    expect(screen.getByLabelText('Verdict: Strong')).toBeTruthy()
  })

  test('renders no gap section when gaps empty', () => {
    const noGaps = { ...STRONG_SCORE, gaps: [] }
    render(<ScoreCard score={noGaps} />)
    expect(screen.queryByTestId('score-gaps')).toBeNull()
  })

  test('verdict labels capitalize correctly', () => {
    const { rerender } = render(<ScoreCard score={{ ...STRONG_SCORE, verdict: 'exceptional' }} />)
    expect(screen.getByTestId('score-verdict').textContent).toBe('Exceptional')

    rerender(<ScoreCard score={{ ...STRONG_SCORE, verdict: 'adequate' }} />)
    expect(screen.getByTestId('score-verdict').textContent).toBe('Adequate')

    rerender(<ScoreCard score={{ ...STRONG_SCORE, verdict: 'weak' }} />)
    expect(screen.getByTestId('score-verdict').textContent).toBe('Weak')
  })
})
