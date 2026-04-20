interface TerminalBlockProps {
  title?: string
  children: React.ReactNode
  className?: string
}

export function TerminalBlock({ title, children, className = '' }: TerminalBlockProps) {
  return (
    <div className={`rounded-[8px] border border-rule overflow-hidden ${className}`}>
      <div className="flex items-center gap-2 px-3 py-2 bg-bg2 border-b border-rule">
        <div className="flex gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-danger/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-warn/70" />
          <span className="w-2.5 h-2.5 rounded-full bg-ok/70" />
        </div>
        {title && (
          <span className="font-mono text-[11px] text-dim2 ml-2">{title}</span>
        )}
      </div>
      <div className="bg-[#0d0b09] p-4 font-mono text-[12.5px] leading-[1.8] text-ink2 overflow-x-auto">
        {children}
      </div>
    </div>
  )
}
