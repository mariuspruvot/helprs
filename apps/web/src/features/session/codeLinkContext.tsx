import { createContext, useContext, useMemo, type MutableRefObject } from 'react'
import type { DiffViewerHandle } from './DiffViewer'

/**
 * Story 3.4: actions exposed by `DiffViewer` to `CodeLink` buttons
 * rendered inside feedback messages. Lives in a React context so
 * `ChatMessage` does not need to receive a ref drilled through props.
 */
export interface CodeLinkActions {
  scrollTo: (file: string, line: number) => void
  preview: (file: string, line: number) => void
  clearPreview: () => void
}

/**
 * The context value is a STABLE OBJECT whose methods dispatch to the
 * latest DiffViewer handle via a mutable ref. This avoids re-rendering
 * every consumer of the context every time DiffViewer remounts.
 */
export const CodeLinkActionsContext = createContext<CodeLinkActions | null>(null)

/**
 * Story 3.4: ChatView mounts this context to give CodeLink buttons a
 * channel to call DiffViewer's imperative API. DiffViewer registers
 * its handle in the ref via `useDiffViewerHandleRegister`; CodeLink
 * consumes the actions via `useCodeLinkActions`.
 */
export const DiffViewerHandleRefContext =
  createContext<MutableRefObject<DiffViewerHandle | null> | null>(null)

/**
 * Build a stable {scrollTo, preview, clearPreview} object that proxies
 * to the current DiffViewer handle. Memoized so the consumer's
 * useContext() doesn't churn on every parent re-render.
 */
export function useStableCodeLinkActions(
  handleRef: MutableRefObject<DiffViewerHandle | null>,
): CodeLinkActions {
  return useMemo<CodeLinkActions>(
    () => ({
      scrollTo: (file, line) => handleRef.current?.scrollTo(file, line),
      preview: (file, line) => handleRef.current?.preview(file, line),
      clearPreview: () => handleRef.current?.clearPreview(),
    }),
    [handleRef],
  )
}

/**
 * Resolve the nearest provider's actions. Throws if no provider is
 * mounted — Story 3.4 Task 15.2 (code-review A21): a silent no-op
 * fallback hid missing-provider bugs in dev. Tests that render
 * `ChatMessage` / `CodeLink` in isolation MUST wrap them in a
 * `CodeLinkActionsContext.Provider` with explicit actions.
 */
export function useCodeLinkActions(): CodeLinkActions {
  const ctx = useContext(CodeLinkActionsContext)
  if (ctx === null) {
    throw new Error(
      'useCodeLinkActions must be used inside a <CodeLinkActionsContext.Provider>',
    )
  }
  return ctx
}

/**
 * Resolve the mutable handle ref so DiffViewer can register itself.
 * Returns null if no provider is mounted (DiffViewer falls back to
 * no-op behaviour in that case).
 */
export function useDiffViewerHandleRefSlot(): MutableRefObject<DiffViewerHandle | null> | null {
  return useContext(DiffViewerHandleRefContext)
}
