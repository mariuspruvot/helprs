import { useEffect, useMemo, useRef } from 'react'
import { Diff, Hunk, parseDiff, tokenize } from 'react-diff-view'
import type { FileData, HunkTokens } from 'react-diff-view'
import 'react-diff-view/style/index.css'
import { useSessionStore } from './store'
import { languageFromPath, refractorAdapter } from './refractorSetup'
import type { SessionResponse } from './types'

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

export default function DiffViewer({ session }: DiffViewerProps) {
  const activeFileIndex = useSessionStore((s) => s.activeFileIndex)
  const setActiveFile = useSessionStore((s) => s.setActiveFile)

  // parseDiff always returns at least one file even for empty/garbage input
  // (empty path, zero hunks). Treat such placeholders as "no changes" so
  // the user sees the empty state instead of an empty tab bar.
  const files = useMemo<FileData[]>(() => {
    const parsed = parseDiff(session.diff)
    return parsed.filter((file) => file.hunks.length > 0)
  }, [session.diff])
  const isTruncated = useMemo(
    () => session.diff.includes(TRUNCATION_MARKER),
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
    } catch {
      // Defensive: a malformed hunk or unsupported lang should degrade to
      // plain text, not crash the whole session page.
      return null
    }
  }, [activeFile])

  const scrollContainerRef = useRef<HTMLDivElement>(null)
  // TODO: story-3.4 — expose scrollToLine via useImperativeHandle on this ref.

  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])

  // Keep keyboard focus synced with the active tab when the store changes.
  useEffect(() => {
    if (document.activeElement?.getAttribute('role') === 'tab') {
      tabRefs.current[safeIndex]?.focus()
    }
  }, [safeIndex])

  const onTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
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
          return (
            <button
              key={`${file.oldRevision}-${file.newRevision}-${index}`}
              ref={(el) => {
                tabRefs.current[index] = el
              }}
              role="tab"
              type="button"
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
              title={title}
              onClick={() => setActiveFile(index)}
              onKeyDown={onTabKeyDown}
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
        {activeFile && (
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
