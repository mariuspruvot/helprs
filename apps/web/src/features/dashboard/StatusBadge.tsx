/**
 * StatusBadge — session status indicator using the Chip component.
 */

import { Chip } from '../../shared/components'

type ChipVariant = 'default' | 'accent' | 'ok' | 'warn' | 'danger'

const STATUS_VARIANTS: Record<string, ChipVariant> = {
  running: 'ok',
  starting: 'ok',
  pending: 'warn',
  completed: 'accent',
  failed: 'danger',
  timeout: 'default',
  stopped: 'default',
}

interface StatusBadgeProps {
  status: string
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const variant = STATUS_VARIANTS[status] ?? 'default'
  return <Chip variant={variant}>{status}</Chip>
}
