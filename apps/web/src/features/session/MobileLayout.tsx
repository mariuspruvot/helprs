import ChatPanel from './ChatPanel'
import type { SessionResponse } from './types'

interface MobileLayoutProps {
  session: SessionResponse
}

export default function MobileLayout({ session }: MobileLayoutProps) {
  return (
    <div className="h-full w-full flex flex-col bg-primary" data-testid="mobile-layout">
      <div
        className="mx-3 mt-3 mb-2 px-3 py-3 rounded bg-surface text-text-secondary text-[14px] shrink-0"
        style={{ minHeight: 40 }}
        data-testid="mobile-banner"
      >
        Open on desktop for the full experience with code view.
      </div>
      <div className="flex-1 min-h-0">
        <ChatPanel session={session} />
      </div>
    </div>
  )
}
