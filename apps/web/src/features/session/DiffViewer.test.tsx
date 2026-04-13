import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test } from 'vitest'
import DiffViewer from './DiffViewer'
import { useSessionStore } from './store'
import { MULTI_FILE_DIFF, makeSession, resetStores } from './__testUtils'

const TRUNCATION_MARKER = '<!-- truncated: diff exceeded 1 MB -->'

beforeEach(() => {
  resetStores()
})

afterEach(() => {
  cleanup()
})

describe('DiffViewer', () => {
  test('renders a dropdown with all files in the parsed diff', () => {
    render(<DiffViewer session={makeSession()} />)
    const select = screen.getByTestId('diff-file-select') as HTMLSelectElement
    const options = select.querySelectorAll('option')
    expect(options.length).toBe(2)
    expect(options[0].textContent).toContain('foo.ts')
    expect(options[1].textContent).toContain('bar.py')
    expect(select.value).toBe('0')
  })

  test('changing the dropdown updates the store and selects the new file', () => {
    render(<DiffViewer session={makeSession()} />)
    const select = screen.getByTestId('diff-file-select') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '1' } })
    expect(useSessionStore.getState().activeFileIndex).toBe(1)
  })

  test('next button navigates to the next file', () => {
    render(<DiffViewer session={makeSession()} />)
    const nextBtn = screen.getByLabelText('Next file')
    fireEvent.click(nextBtn)
    expect(useSessionStore.getState().activeFileIndex).toBe(1)
  })

  test('renders empty state when the diff contains no files', () => {
    render(<DiffViewer session={makeSession({ diff: '' })} />)
    expect(screen.getByText('No textual changes in this PR.')).toBeTruthy()
    expect(screen.queryByTestId('diff-file-tabs')).toBeNull()
  })

  test('renders the truncation warning when the diff contains the truncation marker', () => {
    const diffWithMarker = `${MULTI_FILE_DIFF}\n${TRUNCATION_MARKER}\n`
    render(<DiffViewer session={makeSession({ diff: diffWithMarker })} />)
    const warning = screen.getByTestId('diff-truncation-warning')
    expect(warning.textContent).toContain('Large PR')
  })

  test('keeps binary files in the dropdown with a placeholder body', () => {
    const mixedDiff = `${MULTI_FILE_DIFF}diff --git a/assets/logo.png b/assets/logo.png
index 1111111..2222222 100644
Binary files a/assets/logo.png and b/assets/logo.png differ
`
    render(<DiffViewer session={makeSession({ diff: mixedDiff })} />)

    const select = screen.getByTestId('diff-file-select') as HTMLSelectElement
    const options = select.querySelectorAll('option')
    expect(options.length).toBe(3)
    expect(options[2].textContent).toContain('logo.png')

    // Select the binary file via dropdown
    fireEvent.change(select, { target: { value: '2' } })
    const placeholder = screen.getByTestId('diff-binary-placeholder')
    expect(placeholder.textContent).toContain('Binary file — not displayed')
    expect(placeholder.textContent).toContain('assets/logo.png')
  })
})
