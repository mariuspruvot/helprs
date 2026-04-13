/**
 * Story 4.2: inline report flag button for question messages (AC #2, #3, #6).
 *
 * Renders a small muted flag icon. On click, toggles an inline reason
 * selector. On reason selection, POSTs to the report endpoint. Shows
 * a checkmark on success, disables on duplicate (409).
 *
 * Keyboard accessible: Tab-reachable, Enter-activated (UX-DR17).
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { apiFetch } from '../../shared/api/client'
import { useSessionStore } from './store'
import type { ReportReason } from './types'

interface ReportButtonProps {
  sessionId: string
  questionNumber: number
  /** Pre-reported from a previous session (resume). */
  alreadyReported?: boolean
}

const REASONS: { value: ReportReason; label: string }[] = [
  { value: 'irrelevant', label: 'Irrelevant to the diff' },
  { value: 'factually_incorrect', label: 'Factually incorrect' },
  { value: 'ambiguous', label: 'Ambiguous wording' },
  { value: 'too_easy', label: 'Too easy / obvious' },
  { value: 'too_hard', label: 'Too hard / unfair' },
  { value: 'other', label: 'Other' },
]

export default function ReportButton({
  sessionId,
  questionNumber,
  alreadyReported = false,
}: ReportButtonProps) {
  const storeReported = useSessionStore((s) => s.reportedQuestions.includes(questionNumber))
  const markQuestionReported = useSessionStore((s) => s.markQuestionReported)
  const [reported, setReported] = useState(alreadyReported || storeReported)
  const [selectorOpen, setSelectorOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(false)
  const containerRef = useRef<HTMLSpanElement>(null)

  // Close selector on click-outside or Escape.
  useEffect(() => {
    if (!selectorOpen) return
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setSelectorOpen(false)
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectorOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [selectorOpen])

  const handleToggle = useCallback(() => {
    if (reported || submitting) return
    setSelectorOpen((prev) => !prev)
  }, [reported, submitting])

  const handleSelect = useCallback(
    async (reason: ReportReason) => {
      setSubmitting(true)
      try {
        const resp = await apiFetch(
          `/api/v1/sessions/${sessionId}/questions/${questionNumber}/report`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason }),
          },
        )
        if (resp.ok || resp.status === 409) {
          setReported(true)
          markQuestionReported(questionNumber)
          setSelectorOpen(false)
          setError(false)
        } else {
          setError(true)
          setSelectorOpen(false)
        }
      } catch {
        setError(true)
        setSelectorOpen(false)
      } finally {
        setSubmitting(false)
      }
    },
    [sessionId, questionNumber],
  )

  if (reported) {
    return (
      <span
        data-testid="report-confirmed"
        aria-label="Question reported"
        style={{ color: '#30d158', fontSize: 12 }}
      >
        ✓ Thanks for flagging
      </span>
    )
  }

  return (
    <span ref={containerRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        onClick={handleToggle}
        aria-label="Report this question"
        data-testid="report-button"
        disabled={submitting}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: '#6e6e73',
          fontSize: 14,
          padding: '2px 4px',
          lineHeight: 1,
        }}
      >
        ⚑
      </button>
      {selectorOpen && (
        <div
          role="menu"
          data-testid="report-selector"
          style={{
            position: 'absolute',
            bottom: '100%',
            right: 0,
            backgroundColor: '#2a2626',
            border: 'none',
            borderRadius: 10,
            boxShadow: 'rgba(255,255,255,0.06) 0 0 0 1px, rgba(0,0,0,0.3) 0 4px 16px',
            padding: 8,
            zIndex: 10,
            minWidth: 220,
          }}
        >
          <p
            style={{
              fontSize: 12,
              color: '#aaa',
              margin: '0 0 8px 0',
              fontWeight: 600,
            }}
          >
            Why is this question problematic?
          </p>
          {REASONS.map((r) => (
            <button
              key={r.value}
              type="button"
              role="menuitem"
              onClick={() => handleSelect(r.value)}
              data-testid={`report-reason-${r.value}`}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                background: 'none',
                border: 'none',
                color: '#ccc',
                fontSize: 13,
                padding: '6px 8px',
                borderRadius: 4,
                cursor: 'pointer',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.08)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = 'transparent'
              }}
            >
              {r.label}
            </button>
          ))}
        </div>
      )}
      {error && (
        <span data-testid="report-error" style={{ color: '#ff453a', fontSize: 11 }}>
          Failed — try again
        </span>
      )}
    </span>
  )
}
