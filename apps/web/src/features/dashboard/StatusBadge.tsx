/**
 * StatusBadge — reusable status indicator for sessions.
 */

const STATUS_STYLES: Record<string, { color: string; bg: string }> = {
  running: { color: '#30d158', bg: 'rgba(48, 209, 88, 0.1)' },
  starting: { color: '#30d158', bg: 'rgba(48, 209, 88, 0.1)' },
  pending: { color: '#ff9f0a', bg: 'rgba(255, 159, 10, 0.1)' },
  completed: { color: '#E2A039', bg: 'rgba(226, 160, 57, 0.1)' },
  failed: { color: '#ff3b30', bg: 'rgba(255, 59, 48, 0.1)' },
  timeout: { color: '#9a9898', bg: 'rgba(154, 152, 152, 0.1)' },
  stopped: { color: '#9a9898', bg: 'rgba(154, 152, 152, 0.1)' },
}

interface StatusBadgeProps {
  status: string
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.stopped
  return (
    <span
      className="text-[11px] px-2 py-0.5 rounded-full font-medium font-mono"
      style={{ color: style.color, background: style.bg }}
    >
      {status}
    </span>
  )
}
