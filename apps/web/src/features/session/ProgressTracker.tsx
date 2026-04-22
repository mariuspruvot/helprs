/**
 * ProgressTracker — shows question progress in the session rail.
 * Q1 done / Q2 current / Q3 pending
 */

import { Chip, Dot } from '../../shared/components'

interface ProgressTrackerProps {
  totalQuestions: number
  currentQuestion: number
  isComplete: boolean
}

export default function ProgressTracker({ totalQuestions, currentQuestion, isComplete }: ProgressTrackerProps) {
  if (totalQuestions <= 0) return null

  return (
    <div className="space-y-2">
      {Array.from({ length: totalQuestions }, (_, i) => {
        const qNum = i + 1
        const isDone = isComplete || qNum < currentQuestion
        const isCurrent = !isComplete && qNum === currentQuestion
        const isPending = !isDone && !isCurrent

        return (
          <div key={qNum} className="flex items-center gap-2">
            {isDone && <Dot color="ok" />}
            {isCurrent && <Dot color="accent" pulse />}
            {isPending && <Dot />}
            <span className={`font-mono text-xs ${isDone ? 'text-ok' : isCurrent ? 'text-accent' : 'text-dim2'}`}>
              Q{qNum}
            </span>
            <Chip variant={isDone ? 'ok' : isCurrent ? 'accent' : 'default'}>
              {isDone ? 'done' : isCurrent ? 'current' : 'pending'}
            </Chip>
          </div>
        )
      })}
    </div>
  )
}
