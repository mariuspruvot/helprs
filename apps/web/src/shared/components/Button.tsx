type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-bg font-semibold shadow-glow-accent hover:brightness-110 active:brightness-90',
  secondary: 'bg-card text-ink border border-rule-str hover:bg-card-hi active:bg-bg2',
  ghost: 'text-dim hover:text-ink2 hover:bg-card/50 active:bg-card',
  danger: 'text-danger bg-danger/8 border border-danger/35 hover:bg-danger/15 active:bg-danger/20',
}

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
}

export function Button({ variant = 'primary', className = '', children, ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 px-4 py-2 rounded-button font-mono text-sm font-medium transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${variantClasses[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
