import { useCallback, useRef, useState } from 'react'

interface AnswerInputProps {
  disabled: boolean
  sessionCompleted?: boolean
  onSubmit: (text: string) => void
}

const MIN_HEIGHT_PX = 48
const MAX_HEIGHT_PX = 200

/**
 * Story 3.4: fixed-bottom auto-expanding answer input.
 *
 * UX-DR4 — Berkeley Mono (inherited from the global theme), bg-surface
 * (#302c2c) so the input visually matches the user message bubbles
 * once submitted. Enter submits, Shift+Enter inserts a newline. No
 * Send button — the AC explicitly says "Enter to submit".
 *
 * The disabled state (true while feedback is streaming) switches the
 * placeholder to "Generating feedback..." and makes the textarea
 * `readOnly` + `aria-disabled` so AT users get the same signal as
 * sighted users.
 */
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
    // Reset height to min after clearing — avoids the textarea being
    // stuck at the previous answer's expanded height for the next one.
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (el) {
        el.style.height = `${MIN_HEIGHT_PX}px`
      }
    })
  }, [disabled, onSubmit, value])

  return (
    <form
      data-testid="answer-input-form"
      onSubmit={(e) => {
        e.preventDefault()
        handleSubmit()
      }}
      className="shrink-0 w-full bg-surface"
      style={{ padding: 16 }}
    >
      <label className="sr-only" htmlFor="answer-input">
        Your answer
      </label>
      <textarea
        id="answer-input"
        ref={textareaRef}
        data-testid="answer-input-textarea"
        value={value}
        onChange={(e) => {
          setValue(e.target.value)
          resize()
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSubmit()
          }
        }}
        readOnly={disabled}
        aria-disabled={disabled}
        aria-multiline="true"
        placeholder={sessionCompleted ? 'Session complete' : disabled ? 'Generating feedback...' : 'Type your answer...'}
        rows={1}
        style={{
          minHeight: MIN_HEIGHT_PX,
          maxHeight: MAX_HEIGHT_PX,
          resize: 'none',
          padding: 12,
          width: '100%',
          fontSize: 16,
          lineHeight: '1.5',
          backgroundColor: '#302c2c',
          color: 'var(--text-primary, #f5f5f5)',
          border: '1px solid var(--border, #3a3636)',
          borderRadius: 8,
          opacity: disabled ? 0.6 : 1,
          outline: 'none',
        }}
        className="font-mono"
      />
    </form>
  )
}
