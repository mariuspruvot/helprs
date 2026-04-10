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
// v2 `PanelGroup`/`PanelResizeHandle` mentioned in the story. The semantics
// match: `Separator` still renders with `role="separator"` and handles
// ArrowLeft/ArrowRight via keyboard out of the box.
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
