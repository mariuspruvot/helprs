interface OverlineProps {
  children: React.ReactNode
  className?: string
}

export function Overline({ children, className = '' }: OverlineProps) {
  return (
    <div
      className={`font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-dim ${className}`}
    >
      {children}
    </div>
  )
}
