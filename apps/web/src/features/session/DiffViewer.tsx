import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  Diff,
  Hunk,
  computeNewLineNumber,
  computeOldLineNumber,
  parseDiff,
  tokenize,
} from 'react-diff-view'
import type { ChangeData, FileData, HunkTokens } from 'react-diff-view'
// Library CSS is imported in `main.tsx` BEFORE `index.css` so our
// dark-mode `--diff-*` overrides win the cascade. Do not import it here
// — it would re-import after `index.css` and revert the overrides.
import { useReducedMotion } from '../../shared/hooks/useReducedMotion'
import { useDiffViewerHandleRefSlot } from './codeLinkContext'
import { useSessionStore } from './store'
import { languageFromPath, refractorAdapter } from './refractorSetup'
import type { SessionResponse } from './types'

// AC #11 (story 3.3): how long the active file tab stays highlighted
// after a question commit cites its file. The CSS transition is half
// of this so the fade-in + fade-out are both visible.
const FILE_HIGHLIGHT_DURATION_MS = 600
const FILE_HIGHLIGHT_TRANSITION_MS = 300
const FILE_HIGHLIGHT_COLOR = '#007aff'

// Story 3.4 (AC #12): how long a clicked code-link's row stays
// highlighted with the accent overlay before fading.
const LINE_HIGHLIGHT_DURATION_MS = 1500

interface DiffViewerProps {
  session: SessionResponse
}

/**
 * Story 3.4: imperative API exposed via `forwardRef` so the chat
 * panel's CodeLink buttons can drive a scroll + highlight on the
 * diff side without prop-drilling DOM refs.
 */
export interface DiffViewerHandle {
  /** Switch to ``file`` and scroll its line into view + flash a highlight. */
  scrollTo: (file: string, line: number) => void
  /** Apply a subtle hover preview on ``file:line`` (no scroll). */
  preview: (file: string, line: number) => void
  /** Clear any active hover preview. */
  clearPreview: () => void
}

const TRUNCATION_MARKER = '<!-- truncated: diff exceeded 1 MB -->'

function fileDisplayPath(file: FileData): string {
  return file.newPath && file.newPath !== '/dev/null' ? file.newPath : file.oldPath
}

function fileBasename(file: FileData): string {
  const fullPath = fileDisplayPath(file)
  return fullPath.split('/').pop() || fullPath
}

function hasRealPath(file: FileData): boolean {
  const newPath = file.newPath && file.newPath !== '/dev/null' ? file.newPath : ''
  const oldPath = file.oldPath && file.oldPath !== '/dev/null' ? file.oldPath : ''
  return newPath !== '' || oldPath !== ''
}

function isBinaryFile(file: FileData): boolean {
  return (
    file.hunks.length === 0 &&
    hasRealPath(file) &&
    file.type !== 'rename' &&
    file.type !== 'copy'
  )
}

/**
 * Story 3.4: stable per-row anchor id used by ``scrollTo``.
 *
 * For unified diffs we prefer the NEW line number (which is what the
 * LLM most often cites), falling back to the OLD line number for
 * delete changes that have no new-side mapping. The id is namespaced
 * with ``helprs-line-`` so it cannot collide with any consumer-set
 * anchor.
 */
function makeAnchorID(change: ChangeData): string {
  const newLine = computeNewLineNumber(change)
  if (newLine > 0) {
    return `helprs-line-new-${newLine}`
  }
  const oldLine = computeOldLineNumber(change)
  if (oldLine > 0) {
    return `helprs-line-old-${oldLine}`
  }
  return ''
}

const DiffViewer = forwardRef<DiffViewerHandle, DiffViewerProps>(function DiffViewer(
  { session },
  ref,
) {
  const activeFileIndex = useSessionStore((s) => s.activeFileIndex)
  const setActiveFile = useSessionStore((s) => s.setActiveFile)
  const highlightActiveFile = useSessionStore((s) => s.highlightActiveFile)
  const highlightFileTrigger = useSessionStore((s) => s.highlightFileTrigger)
  const [isHighlighted, setIsHighlighted] = useState(false)
  const reducedMotion = useReducedMotion()

  // AC #11: fires a short-lived highlight on the active file tab
  // every time ``highlightFileTrigger`` ticks (ChatPanel calls
  // ``highlightActiveFile`` on question commit). Keyboard nav /
  // click nav use ``setActiveFile`` which does NOT tick the trigger,
  // so this only fires for commit-driven highlights.
  useEffect(() => {
    if (highlightFileTrigger === 0) return
    setIsHighlighted(true)
    const id = setTimeout(() => setIsHighlighted(false), FILE_HIGHLIGHT_DURATION_MS)
    return () => clearTimeout(id)
  }, [highlightFileTrigger])

  // parseDiff always returns at least one file even for empty/garbage input
  // (empty path, zero hunks). Treat such empty placeholders as "no changes"
  // so the user sees the empty state instead of an empty tab bar — but
  // KEEP binary entries (zero hunks + real path + non-rename/copy) so a PR
  // that only changes images / lockfiles is still discoverable from the tab
  // list, with a "Binary file — not displayed" placeholder in the panel
  // body. Pure renames and copies are dropped from the tab list (they have
  // no content to show anyway).
  const files = useMemo<FileData[]>(() => {
    const parsed = parseDiff(session.diff)
    return parsed.filter((file) => file.hunks.length > 0 || isBinaryFile(file))
  }, [session.diff])
  // Anchor the check to the end of the diff — `includes()` would false-positive
  // on any file whose contents legitimately contain the marker comment (e.g.
  // a test fixture that round-trips this exact string).
  const isTruncated = useMemo(
    () => session.diff.trimEnd().endsWith(TRUNCATION_MARKER),
    [session.diff],
  )

  const safeIndex = Math.min(Math.max(0, activeFileIndex), Math.max(0, files.length - 1))
  const activeFile = files[safeIndex]

  // Syntax highlighting — lazy per active file. If language is unknown we
  // skip tokenization so unknown extensions still render as plain text.
  const tokens = useMemo<HunkTokens | null>(() => {
    if (!activeFile) return null
    const language = languageFromPath(fileDisplayPath(activeFile))
    if (!language) return null
    try {
      return tokenize(activeFile.hunks, {
        highlight: true,
        refractor: refractorAdapter,
        language,
      })
    } catch (err) {
      console.warn('[DiffViewer] syntax highlighting disabled — falling back to plain text', err)
      return null
    }
  }, [activeFile])

  const scrollContainerRef = useRef<HTMLDivElement>(null)
  // Track timeouts so a rapid second scrollTo cancels the first highlight
  // before its 1.5 s timer expires.
  const highlightTimeoutRef = useRef<number | null>(null)
  const previewedRowRef = useRef<HTMLElement | null>(null)

  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])

  // Trim stale ref slots when the file count shrinks (e.g. navigating to a
  // session with fewer files). Without this the array keeps pointing at
  // detached DOM nodes and `focus()` can target a dead ref.
  useEffect(() => {
    tabRefs.current.length = files.length
  }, [files.length])

  // Keep keyboard focus synced with the active tab when the store changes.
  useEffect(() => {
    if (document.activeElement?.getAttribute('role') === 'tab') {
      tabRefs.current[safeIndex]?.focus()
    }
  }, [safeIndex])

  // Story 3.4 (AC #12): imperative scroll-to-line + hover preview API.
  // Built once via useMemo so the same object can be:
  //   1. exposed via useImperativeHandle for the forwardRef caller
  //   2. registered in the optional CodeLinkActions context slot so
  //      CodeLink buttons elsewhere in the tree can dispatch to it
  //      without prop drilling
  const handleRefSlot = useDiffViewerHandleRefSlot()
  const handle = useMemo<DiffViewerHandle>(
    () => ({
      scrollTo: (file, line) => {
        const targetIndex = files.findIndex((f) => fileDisplayPath(f) === file)
        if (targetIndex === -1) {
          console.warn(`[DiffViewer] scrollTo: file not in diff: ${file}`)
          return
        }
        if (targetIndex !== safeIndex) {
          // Tab switch + flash so the user notices the change.
          highlightActiveFile(targetIndex)
        }
        // Story 3.4 P6 (code-review E12+E13):
        //   * Look up the row via ``scrollContainerRef.current.querySelector``
        //     (scoped) rather than ``document.getElementById`` so two
        //     DiffViewer instances in the same DOM (StrictMode double-mount
        //     or parallel layouts during a viewport transition) don't
        //     collide on the same anchor id.
        //   * Retry across up to 3 rAFs to give react-diff-view time to
        //     render the newly-activated file's hunks. A single rAF
        //     can lose the race on large diffs under React 18 concurrent
        //     scheduling.
        const newSelector = `#helprs-line-new-${line}`
        const oldSelector = `#helprs-line-old-${line}`

        let attempts = 0
        const MAX_ATTEMPTS = 3
        const tryLocate = () => {
          const container = scrollContainerRef.current
          if (!container) return
          const row =
            (container.querySelector(newSelector) as HTMLElement | null) ??
            (container.querySelector(oldSelector) as HTMLElement | null)
          if (!row) {
            attempts += 1
            if (attempts < MAX_ATTEMPTS) {
              requestAnimationFrame(tryLocate)
              return
            }
            console.warn(`[DiffViewer] scrollTo: line ${line} not found in ${file}`)
            return
          }
          row.scrollIntoView({
            behavior: reducedMotion ? 'instant' : 'smooth',
            block: 'center',
          })
          row.classList.add('diff-line-highlight')
          if (highlightTimeoutRef.current !== null) {
            window.clearTimeout(highlightTimeoutRef.current)
          }
          highlightTimeoutRef.current = window.setTimeout(() => {
            row.classList.remove('diff-line-highlight')
            highlightTimeoutRef.current = null
          }, LINE_HIGHLIGHT_DURATION_MS)
        }
        requestAnimationFrame(tryLocate)
      },
      preview: (file, line) => {
        const targetIndex = files.findIndex((f) => fileDisplayPath(f) === file)
        if (targetIndex === -1 || targetIndex !== safeIndex) {
          // Only preview rows visible in the current file — switching
          // tabs on hover would be jarring.
          return
        }
        const container = scrollContainerRef.current
        if (!container) return
        const newSelector = `#helprs-line-new-${line}`
        const oldSelector = `#helprs-line-old-${line}`
        const row =
          (container.querySelector(newSelector) as HTMLElement | null) ??
          (container.querySelector(oldSelector) as HTMLElement | null)
        if (!row) return
        if (previewedRowRef.current && previewedRowRef.current !== row) {
          previewedRowRef.current.classList.remove('diff-line-preview')
        }
        row.classList.add('diff-line-preview')
        previewedRowRef.current = row
      },
      clearPreview: () => {
        if (previewedRowRef.current) {
          previewedRowRef.current.classList.remove('diff-line-preview')
          previewedRowRef.current = null
        }
      },
    }),
    [files, safeIndex, highlightActiveFile, reducedMotion],
  )

  useImperativeHandle(ref, () => handle, [handle])

  // Register the imperative handle into the optional context slot so
  // CodeLink buttons elsewhere in the tree can dispatch to it. The
  // ref slot is null when DiffViewer is rendered outside a
  // DiffViewerHandleRefContext.Provider (e.g. unit tests), in which
  // case the registration is a no-op.
  useEffect(() => {
    if (!handleRefSlot) return
    handleRefSlot.current = handle
    return () => {
      if (handleRefSlot.current === handle) {
        handleRefSlot.current = null
      }
    }
  }, [handleRefSlot, handle])

  const onTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return
    event.preventDefault()
    const delta = event.key === 'ArrowLeft' ? -1 : 1
    const next = (safeIndex + delta + files.length) % files.length
    setActiveFile(next)
  }

  if (files.length === 0) {
    return (
      <div
        className="h-full w-full bg-surface flex items-center justify-center"
        data-testid="diff-viewer"
      >
        <p className="text-[14px] text-text-muted">No textual changes in this PR.</p>
      </div>
    )
  }

  return (
    <div
      className="h-full w-full bg-surface flex flex-col text-text-primary"
      data-testid="diff-viewer"
    >
      {isTruncated && (
        <div
          className="px-3 py-1 border-b border-border text-[12px] text-warning bg-surface shrink-0"
          data-testid="diff-truncation-warning"
        >
          Large PR — diff truncated at 1 MB. Story 3.5 will add file-ranked selection.
        </div>
      )}
      <div
        role="tablist"
        aria-label="Changed files"
        className="flex items-stretch h-10 bg-surface border-b border-border overflow-x-auto shrink-0"
        data-testid="diff-file-tabs"
      >
        {files.map((file, index) => {
          const isActive = index === safeIndex
          const label = fileBasename(file)
          const title = fileDisplayPath(file)
          const highlighted = isActive && isHighlighted
          const activeStyle: React.CSSProperties | undefined = isActive
            ? {
                transition: `border-bottom-color ${FILE_HIGHLIGHT_TRANSITION_MS}ms ease-in-out`,
                borderBottomColor: highlighted ? FILE_HIGHLIGHT_COLOR : undefined,
              }
            : undefined
          return (
            <button
              key={`${file.oldRevision}-${file.newRevision}-${index}`}
              ref={(el) => {
                tabRefs.current[index] = el
              }}
              role="tab"
              type="button"
              aria-selected={isActive}
              aria-current={highlighted ? 'true' : undefined}
              data-highlighted={highlighted ? 'true' : undefined}
              tabIndex={isActive ? 0 : -1}
              title={title}
              onClick={() => setActiveFile(index)}
              onKeyDown={onTabKeyDown}
              style={activeStyle}
              className={`px-3 flex items-center whitespace-nowrap text-[14px] ${
                isActive
                  ? 'font-bold text-text-primary border-b-2 border-accent'
                  : 'font-medium text-text-secondary'
              }`}
              data-testid={`diff-file-tab-${index}`}
            >
              {label}
            </button>
          )
        })}
      </div>
      <div
        ref={scrollContainerRef}
        className="flex-1 min-h-0 overflow-auto bg-surface"
        data-testid="diff-scroll-container"
      >
        {activeFile && isBinaryFile(activeFile) && (
          <div
            className="h-full w-full flex items-center justify-center p-6"
            data-testid="diff-binary-placeholder"
            role="region"
            aria-label={`Binary file: ${fileDisplayPath(activeFile)}`}
          >
            <p className="text-[14px] text-text-muted text-center">
              Binary file — not displayed.
              <br />
              <span className="text-[12px]">{fileDisplayPath(activeFile)}</span>
            </p>
          </div>
        )}
        {activeFile && !isBinaryFile(activeFile) && (
          <Diff
            key={`${activeFile.oldRevision}-${activeFile.newRevision}-${safeIndex}`}
            viewType="unified"
            diffType={activeFile.type}
            hunks={activeFile.hunks}
            tokens={tokens}
            generateAnchorID={makeAnchorID}
          >
            {(hunks) => hunks.map((hunk) => <Hunk key={hunk.content} hunk={hunk} />)}
          </Diff>
        )}
      </div>
    </div>
  )
})

export default DiffViewer
