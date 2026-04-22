interface GrainOverlayProps {
  className?: string
}

export function GrainOverlay({ className = '' }: GrainOverlayProps) {
  return (
    <div
      className={`pointer-events-none absolute inset-0 opacity-40 ${className}`}
      style={{
        background: [
          'radial-gradient(ellipse at 15% 0%, rgba(232, 163, 71, 0.05), transparent 60%)',
          'radial-gradient(ellipse at 85% 100%, rgba(232, 163, 71, 0.03), transparent 55%)',
        ].join(', '),
      }}
    />
  )
}
