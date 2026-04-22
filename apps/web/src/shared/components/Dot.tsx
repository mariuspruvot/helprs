type DotColor = 'ok' | 'warn' | 'danger' | 'accent' | 'dim'

const colorClasses: Record<DotColor, string> = {
  ok: 'bg-ok',
  warn: 'bg-warn',
  danger: 'bg-danger',
  accent: 'bg-accent',
  dim: 'bg-dim',
}

interface DotProps {
  color?: DotColor
  pulse?: boolean
  className?: string
}

export function Dot({ color = 'ok', pulse = false, className = '' }: DotProps) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${colorClasses[color]} ${pulse ? 'animate-[pulse-dot_2s_ease-in-out_infinite]' : ''} ${className}`}
    />
  )
}
