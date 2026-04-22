/**
 * SessionRail — right sidebar for the session view.
 * Shows progress tracker, scorecard, session meta, and privacy note.
 */

import { Chip, Overline } from '../../shared/components'
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

export default function SessionRail({
  session,
  status,
  scorecard,
  questionCount,
  currentQuestion,
  isComplete,
}: SessionRailProps) {
  const isTerminal = status === 'completed' || status === 'failed' || status === 'stopped'

  return (
    <div className="w-[260px] shrink-0 border-l border-rule bg-bg2 overflow-y-auto">
      <div className="p-4 space-y-6">
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
              {session.started_at && (
                <div className="flex justify-between">
                  <span className="text-dim font-mono">Started</span>
                  <span className="text-ink2 font-mono">
                    {new Date(session.started_at).toLocaleTimeString()}
                  </span>
                </div>
              )}
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
