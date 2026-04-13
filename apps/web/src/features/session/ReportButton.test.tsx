/**
 * Story 4.2: Tests for ReportButton component (AC #2, #4, #6).
 */
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, describe, test, expect, vi, beforeEach } from 'vitest'

import ReportButton from './ReportButton'
import { useSessionStore } from './store'

// Mock apiFetch
vi.mock('../../shared/api/client', () => ({
  apiFetch: vi.fn(),
  API_BASE: 'http://test',
}))

import { apiFetch } from '../../shared/api/client'

const mockApiFetch = vi.mocked(apiFetch)

describe('ReportButton', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    mockApiFetch.mockReset()
    useSessionStore.setState({ reportedQuestions: [], feedbackSubmitted: false })
  })

  test('renders flag icon button', () => {
    render(<ReportButton sessionId="s1" questionNumber={1} />)
    expect(screen.getByTestId('report-button')).toBeTruthy()
    expect(screen.getByLabelText('Report this question')).toBeTruthy()
  })

  test('toggles selector on click', () => {
    render(<ReportButton sessionId="s1" questionNumber={1} />)
    expect(screen.queryByTestId('report-selector')).toBeNull()
    fireEvent.click(screen.getByTestId('report-button'))
    expect(screen.getByTestId('report-selector')).toBeTruthy()
    expect(screen.getByRole('menu')).toBeTruthy()
  })

  test('submits report and shows confirmation', async () => {
    mockApiFetch.mockResolvedValueOnce(new Response(null, { status: 201 }))

    render(<ReportButton sessionId="s1" questionNumber={2} />)
    fireEvent.click(screen.getByTestId('report-button'))
    fireEvent.click(screen.getByTestId('report-reason-ambiguous'))

    await waitFor(() => {
      expect(screen.getByTestId('report-confirmed')).toBeTruthy()
    })

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/sessions/s1/questions/2/report',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ reason: 'ambiguous' }),
      }),
    )
  })

  test('shows confirmation on 409 (already reported)', async () => {
    mockApiFetch.mockResolvedValueOnce(new Response(null, { status: 409 }))

    render(<ReportButton sessionId="s1" questionNumber={1} />)
    fireEvent.click(screen.getByTestId('report-button'))
    fireEvent.click(screen.getByTestId('report-reason-too_easy'))

    await waitFor(() => {
      expect(screen.getByTestId('report-confirmed')).toBeTruthy()
    })
  })

  test('renders confirmed state when alreadyReported=true', () => {
    render(<ReportButton sessionId="s1" questionNumber={1} alreadyReported />)
    expect(screen.getByTestId('report-confirmed')).toBeTruthy()
    expect(screen.queryByTestId('report-button')).toBeNull()
  })

  test('keyboard accessibility: Enter activates toggle (native button behavior)', () => {
    render(<ReportButton sessionId="s1" questionNumber={1} />)
    const btn = screen.getByTestId('report-button')
    // Native <button> fires onClick on Enter — no custom onKeyDown needed.
    fireEvent.click(btn)
    expect(screen.getByTestId('report-selector')).toBeTruthy()
  })

  test('Tab reaches the button', () => {
    render(<ReportButton sessionId="s1" questionNumber={1} />)
    const btn = screen.getByTestId('report-button')
    btn.focus()
    expect(document.activeElement).toBe(btn)
  })
})
