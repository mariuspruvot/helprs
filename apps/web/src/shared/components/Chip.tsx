type ChipVariant = 'default' | 'accent' | 'ok' | 'warn' | 'danger'

const variantClasses: Record<ChipVariant, string> = {
  default: 'border-rule text-dim bg-card',
  accent: 'border-accent/30 text-accent bg-accent-dim/20',
  ok: 'border-ok/30 text-ok bg-ok/10',
  warn: 'border-warn/30 text-warn bg-warn/10',
  danger: 'border-danger/30 text-danger bg-danger/10',
}

interface ChipProps {
  variant?: ChipVariant
  children: React.ReactNode
  className?: string
}

export function Chip({ variant = 'default', children, className = '' }: ChipProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-default border font-mono text-[11px] font-medium leading-tight ${variantClasses[variant]} ${className}`}
    >
      {children}
    </span>
  )
}
