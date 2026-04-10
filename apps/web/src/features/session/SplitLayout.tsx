import { Group, Panel, Separator } from 'react-resizable-panels'
import ChatPanel from './ChatPanel'
import DiffViewer from './DiffViewer'
import { useSessionStore } from './store'
import type { SessionResponse } from './types'

interface SplitLayoutProps {
  session: SessionResponse
}

const CHAT_PANEL_ID = 'session-chat-panel'
const DIFF_PANEL_ID = 'session-diff-panel'

// NOTE — react-resizable-panels v4 API (`Group`/`Separator`) replaced the
// v2 `PanelGroup`/`PanelResizeHandle` mentioned in the story. v4's
// `Separator` already honours AC #3 without any custom code: it installs a
// native DOM `keydown` listener on the separator element and steps the
// layout by 5% on ArrowLeft / ArrowRight (verified at
// `node_modules/react-resizable-panels/dist/react-resizable-panels.js`
// lines 966/970 — the step is hardcoded to `H(t, ±5)`). The library's
// handler also calls `event.preventDefault()` unconditionally, so Cmd+Arrow
// / Alt+Arrow / Shift+Arrow passthrough is NOT supported by the library;
// we do not attempt to work around that here because fighting the library's
// internal listener via capture-phase `stopImmediatePropagation` is a
// fragile coupling to v4 internals. Drag still bounds-checks via `minSize`
// / `maxSize` on the `Panel`s and the store's own `[0.3, 0.8]` clamp.
export default function SplitLayout({ session }: SplitLayoutProps) {
  const panelRatio = useSessionStore((s) => s.panelRatio)
  const setPanelRatio = useSessionStore((s) => s.setPanelRatio)

  const defaultChat = `${(panelRatio * 100).toFixed(0)}%`
  const defaultDiff = `${((1 - panelRatio) * 100).toFixed(0)}%`

  return (
    <Group
      orientation="horizontal"
      className="h-full w-full flex"
      // Use `onLayoutChanged` (past tense) — the library docs call this out
      // explicitly: `onLayoutChange` fires every pointer frame during drag
      // (N renders per drag); `onLayoutChanged` fires once on pointer release,
      // which is what we want for syncing the store.
      onLayoutChanged={(layout) => {
        const chat = layout[CHAT_PANEL_ID]
        if (typeof chat === 'number') {
          setPanelRatio(chat / 100)
        }
      }}
    >
      <Panel
        id={CHAT_PANEL_ID}
        defaultSize={defaultChat}
        minSize="30%"
        maxSize="80%"
        className="h-full bg-primary"
        data-testid="chat-panel-container"
      >
        <ChatPanel session={session} />
      </Panel>
      <Separator
        // 12px hit area (outer padding), 4px visual line centred.
        className="group relative flex items-stretch justify-center cursor-col-resize focus:outline-none"
        style={{ width: 12 }}
        data-testid="session-resize-handle"
      >
        <span
          className="block w-[4px] h-full bg-border-strong group-focus-visible:border-l-2 group-focus-visible:border-r-2 group-focus-visible:border-accent"
          aria-hidden
        />
      </Separator>
      <Panel
        id={DIFF_PANEL_ID}
        defaultSize={defaultDiff}
        minSize="20%"
        className="h-full bg-surface"
        data-testid="diff-panel-container"
      >
        <DiffViewer session={session} />
      </Panel>
    </Group>
  )
}
