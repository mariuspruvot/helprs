import { useEffect, useMemo, useRef, useState } from 'react'
import { Diff, Hunk, parseDiff, tokenize } from 'react-diff-view'
import type { FileData, HunkTokens } from 'react-diff-view'
// Library CSS is imported in `main.tsx` BEFORE `index.css` so our
// dark-mode `--diff-*` overrides win the cascade. Do not import it here
// — it would re-import after `index.css` and revert the overrides.
import { useSessionStore } from './store'
import { languageFromPath, refractorAdapter } from './refractorSetup'
import type { SessionResponse } from './types'

// AC #11 (story 3.3): how long the active file tab stays highlighted
// after a question commit cites its file. The CSS transition is half
// of this so the fade-in + fade-out are both visible.
const FILE_HIGHLIGHT_DURATION_MS = 600
const FILE_HIGHLIGHT_TRANSITION_MS = 300
const FILE_HIGHLIGHT_COLOR = '#007aff'

interface DiffViewerProps {
  session: SessionResponse
}

const TRUNCATION_MARKER = '<!-- truncated: diff exceeded 1 MB -->'

function fileDisplayPath(file: FileData): string {
  return file.newPath && file.newPath !== '/dev/null' ? file.newPath : file.oldPath
}

function fileBasename(file: FileData): string {
  const fullPath = fileDisplayPath(file)
  return fullPath.split('/').pop() || fullPath
}

// A binary delta parses into a FileData with zero hunks, a real path, and
// `type: 'modify'`. The empty-input placeholder that `parseDiff` also emits
// has neither hunks nor a meaningful path, so we can distinguish them by
// checking for a usable path.
//
// ⚠️ `gitdiff-parser` technically defines a `file.isBinary` boolean on its
// File type, but its internal parser NEVER sets it in practice: the branch
// that does is only reached when the outer loop reads a line starting with
// "Binary" directly, whereas the inner `simiLoop` (which processes the
// headers following `diff --git`) aggressively consumes the `Binary files
// … differ` line without matching any case — verified empirically with
// `node -e "console.log(require('gitdiff-parser').parse(…).map(f => f.isBinary))"`.
// Until the upstream parser fixes that, we fall back to the structural
// check below.
function hasRealPath(file: FileData): boolean {
  const newPath = file.newPath && file.newPath !== '/dev/null' ? file.newPath : ''
  const oldPath = file.oldPath && file.oldPath !== '/dev/null' ? file.oldPath : ''
  return newPath !== '' || oldPath !== ''
}

function isBinaryFile(file: FileData): boolean {
  // Exclude pure renames (`type === 'rename'`) and pure copies (`type ===
  // 'copy'`) — they also parse with zero hunks + real paths but are clearly
  // not binary. Mode-only changes (chmod) parse with `type: 'modify'` and
  // zero hunks, so they WILL be mis-labelled as "Binary file — not
  // displayed"; this is an accepted edge case (rare in practice, recoverable
  // mis-label rather than a crash), tracked in `deferred-work.md`.
  return (
    file.hunks.length === 0 &&
    hasRealPath(file) &&
    file.type !== 'rename' &&
    file.type !== 'copy'
  )
}

export default function DiffViewer({ session }: DiffViewerProps) {
  const activeFileIndex = useSessionStore((s) => s.activeFileIndex)
  const setActiveFile = useSessionStore((s) => s.setActiveFile)
  const highlightFileTrigger = useSessionStore((s) => s.highlightFileTrigger)
  const [isHighlighted, setIsHighlighted] = useState(false)

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
      // Defensive: a malformed hunk or unsupported lang should degrade to
      // plain text, not crash the whole session page. Log so CI / local
      // dev surfaces a regression if `react-diff-view` ever calls a
      // refractor method that the v4 rename removed.
      console.warn('[DiffViewer] syntax highlighting disabled — falling back to plain text', err)
      return null
    }
  }, [activeFile])

  const scrollContainerRef = useRef<HTMLDivElement>(null)
  // TODO: story-3.4 — expose scrollToLine via useImperativeHandle on this ref.

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

  const onTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    // Do not swallow browser navigation / selection shortcuts — Cmd+Arrow
    // (macOS back/forward), Alt+Arrow (Win/Linux), Shift+Arrow (selection),
    // Ctrl+Arrow (word jump) must still reach the browser.
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
          // AC #11: when ``isHighlighted`` is true and this tab is
          // the active one, override the border-bottom-color to the
          // accent-blue #007aff with a 300 ms transition. The
          // transition is declared unconditionally so both the
          // fade-in and fade-out animate smoothly.
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
          >
            {(hunks) => hunks.map((hunk) => <Hunk key={hunk.content} hunk={hunk} />)}
          </Diff>
        )}
      </div>
    </div>
  )
}
