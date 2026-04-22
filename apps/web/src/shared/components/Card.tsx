interface CardProps {
  children: React.ReactNode
  className?: string
  hover?: boolean
}

export function Card({ children, className = '', hover = false }: CardProps) {
  return (
    <div
      className={`bg-card border border-rule rounded-card p-5 ${hover ? 'transition-colors hover:bg-card-hi hover:border-rule-str' : ''} ${className}`}
    >
      {children}
    </div>
  )
}
