import { useSessionStore } from './store'
import type { SessionResponse, SessionRole } from './types'

interface SessionHeaderProps {
  session: SessionResponse
}

interface RoleBadgeStyle {
  label: string
  background: string
  color: string
}

const ROLE_BADGE: Record<SessionRole, RoleBadgeStyle> = {
  author: {
    label: 'AUTHOR',
    background: 'rgba(226, 160, 57, 0.12)',
    color: '#E2A039',
  },
  reviewer: {
    label: 'REVIEWING',
    background: 'rgba(255, 159, 10, 0.12)',
    color: '#ff9f0a',
  },
}

export default function SessionHeader({ session }: SessionHeaderProps) {
  const badge = ROLE_BADGE[session.role]
  const completedCycles = useSessionStore((s) =>
    s.messages.filter((m) => m.kind === 'ai_feedback').length,
  )
  const progressLabel =
    session.total_questions > 0
      ? `Question ${completedCycles} of ${session.total_questions}`
      : 'Questions pending...'

  return (
    <header
      className="w-full flex items-center gap-4 px-4 shrink-0"
      style={{
        height: 48,
        background: '#1e1a1a',
        boxShadow: '0 1px 0 rgba(255,255,255,0.04)',
      }}
      data-testid="session-header"
    >
      <span
        className="text-[14px] font-bold text-text-primary shrink-0 font-mono"
        data-testid="session-header-repo"
      >
        {session.repo_full_name}
      </span>
      <span
        className="text-[14px] text-text-secondary flex-1 min-w-0 truncate"
        style={{ fontFamily: 'var(--font-family-sans)' }}
        title={session.pr_title}
        data-testid="session-header-pr-title"
      >
        {session.pr_title}
      </span>
      <span
        className="text-[11px] font-semibold uppercase shrink-0"
        style={{
          padding: '3px 10px',
          borderRadius: 9999,
          backgroundColor: badge.background,
          color: badge.color,
          letterSpacing: '0.04em',
        }}
        data-testid="session-header-role-badge"
      >
        {badge.label}
      </span>
      <span
        aria-live="polite"
        className="text-[13px] text-text-muted shrink-0"
        style={{ fontFamily: 'var(--font-family-sans)' }}
        data-testid="session-header-progress"
      >
        {progressLabel}
      </span>
      <span
        className="text-[11px] text-text-muted shrink-0 hidden lg:inline"
        style={{ opacity: 0.5, fontFamily: 'var(--font-family-sans)' }}
        data-testid="session-header-ai-disclaimer"
      >
        AI-generated content may be inaccurate
      </span>
    </header>
  )
}
