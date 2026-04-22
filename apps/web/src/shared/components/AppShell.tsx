import { GrainOverlay } from './GrainOverlay'
import { Topbar } from './Topbar'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="relative h-screen flex flex-col bg-bg text-ink">
      <GrainOverlay />
      <Topbar />
      <main className="relative flex-1 min-h-0 flex flex-col overflow-y-auto">
        <div className="flex-1 flex flex-col w-full max-w-[1120px] mx-auto px-5 py-6">
          {children}
        </div>
      </main>
    </div>
  )
}
