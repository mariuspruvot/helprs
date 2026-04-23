import { useEffect } from 'react'
import { Button, GrainOverlay } from '../../shared/components'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const GITHUB_URL = 'https://github.com/mariuspruvot/helprs'
const SIGN_IN_URL = `${API_BASE}/api/v1/auth/github`

function GitHubIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.62 7.62 0 0 1 8 3.85c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

export default function LoginPage() {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Enter' || e.defaultPrevented) return
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'A' || tag === 'BUTTON' || tag === 'INPUT' || tag === 'TEXTAREA') return
      window.location.href = SIGN_IN_URL
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <div className="relative min-h-screen bg-bg text-ink font-sans flex flex-col items-center justify-center px-6">
      <GrainOverlay />

      <main className="relative flex flex-col items-center text-center max-w-md w-full">
        <h1 className="font-mono text-3xl font-bold text-accent tracking-tight inline-flex items-center">
          helPRs
          <span
            className="ml-1 inline-block w-[0.55ch] h-[1.1rem] bg-accent align-middle animate-cursor"
            aria-hidden="true"
          />
        </h1>
        <p className="mt-4 text-ink2 text-sm leading-relaxed font-mono">
          Interactive skills for your pull requests.
        </p>
        <p className="mt-1 text-dim text-xs font-mono">
          Review, challenge, quiz {'\u2014'} powered by Claude Code. Self-hosted.
        </p>

        <a href={SIGN_IN_URL} className="mt-10 w-full sm:w-auto">
          <Button className="w-full sm:w-auto px-6 py-3">
            <GitHubIcon />
            Sign in with GitHub
          </Button>
        </a>

        <p className="mt-4 font-mono text-xs text-dim">
          press{' '}
          <kbd className="px-1.5 py-0.5 rounded border border-rule-str text-ink2 text-[10px]">
            {'\u21B5'} enter
          </kbd>{' '}
          to continue
        </p>

        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-8 font-mono text-xs text-dim hover:text-ink2 transition-colors"
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
