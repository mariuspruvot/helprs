/**
 * Story 4.2: Tests for SessionFeedback component (AC #4, #5).
 */
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, describe, test, expect, vi, beforeEach } from 'vitest'

import SessionFeedback from './SessionFeedback'
import { useSessionStore } from './store'

// Mock apiFetch
vi.mock('../../shared/api/client', () => ({
  apiFetch: vi.fn(),
  API_BASE: 'http://test',
}))

import { apiFetch } from '../../shared/api/client'

const mockApiFetch = vi.mocked(apiFetch)

describe('SessionFeedback', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    mockApiFetch.mockReset()
    useSessionStore.setState({ reportedQuestions: [], feedbackSubmitted: false })
  })

  test('renders thumbs up/down buttons', () => {
    render(<SessionFeedback sessionId="s1" />)
    expect(screen.getByTestId('feedback-thumbs-up')).toBeTruthy()
    expect(screen.getByTestId('feedback-thumbs-down')).toBeTruthy()
  })

  test('shows comment field on thumbs click', () => {
    render(<SessionFeedback sessionId="s1" />)
    expect(screen.queryByTestId('feedback-comment')).toBeNull()
    fireEvent.click(screen.getByTestId('feedback-thumbs-up'))
    expect(screen.getByTestId('feedback-comment')).toBeTruthy()
    expect(screen.getByTestId('feedback-submit')).toBeTruthy()
  })

  test('submits thumbs up + comment and shows confirmation', async () => {
    mockApiFetch.mockResolvedValueOnce(new Response(null, { status: 201 }))

    render(<SessionFeedback sessionId="s1" />)
    fireEvent.click(screen.getByTestId('feedback-thumbs-up'))
    fireEvent.change(screen.getByTestId('feedback-comment'), {
      target: { value: 'Great session!' },
    })
    fireEvent.click(screen.getByTestId('feedback-submit'))

    await waitFor(() => {
      expect(screen.getByTestId('session-feedback-submitted')).toBeTruthy()
    })

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/sessions/s1/feedback',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ rating: true, comment: 'Great session!' }),
      }),
    )
  })

  test('submits thumbs down without comment', async () => {
    mockApiFetch.mockResolvedValueOnce(new Response(null, { status: 201 }))

    render(<SessionFeedback sessionId="s1" />)
    fireEvent.click(screen.getByTestId('feedback-thumbs-down'))
    fireEvent.click(screen.getByTestId('feedback-submit'))

    await waitFor(() => {
      expect(screen.getByTestId('session-feedback-submitted')).toBeTruthy()
    })

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/sessions/s1/feedback',
      expect.objectContaining({
        body: JSON.stringify({ rating: false, comment: null }),
      }),
    )
  })

  test('shows confirmation on 409 (already submitted)', async () => {
    mockApiFetch.mockResolvedValueOnce(new Response(null, { status: 409 }))

    render(<SessionFeedback sessionId="s1" />)
    fireEvent.click(screen.getByTestId('feedback-thumbs-up'))
    fireEvent.click(screen.getByTestId('feedback-submit'))

    await waitFor(() => {
      expect(screen.getByTestId('session-feedback-submitted')).toBeTruthy()
    })
  })

  test('renders submitted state when existingFeedback provided (resume)', () => {
    render(
      <SessionFeedback
        sessionId="s1"
        existingFeedback={{ rating: true, comment: 'Nice' }}
      />,
    )
    expect(screen.getByTestId('session-feedback-submitted')).toBeTruthy()
    expect(screen.queryByTestId('feedback-thumbs-up')).toBeNull()
  })

  test('submit button visible after selecting rating', () => {
    render(<SessionFeedback sessionId="s1" />)
    expect(screen.queryByTestId('feedback-submit')).toBeNull()
    fireEvent.click(screen.getByTestId('feedback-thumbs-down'))
    expect(screen.getByTestId('feedback-submit')).toBeTruthy()
  })
})
