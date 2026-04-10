import { useRef, useState } from 'react'
import ChatPanel from './ChatPanel'
import DiffViewer from './DiffViewer'
import type { SessionResponse } from './types'

interface TabbedLayoutProps {
  session: SessionResponse
}

type Tab = 'chat' | 'diff'

const TABS: ReadonlyArray<{ id: Tab; label: string }> = [
  { id: 'chat', label: 'Chat' },
  { id: 'diff', label: 'Diff' },
]

export default function TabbedLayout({ session }: TabbedLayoutProps) {
  const [activeTab, setActiveTab] = useState<Tab>('chat')
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({
    chat: null,
    diff: null,
  })

  const focusTab = (tab: Tab) => {
    setActiveTab(tab)
    tabRefs.current[tab]?.focus()
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const currentIndex = TABS.findIndex((t) => t.id === activeTab)
    const nextIndex =
      event.key === 'ArrowLeft'
        ? (currentIndex - 1 + TABS.length) % TABS.length
        : (currentIndex + 1) % TABS.length
    focusTab(TABS[nextIndex].id)
  }

  return (
    <div className="h-full w-full flex flex-col" data-testid="tabbed-layout">
      <div
        role="tablist"
        aria-label="Session view"
        className="flex border-b border-border bg-primary shrink-0"
      >
        {TABS.map((tab) => {
          const isActive = tab.id === activeTab
          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[tab.id] = el
              }}
              role="tab"
              type="button"
              id={`session-tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`session-tabpanel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => focusTab(tab.id)}
              onKeyDown={handleKeyDown}
              className={`px-4 py-2 text-[14px] ${
                isActive
                  ? 'font-bold text-text-primary border-b-2 border-accent'
                  : 'font-medium text-text-secondary'
              }`}
            >
              {tab.label}
            </button>
          )
        })}
      </div>
      <div
        role="tabpanel"
        id={`session-tabpanel-${activeTab}`}
        aria-labelledby={`session-tab-${activeTab}`}
        className="flex-1 min-h-0"
      >
        {activeTab === 'chat' ? (
          <ChatPanel session={session} />
        ) : (
          <DiffViewer session={session} />
        )}
      </div>
    </div>
  )
}
