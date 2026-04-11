import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { createRef } from 'react'
import DiffViewer, { type DiffViewerHandle } from './DiffViewer'
import { useSessionStore } from './store'
import { makeSession, resetStores } from './__testUtils'

beforeEach(() => {
  resetStores()
  // jsdom doesn't implement scrollIntoView — provide a spyable shim.
  ;(Element.prototype as unknown as { scrollIntoView: (...args: unknown[]) => void }).scrollIntoView =
    vi.fn()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// jsdom's requestAnimationFrame fires on the next macrotask. Wait for
// it to flush so the post-rAF DOM mutations the imperative handle does
// land before our assertions run.
async function flushRaf(): Promise<void> {
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
}

describe('DiffViewer.scrollTo (Story 3.4 imperative API)', () => {
  test('scrollTo on the active file finds the row and calls scrollIntoView', async () => {
    const ref = createRef<DiffViewerHandle>()
    render(<DiffViewer ref={ref} session={makeSession()} />)
    // foo.ts is the active file by default — the multi-file diff fixture
    // renders line numbers 1, 2, 3 in the new column. Pick line 2.
    ref.current?.scrollTo('foo.ts', 2)
    await flushRaf()
    // The TR with id helprs-line-new-2 should have received a
    // scrollIntoView call.
    const row = document.getElementById('helprs-line-new-2')
    expect(row).not.toBeNull()
    expect(row?.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ block: 'center' }),
    )
    expect(row?.classList.contains('diff-line-highlight')).toBe(true)
  })

  test('scrollTo on a different file triggers the active-file highlight', () => {
    const ref = createRef<DiffViewerHandle>()
    render(<DiffViewer ref={ref} session={makeSession()} />)
    expect(useSessionStore.getState().activeFileIndex).toBe(0)
    ref.current?.scrollTo('bar.py', 2)
    expect(useSessionStore.getState().activeFileIndex).toBe(1)
    // highlightActiveFile bumps the trigger counter for the tab flash.
    expect(useSessionStore.getState().highlightFileTrigger).toBeGreaterThan(0)
  })

  test('scrollTo on an unknown file logs a warning and is a no-op', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const ref = createRef<DiffViewerHandle>()
    render(<DiffViewer ref={ref} session={makeSession()} />)
    ref.current?.scrollTo('does-not-exist.ts', 1)
    expect(warn).toHaveBeenCalled()
    // Active file unchanged.
    expect(useSessionStore.getState().activeFileIndex).toBe(0)
  })

  test('scrollTo on a missing line logs a warning and does not throw', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const ref = createRef<DiffViewerHandle>()
    render(<DiffViewer ref={ref} session={makeSession()} />)
    ref.current?.scrollTo('foo.ts', 9999)
    expect(warn).toHaveBeenCalled()
  })

  test('preview adds the diff-line-preview class without scrolling', () => {
    const ref = createRef<DiffViewerHandle>()
    render(<DiffViewer ref={ref} session={makeSession()} />)
    ref.current?.preview('foo.ts', 1)
    const row = document.getElementById('helprs-line-new-1')
    expect(row?.classList.contains('diff-line-preview')).toBe(true)
    // No scroll on preview.
    expect(row?.scrollIntoView).not.toHaveBeenCalled()
    // Clearing removes the class.
    ref.current?.clearPreview()
    expect(row?.classList.contains('diff-line-preview')).toBe(false)
  })

  // Story 3.4 P17 (code-review A22): AC#16 requires a reduced-motion
  // assertion that scrollIntoView is called with `behavior: 'instant'`.
  test('scrollTo passes behavior: instant when prefers-reduced-motion is set', async () => {
    window.matchMedia = vi.fn().mockImplementation(() => ({
      matches: true,
      media: '(prefers-reduced-motion: reduce)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
    const ref = createRef<DiffViewerHandle>()
    render(<DiffViewer ref={ref} session={makeSession()} />)
    ref.current?.scrollTo('foo.ts', 2)
    await flushRaf()
    const row = document.getElementById('helprs-line-new-2')
    expect(row?.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ behavior: 'instant' }),
    )
  })
})
