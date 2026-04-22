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
      <main className="relative flex-1 min-h-0 flex flex-col max-w-[1120px] w-full mx-auto px-5 py-6 overflow-auto">
        {children}
      </main>
    </div>
  )
}
