/**
 * ThinkingBlock — collapsible display for Claude's internal thinking.
 * Dimmed and collapsed by default — most users won't need this.
 */

interface ThinkingBlockProps {
  text: string
}

export default function ThinkingBlock({ text }: ThinkingBlockProps) {
  return (
    <details
      className="my-2 rounded-lg border"
      style={{
        borderColor: 'rgba(255, 255, 255, 0.06)',
        background: 'rgba(255, 255, 255, 0.02)',
      }}
    >
      <summary
        className="cursor-pointer select-none px-3 py-2 text-[12px] font-mono"
        style={{ color: '#6e6e73' }}
      >
        Thinking...
      </summary>
      <div
        className="px-3 pb-3 text-[13px] leading-relaxed font-sans whitespace-pre-wrap"
        style={{ color: '#6e6e73', fontStyle: 'italic' }}
      >
        {text}
      </div>
    </details>
  )
}
