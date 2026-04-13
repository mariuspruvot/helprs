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

export default function SplitLayout({ session }: SplitLayoutProps) {
  const panelRatio = useSessionStore((s) => s.panelRatio)
  const setPanelRatio = useSessionStore((s) => s.setPanelRatio)
  const diffCollapsed = useSessionStore((s) => s.diffCollapsed)
  const toggleDiffCollapsed = useSessionStore((s) => s.toggleDiffCollapsed)

  if (diffCollapsed) {
    return (
      <div className="h-full w-full flex flex-col">
        <div className="h-full bg-primary relative">
          <ChatPanel session={session} />
          <button
            type="button"
            onClick={toggleDiffCollapsed}
            title="Show diff"
            style={{
              position: 'absolute',
              top: 12,
              right: 12,
              background: '#2c2727',
              color: '#9a9898',
              border: 'none',
              borderRadius: 8,
              padding: '6px 12px',
              fontSize: 13,
              fontFamily: 'var(--font-family-sans)',
              cursor: 'pointer',
              boxShadow: 'rgba(255,255,255,0.06) 0 0 0 1px, rgba(0,0,0,0.2) 0 2px 6px',
              zIndex: 5,
            }}
          >
            Show diff
          </button>
        </div>
      </div>
    )
  }

  const defaultChat = `${(panelRatio * 100).toFixed(0)}%`
  const defaultDiff = `${((1 - panelRatio) * 100).toFixed(0)}%`

  return (
    <Group
      orientation="horizontal"
      className="h-full w-full flex"
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
        className="group relative flex items-stretch justify-center cursor-col-resize focus:outline-none"
        style={{ width: 12 }}
        data-testid="session-resize-handle"
      >
        <span
          className="block w-[2px] h-full group-focus-visible:border-l-2 group-focus-visible:border-r-2 group-focus-visible:border-accent"
          style={{ background: 'rgba(255,255,255,0.08)' }}
          aria-hidden
        />
      </Separator>
      <Panel
        id={DIFF_PANEL_ID}
        defaultSize={defaultDiff}
        minSize="20%"
        className="h-full"
        style={{ background: '#1a1717' }}
        data-testid="diff-panel-container"
      >
        <DiffViewer session={session} onClose={toggleDiffCollapsed} />
      </Panel>
    </Group>
  )
}
