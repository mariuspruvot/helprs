import { useCallback, useRef, useState } from 'react'

interface AnswerInputProps {
  disabled: boolean
  sessionCompleted?: boolean
  onSubmit: (text: string) => void
}

const MIN_HEIGHT_PX = 48
const MAX_HEIGHT_PX = 200

export default function AnswerInput({ disabled, sessionCompleted, onSubmit }: AnswerInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const resize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const next = Math.min(MAX_HEIGHT_PX, Math.max(MIN_HEIGHT_PX, el.scrollHeight))
    el.style.height = `${next}px`
  }, [])

  const handleSubmit = useCallback(() => {
    if (disabled) return
    const trimmed = value.trim()
    if (!trimmed) return
    onSubmit(trimmed)
    setValue('')
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (el) el.style.height = `${MIN_HEIGHT_PX}px`
    })
  }, [disabled, onSubmit, value])

  return (
    <form
      data-testid="answer-input-form"
      onSubmit={(e) => { e.preventDefault(); handleSubmit() }}
      className="shrink-0 w-full"
      style={{ padding: '12px 16px', background: '#1e1a1a', boxShadow: '0 -1px 0 rgba(255,255,255,0.06)' }}
    >
      <label className="sr-only" htmlFor="answer-input">Your answer</label>
      <textarea
        id="answer-input"
        ref={textareaRef}
        data-testid="answer-input-textarea"
        value={value}
        onChange={(e) => { setValue(e.target.value); resize() }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
        }}
        readOnly={disabled}
        aria-disabled={disabled}
        aria-multiline="true"
        placeholder={sessionCompleted ? 'Session complete' : disabled ? 'Generating feedback...' : 'Type your answer — Enter to send'}
        rows={1}
        style={{
          minHeight: MIN_HEIGHT_PX,
          maxHeight: MAX_HEIGHT_PX,
          resize: 'none',
          padding: 12,
          width: '100%',
          fontSize: 15,
          lineHeight: '1.6',
          fontFamily: 'var(--font-family-sans)',
          letterSpacing: '0.2px',
          backgroundColor: '#2a2626',
          color: 'var(--color-text-primary, #fdfcfc)',
          border: 'none',
          borderRadius: 10,
          boxShadow: 'rgba(255,255,255,0.06) 0 0 0 1px',
          opacity: disabled ? 0.5 : 1,
          outline: 'none',
        }}
      />
    </form>
  )
}
