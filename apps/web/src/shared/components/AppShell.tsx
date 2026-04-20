import { GrainOverlay } from './GrainOverlay'
import { Topbar } from './Topbar'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="relative min-h-screen bg-bg text-ink">
      <GrainOverlay />
      <Topbar />
      <main className="relative max-w-[1120px] mx-auto px-5 py-8">
        {children}
      </main>
    </div>
  )
}
