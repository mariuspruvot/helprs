interface StatCardProps {
  label: string
  value: string | number
  sub?: string
  color?: 'ink' | 'accent' | 'ok' | 'warn' | 'danger'
  className?: string
}

const colorClasses: Record<string, string> = {
  ink: 'text-ink',
  accent: 'text-accent',
  ok: 'text-ok',
  warn: 'text-warn',
  danger: 'text-danger',
}

export function StatCard({ label, value, sub, color = 'ink', className = '' }: StatCardProps) {
  return (
    <div className={`bg-card border border-rule rounded-card p-4 ${className}`}>
      <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-dim">
        {label}
      </div>
      <div className={`font-mono text-[28px] font-bold leading-tight mt-1 ${colorClasses[color]}`}>
        {value}
      </div>
      {sub && (
        <div className="font-mono text-[11px] text-dim mt-1">{sub}</div>
      )}
    </div>
  )
}
