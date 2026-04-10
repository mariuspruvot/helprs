import type { SessionResponse } from './types'

interface ChatPanelProps {
  session: SessionResponse
}

// Scaffolding only (Story 3.2) — Story 3.3 will replace the placeholder with
// the streaming message list and Story 3.4 will add the chat input at the
// bottom of this panel. Do NOT render a disabled input stub.
export default function ChatPanel({ session: _session }: ChatPanelProps) {
  return (
    <div
      className="h-full w-full bg-primary flex flex-col overflow-hidden"
      data-testid="chat-panel"
    >
      <div className="flex-1 overflow-y-auto flex items-center justify-center">
        {/* 720px cap lives on the inner content container, NOT the panel. */}
        <div className="max-w-[720px] w-full px-4 text-center">
          <p className="text-[14px] text-text-muted">Waiting for the first question...</p>
        </div>
      </div>
    </div>
  )
}
