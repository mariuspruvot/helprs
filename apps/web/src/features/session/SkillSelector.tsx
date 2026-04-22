/**
 * SkillSelector — displays available skills as cards.
 * Skills per spec: challenge-me (active), eli5/pair-debug/hot-seat/test-me (coming soon).
 */

import { Card, Chip, Overline } from '../../shared/components'
import type { Skill } from './containerTypes'

const SKILLS: Skill[] = [
  {
    name: 'challenge-me',
    label: 'Challenge Me',
    description: 'Socratic quiz — tests your understanding of your own PR changes. 3 questions targeting failure modes, system knowledge, and design trade-offs.',
    duration: '5-10 min',
  },
  {
    name: 'eli5',
    label: 'ELI5',
    description: 'Explain Like I\'m 5 — can you vulgarize your own code? Picks complex sections and asks you to explain them simply.',
    duration: '5-8 min',
    comingSoon: true,
  },
  {
    name: 'pair-debug',
    label: 'Pair Debug',
    description: 'Find the subtle bug Claude injected into your code. Ask questions, narrow it down, submit your diagnosis.',
    duration: '5-12 min',
    comingSoon: true,
  },
  {
    name: 'hot-seat',
    label: 'Hot Seat',
    description: 'Architecture hot seat — defend your design choices under pressure. Claude plays devil\'s advocate on your decisions.',
    duration: '5-10 min',
    comingSoon: true,
  },
  {
    name: 'test-me',
    label: 'Test Me',
    description: 'Predict whether test cases pass or fail on your code. Claude writes tests, you predict the outcome and explain why.',
    duration: '5-8 min',
    comingSoon: true,
  },
]

interface SkillSelectorProps {
  repoFullName: string
  prNumber: number
  onSelectSkill: (skillName: string) => void
  disabled?: boolean
}

export { SKILLS }

export default function SkillSelector({
  repoFullName,
  prNumber,
  onSelectSkill,
  disabled = false,
}: SkillSelectorProps) {
  return (
    <div
      data-testid="skill-selector"
      className="min-h-screen bg-bg text-ink font-sans flex flex-col items-center justify-center px-6 py-12"
    >
      {/* Header */}
      <div className="text-center mb-10 max-w-lg">
        <h1 className="font-mono text-lg font-bold text-accent mb-2">helPRs</h1>
        <p className="text-ink2 text-sm">
          Run something on{' '}
          <span className="font-mono text-ink">{repoFullName}</span>
          <span className="text-dim">#{prNumber}</span>
        </p>
      </div>

      {/* Skill cards */}
      <div className="grid gap-3 w-full max-w-lg">
        {SKILLS.map((skill) => (
          <Card
            key={skill.name}
            hover={!skill.comingSoon}
            className={`${skill.comingSoon ? 'opacity-60' : 'cursor-pointer'}`}
          >
            <button
              data-testid={`skill-card-${skill.name}`}
              onClick={() => !skill.comingSoon && onSelectSkill(skill.name)}
              disabled={disabled || skill.comingSoon}
              className="w-full text-left disabled:cursor-not-allowed cursor-pointer"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h2 className="font-mono text-sm font-semibold text-ink">
                      {skill.label}
                    </h2>
                    {!skill.comingSoon && (
                      <Chip variant="accent">DEFAULT</Chip>
                    )}
                  </div>
                  <p className="text-ink2 text-[13px] leading-relaxed">
                    {skill.description}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  <Chip>{skill.duration}</Chip>
                  {skill.comingSoon ? (
                    <Chip variant="warn">soon</Chip>
                  ) : (
                    <span className="text-accent text-xs font-semibold font-mono">
                      Run &rarr;
                    </span>
                  )}
                </div>
              </div>
            </button>
          </Card>
        ))}
      </div>

      {/* Footer */}
      <Overline className="mt-8 text-center max-w-md">
        // skills run in ephemeral containers using your configured Claude credentials
      </Overline>
    </div>
  )
}
