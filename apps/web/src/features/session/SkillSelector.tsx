/**
 * SkillSelector — displays available skills as cards with a Run button.
 *
 * Hardcoded skill list for now (will be dynamic later).
 */

import type { Skill } from './containerTypes'

const SKILLS: Skill[] = [
  {
    name: 'challenge-me',
    label: 'Challenge Me',
    description: 'Socratic quiz -- tests your understanding of your own PR changes',
    duration: '5-10 min',
  },
  {
    name: 'code-review',
    label: 'Code Review',
    description: 'Multi-layer adversarial code review',
    duration: '3-5 min',
    comingSoon: true,
  },
  {
    name: 'security-audit',
    label: 'Security Audit',
    description: 'Vulnerability scan on your diff',
    duration: '1-3 min',
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
      className="min-h-screen bg-primary text-text-primary font-sans flex flex-col items-center justify-center px-6"
    >
      {/* Header */}
      <div className="text-center mb-10 max-w-lg">
        <h1 className="font-mono text-[24px] font-bold mb-2">
          <span style={{ color: '#E2A039' }}>helPRs</span>
        </h1>
        <p className="text-text-secondary text-[14px]">
          <span className="font-mono text-text-primary">{repoFullName}</span>
          {' '}
          <span className="text-text-muted">#{prNumber}</span>
        </p>
        <p className="text-text-muted text-[13px] mt-2">Select a skill to run against this PR</p>
      </div>

      {/* Skill cards */}
      <div className="grid gap-4 w-full max-w-lg">
        {SKILLS.map((skill) => (
          <button
            key={skill.name}
            data-testid={`skill-card-${skill.name}`}
            onClick={() => !skill.comingSoon && onSelectSkill(skill.name)}
            disabled={disabled || skill.comingSoon}
            className="text-left p-5 rounded-[10px] transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: '#1a1717',
              boxShadow: '0 0 0 1px rgba(255, 255, 255, 0.06), 0 2px 4px rgba(0, 0, 0, 0.2), 0 8px 24px -8px rgba(0, 0, 0, 0.3)',
            }}
            onMouseEnter={(e) => {
              if (!disabled) {
                e.currentTarget.style.boxShadow = '0 0 0 1px rgba(226, 160, 57, 0.3), 0 4px 12px rgba(0, 0, 0, 0.3), 0 16px 48px -12px rgba(0, 0, 0, 0.4)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = '0 0 0 1px rgba(255, 255, 255, 0.06), 0 2px 4px rgba(0, 0, 0, 0.2), 0 8px 24px -8px rgba(0, 0, 0, 0.3)'
            }}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <h2 className="font-mono text-[15px] font-medium text-text-primary mb-1">
                  {skill.label}
                </h2>
                <p className="text-text-secondary text-[13px] leading-relaxed">
                  {skill.description}
                </p>
              </div>
              <div className="flex flex-col items-end gap-2 shrink-0">
                <span
                  className="text-[11px] font-mono px-2 py-0.5 rounded-full"
                  style={{
                    color: 'rgba(255, 255, 255, 0.5)',
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                  }}
                >
                  {skill.duration}
                </span>
                {skill.comingSoon ? (
                  <span
                    className="text-[11px] font-mono px-2 py-0.5 rounded-full"
                    style={{
                      color: 'rgba(226, 160, 57, 0.7)',
                      background: 'rgba(226, 160, 57, 0.08)',
                      border: '1px solid rgba(226, 160, 57, 0.15)',
                    }}
                  >
                    Coming soon
                  </span>
                ) : (
                  <span
                    className="text-[12px] font-semibold font-mono"
                    style={{ color: '#E2A039' }}
                  >
                    Run &rarr;
                  </span>
                )}
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Footer disclaimer */}
      <p className="text-text-muted text-[11px] mt-8 text-center max-w-md">
        Skills run in ephemeral containers using your configured Claude credentials.
        AI-generated content may be inaccurate -- verify important findings.
      </p>
    </div>
  )
}
