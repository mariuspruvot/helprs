import { Button, GrainOverlay } from '../../shared/components'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const GITHUB_URL = 'https://github.com/mariuspruvot/helprs'

export default function LoginPage() {
  return (
    <div className="relative min-h-screen bg-bg text-ink font-sans flex flex-col items-center justify-center px-6">
      <GrainOverlay />

      <main className="relative flex flex-col items-center text-center max-w-md w-full">
        <span className="font-mono text-3xl font-bold text-accent tracking-tight">helPRs</span>
        <p className="mt-4 text-ink2 text-sm leading-relaxed font-mono">
          Claude Code on your PRs. Self-hosted.
        </p>

        <a href={`${API_BASE}/api/v1/auth/github`} className="mt-10 w-full sm:w-auto">
          <Button className="w-full sm:w-auto px-6 py-3">Sign in with GitHub</Button>
        </a>

        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-6 font-mono text-xs text-dim hover:text-ink2 transition-colors"
        >
          View on GitHub {'\u2192'}
        </a>
      </main>

      <footer className="relative mt-16 font-mono text-xs text-dim">
        {'// MIT \u00B7 open source'}
      </footer>
    </div>
  )
}
