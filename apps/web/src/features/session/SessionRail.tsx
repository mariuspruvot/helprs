/**
 * SessionRail — right sidebar for the session view.
 * Shows live timer, progress tracker, scorecard, session meta, and privacy note.
 */

import { useEffect, useState } from 'react'
import { Chip, Dot, Overline } from '../../shared/components'
import type { ScorecardResponse } from './containerApi'
import type { ContainerSessionResponse, ContainerStatus } from './containerTypes'
import ProgressTracker from './ProgressTracker'
import ScorecardDisplay from './ScorecardDisplay'

interface SessionRailProps {
  session: ContainerSessionResponse | null
  status: ContainerStatus
  scorecard: ScorecardResponse | null
  questionCount: number
  currentQuestion: number
  isComplete: boolean
}

function formatElapsed(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

function LiveTimer({ startedAt }: { startedAt: string }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const start = new Date(startedAt).getTime()
    setElapsed(Date.now() - start)
    const interval = setInterval(() => {
      setElapsed(Date.now() - start)
    }, 1000)
    return () => clearInterval(interval)
  }, [startedAt])

  return (
    <div className="flex items-center gap-2">
      <Dot color="ok" pulse />
      <span className="font-mono text-lg font-bold text-ink tabular-nums">
        {formatElapsed(elapsed)}
      </span>
    </div>
  )
}

function FinalDuration({ startedAt, completedAt }: { startedAt: string; completedAt: string }) {
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime()
  return (
    <span className="font-mono text-lg font-bold text-dim tabular-nums">
      {formatElapsed(ms)}
    </span>
  )
}

export default function SessionRail({
  session,
  status,
  scorecard,
  questionCount,
  currentQuestion,
  isComplete,
}: SessionRailProps) {
  const isTerminal = status === 'completed' || status === 'failed' || status === 'stopped'
  const isRunning = status === 'running' || status === 'starting'

  return (
    <div className="w-[260px] shrink-0 border-l border-rule bg-bg2 overflow-y-auto">
      <div className="p-4 space-y-6">
        {/* Timer */}
        {session?.started_at && (
          <section>
            <Overline className="mb-2">{'\u25b8'} ELAPSED</Overline>
            {isRunning && <LiveTimer startedAt={session.started_at} />}
            {isTerminal && session.completed_at && (
              <FinalDuration startedAt={session.started_at} completedAt={session.completed_at} />
            )}
            {isTerminal && !session.completed_at && (
              <span className="font-mono text-lg font-bold text-dim">--:--</span>
            )}
          </section>
        )}

        {/* Progress tracker */}
        {questionCount > 0 && (
          <section>
            <Overline className="mb-3">{'\u25b8'} PROGRESS</Overline>
            <ProgressTracker
              totalQuestions={questionCount}
              currentQuestion={currentQuestion}
              isComplete={isComplete}
            />
          </section>
        )}

        {/* Scorecard */}
        {scorecard && (
          <section>
            <Overline className="mb-3">{'\u25b8'} SCORECARD</Overline>
            <ScorecardDisplay scorecard={scorecard} expanded={isTerminal} />
          </section>
        )}

        {/* Session meta */}
        {session && (
          <section>
            <Overline className="mb-3">{'\u25b8'} META</Overline>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-dim font-mono">Session</span>
                <span className="text-ink2 font-mono truncate ml-2" title={session.id}>
                  {session.id.slice(0, 8)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-dim font-mono">Skill</span>
                <Chip variant="accent">{session.skill_name}</Chip>
              </div>
              <div className="flex justify-between">
                <span className="text-dim font-mono">PR</span>
                <span className="text-ink2 font-mono">#{session.pr_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-dim font-mono">Repo</span>
                <span className="text-ink2 font-mono truncate ml-2" title={session.repo_full_name}>
                  {session.repo_full_name.split('/').pop()}
                </span>
              </div>
            </div>
          </section>
        )}

        {/* Privacy note */}
        <section className="pt-2 border-t border-rule">
          <p className="text-dim2 text-[10px] font-mono leading-relaxed">
            {'\u2770'} sessions run in ephemeral containers. no data leaves your network.
          </p>
        </section>
      </div>
    </div>
  )
}
