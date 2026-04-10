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
  test('renders a tab per file in the parsed diff', () => {
    render(<DiffViewer session={makeSession()} />)
    expect(screen.getByTestId('diff-file-tab-0').textContent).toBe('foo.ts')
    expect(screen.getByTestId('diff-file-tab-1').textContent).toBe('bar.py')
    expect(screen.getByTestId('diff-file-tab-0').getAttribute('aria-selected')).toBe('true')
    expect(screen.getByTestId('diff-file-tab-1').getAttribute('aria-selected')).toBe('false')
  })

  test('clicking a file tab updates the store and re-renders with the new file active', () => {
    render(<DiffViewer session={makeSession()} />)
    fireEvent.click(screen.getByTestId('diff-file-tab-1'))
    expect(useSessionStore.getState().activeFileIndex).toBe(1)
    expect(screen.getByTestId('diff-file-tab-1').getAttribute('aria-selected')).toBe('true')
  })

  test('ArrowRight on a focused tab navigates to the next file', () => {
    render(<DiffViewer session={makeSession()} />)
    const firstTab = screen.getByTestId('diff-file-tab-0')
    firstTab.focus()
    fireEvent.keyDown(firstTab, { key: 'ArrowRight' })
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
    expect(warning.textContent).toContain(
      'Large PR — diff truncated at 1 MB. Story 3.5 will add file-ranked selection.',
    )
  })

  test('keeps binary files in the tab list with a placeholder body instead of silently dropping them', () => {
    // Mixed PR: one text file + one binary file. git-format binary delta
    // uses the `Binary files … and … differ` sentinel with zero hunks; the
    // old code filtered it out and the user never knew the PR had a binary
    // change. The fix keeps the tab and renders a placeholder body when
    // the binary tab is active.
    const mixedDiff = `${MULTI_FILE_DIFF}diff --git a/assets/logo.png b/assets/logo.png
index 1111111..2222222 100644
Binary files a/assets/logo.png and b/assets/logo.png differ
`
    render(<DiffViewer session={makeSession({ diff: mixedDiff })} />)

    // Both text files AND the binary file are in the tab list.
    expect(screen.getByTestId('diff-file-tab-0').textContent).toBe('foo.ts')
    expect(screen.getByTestId('diff-file-tab-1').textContent).toBe('bar.py')
    expect(screen.getByTestId('diff-file-tab-2').textContent).toBe('logo.png')

    // Clicking the binary tab surfaces the placeholder, not a crash or
    // empty state.
    fireEvent.click(screen.getByTestId('diff-file-tab-2'))
    const placeholder = screen.getByTestId('diff-binary-placeholder')
    expect(placeholder.textContent).toContain('Binary file — not displayed')
    expect(placeholder.textContent).toContain('assets/logo.png')
  })
})
