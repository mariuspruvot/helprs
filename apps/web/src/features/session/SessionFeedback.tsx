/**
 * Story 4.2: post-session feedback below the ScoreCard (AC #4, #5).
 *
 * Shows thumbs up/down buttons + optional comment textarea.
 * On submit, POSTs to the feedback endpoint. Shows confirmation
 * and disables on success. On resume (COMPLETED session with existing
 * feedback), shows the submitted state.
 */

import { useCallback, useState } from 'react'

import { apiFetch } from '../../shared/api/client'
import { useSessionStore } from './store'

interface SessionFeedbackProps {
  sessionId: string
  /** Pre-submitted feedback from session response (resume). */
  existingFeedback?: { rating: boolean; comment: string | null } | null
}

export default function SessionFeedback({
  sessionId,
  existingFeedback,
}: SessionFeedbackProps) {
  const storeFeedbackSubmitted = useSessionStore((s) => s.feedbackSubmitted)
  const markFeedbackSubmitted = useSessionStore((s) => s.markFeedbackSubmitted)
  const [submitted, setSubmitted] = useState(existingFeedback != null || storeFeedbackSubmitted)
  const [selectedRating, setSelectedRating] = useState<boolean | null>(
    existingFeedback?.rating ?? null,
  )
  const [comment, setComment] = useState(existingFeedback?.comment ?? '')
  const [showComment, setShowComment] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(false)

  const handleThumbClick = useCallback((rating: boolean) => {
    setSelectedRating(rating)
    setShowComment(true)
  }, [])

  const handleSubmit = useCallback(async () => {
    if (selectedRating === null || submitting) return
    setSubmitting(true)
    try {
      const resp = await apiFetch(`/api/v1/sessions/${sessionId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rating: selectedRating,
          comment: comment.trim() || null,
        }),
      })
      if (resp.ok || resp.status === 409) {
        setSubmitted(true)
        markFeedbackSubmitted()
        setError(false)
      } else {
        setError(true)
      }
    } catch {
      setError(true)
    } finally {
      setSubmitting(false)
    }
  }, [sessionId, selectedRating, comment, submitting])

  if (submitted) {
    return (
      <div
        data-testid="session-feedback-submitted"
        style={{
          marginTop: 16,
          padding: 16,
          borderRadius: 8,
          backgroundColor: '#252121',
          boxShadow: 'rgba(255,255,255,0.05) 0 0 0 1px',
          textAlign: 'center',
        }}
      >
        <span style={{ color: '#30d158', fontSize: 14 }}>
          Thanks for your feedback!
        </span>
      </div>
    )
  }

  return (
    <div
      data-testid="session-feedback"
      style={{
        marginTop: 16,
        padding: 16,
        borderRadius: 8,
        backgroundColor: '#201d1d',
      }}
    >
      <p
        style={{
          fontSize: 13,
          color: '#aaa',
          margin: '0 0 12px 0',
        }}
      >
        How was this session?
      </p>
      <div style={{ display: 'flex', gap: 12, marginBottom: showComment ? 12 : 0 }}>
        <button
          type="button"
          onClick={() => handleThumbClick(true)}
          disabled={submitting}
          aria-label="Thumbs up"
          data-testid="feedback-thumbs-up"
          style={{
            background: selectedRating === true ? 'rgba(48, 209, 88, 0.2)' : 'none',
            border: selectedRating === true ? '1px solid #30d158' : '1px solid rgba(255,255,255,0.08)',
            borderRadius: 8,
            padding: '8px 16px',
            cursor: 'pointer',
            color: '#6e6e73',
            fontSize: 20,
          }}
        >
          👍
        </button>
        <button
          type="button"
          onClick={() => handleThumbClick(false)}
          disabled={submitting}
          aria-label="Thumbs down"
          data-testid="feedback-thumbs-down"
          style={{
            background: selectedRating === false ? 'rgba(255, 59, 48, 0.2)' : 'none',
            border: selectedRating === false ? '1px solid #ff3b30' : '1px solid rgba(255,255,255,0.08)',
            borderRadius: 8,
            padding: '8px 16px',
            cursor: 'pointer',
            color: '#6e6e73',
            fontSize: 20,
          }}
        >
          👎
        </button>
      </div>
      {showComment && (
        <>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Any additional thoughts? (optional)"
            maxLength={2000}
            data-testid="feedback-comment"
            style={{
              width: '100%',
              minHeight: 60,
              backgroundColor: '#1e1a1a',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 8,
              padding: 8,
              color: '#ccc',
              fontSize: 13,
              resize: 'vertical',
              marginBottom: 8,
            }}
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            data-testid="feedback-submit"
            style={{
              background: '#E2A039',
            color: '#1a1400',
              border: 'none',
              borderRadius: 8,
              padding: '8px 16px',
              color: '#fff',
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            {submitting ? 'Sending...' : 'Send feedback'}
          </button>
          {error && (
            <span data-testid="feedback-error" style={{ color: '#ff453a', fontSize: 12, marginLeft: 8 }}>
              Something went wrong — please try again.
            </span>
          )}
        </>
      )}
    </div>
  )
}
