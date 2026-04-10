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
    background: 'rgba(0, 122, 255, 0.15)',
    color: '#007aff',
  },
  reviewer: {
    label: 'REVIEWING',
    background: 'rgba(255, 159, 10, 0.15)',
    color: '#ff9f0a',
  },
}

// Note: the header is intentionally `font-mono` inherited from the root.
// Do not set a font-family here. Colours come from CSS variables except
// for the exact rgba()/hex role badge tones which are load-bearing per UX.
export default function SessionHeader({ session }: SessionHeaderProps) {
  const badge = ROLE_BADGE[session.role]
  // TODO: story-3.3 — replace the second `question_count` with the real total
  // once questions are persisted. The shape of the string must remain stable
  // for screen reader users tracking `aria-live`.
  const progressLabel =
    session.question_count > 0
      ? `Question ${session.question_count} of ${session.question_count}`
      : 'Questions pending...'

  return (
    <header
      className="h-12 w-full flex items-center gap-4 px-4 border-b border-border bg-primary shrink-0"
      style={{ paddingTop: 12, paddingBottom: 12 }}
      data-testid="session-header"
    >
      <span
        className="text-[16px] font-bold text-text-primary shrink-0"
        data-testid="session-header-repo"
      >
        {session.repo_full_name}
      </span>
      <span
        className="text-[16px] font-normal text-text-secondary flex-1 min-w-0 truncate"
        title={session.pr_title}
        data-testid="session-header-pr-title"
      >
        {session.pr_title}
      </span>
      <span
        className="text-[12px] font-medium uppercase rounded shrink-0"
        style={{
          paddingLeft: 8,
          paddingRight: 8,
          paddingTop: 2,
          paddingBottom: 2,
          backgroundColor: badge.background,
          color: badge.color,
        }}
        data-testid="session-header-role-badge"
      >
        {badge.label}
      </span>
      <span
        aria-live="polite"
        className="text-[14px] font-normal text-text-secondary shrink-0"
        data-testid="session-header-progress"
      >
        {progressLabel}
      </span>
      <span
        className="text-[12px] font-normal text-text-muted shrink-0"
        data-testid="session-header-ai-disclaimer"
      >
        AI-generated content may be inaccurate
      </span>
    </header>
  )
}
