import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'
import AnswerInput from './AnswerInput'

afterEach(() => {
  cleanup()
})

describe('AnswerInput', () => {
  test('renders with default placeholder when enabled', () => {
    render(<AnswerInput disabled={false} onSubmit={vi.fn()} />)
    const ta = screen.getByTestId('answer-input-textarea') as HTMLTextAreaElement
    expect(ta.placeholder).toContain('Type your answer')
    expect(ta.readOnly).toBe(false)
    expect(ta.getAttribute('aria-disabled')).toBe('false')
  })

  test('Enter submits the trimmed text', () => {
    const onSubmit = vi.fn()
    render(<AnswerInput disabled={false} onSubmit={onSubmit} />)
    const ta = screen.getByTestId('answer-input-textarea') as HTMLTextAreaElement

    fireEvent.change(ta, { target: { value: '  hello world  ' } })
    fireEvent.keyDown(ta, { key: 'Enter', shiftKey: false })

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith('hello world')
    expect(ta.value).toBe('')
  })

  test('Shift+Enter does NOT submit (newline insertion is browser default)', () => {
    const onSubmit = vi.fn()
    render(<AnswerInput disabled={false} onSubmit={onSubmit} />)
    const ta = screen.getByTestId('answer-input-textarea') as HTMLTextAreaElement

    fireEvent.change(ta, { target: { value: 'first' } })
    fireEvent.keyDown(ta, { key: 'Enter', shiftKey: true })
    // jsdom does not implement the textarea-Enter native behavior, so
    // we cannot assert the actual newline insertion. We assert that
    // submit did NOT fire — that's the load-bearing behavior.
    expect(onSubmit).not.toHaveBeenCalled()
  })

  test('empty submit is a silent no-op', () => {
    const onSubmit = vi.fn()
    render(<AnswerInput disabled={false} onSubmit={onSubmit} />)
    const ta = screen.getByTestId('answer-input-textarea') as HTMLTextAreaElement
    fireEvent.keyDown(ta, { key: 'Enter' })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  test('whitespace-only submit is a silent no-op', () => {
    const onSubmit = vi.fn()
    render(<AnswerInput disabled={false} onSubmit={onSubmit} />)
    const ta = screen.getByTestId('answer-input-textarea') as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: '   ' } })
    fireEvent.keyDown(ta, { key: 'Enter' })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  test('disabled state shows loading placeholder, is readOnly, and refuses submits', () => {
    const onSubmit = vi.fn()
    render(<AnswerInput disabled={true} onSubmit={onSubmit} />)
    const ta = screen.getByTestId('answer-input-textarea') as HTMLTextAreaElement
    expect(ta.placeholder).toBe('Generating feedback...')
    expect(ta.readOnly).toBe(true)
    expect(ta.getAttribute('aria-disabled')).toBe('true')

    fireEvent.keyDown(ta, { key: 'Enter' })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  test('sr-only label is present for screen readers', () => {
    const { container } = render(<AnswerInput disabled={false} onSubmit={vi.fn()} />)
    const label = container.querySelector('label[for="answer-input"]')
    expect(label).not.toBeNull()
    expect(label?.className).toContain('sr-only')
  })

  test('form submission is also handled (defensive)', () => {
    const onSubmit = vi.fn()
    render(<AnswerInput disabled={false} onSubmit={onSubmit} />)
    const ta = screen.getByTestId('answer-input-textarea') as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: 'submitted via form' } })
    fireEvent.submit(screen.getByTestId('answer-input-form'))
    expect(onSubmit).toHaveBeenCalledWith('submitted via form')
  })
})
