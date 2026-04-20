import { Button, Card, GrainOverlay, Overline, StatCard, TerminalBlock } from '../../shared/components'
import SignInButton from './SignInButton'

const GITHUB_URL = 'https://github.com/mariuspruvot/helprs'
const DOCS_URL = `${GITHUB_URL}/blob/main/docs/self-hosting.md`
const INSTALL_URL = `https://github.com/apps/${import.meta.env.VITE_GITHUB_APP_SLUG ?? 'helprs'}/installations/new`
const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const TERM = { green: '#7fb37a', amber: '#e2a039', dim: '#5a5348' } as const

const STEPS = [
  {
    number: '01',
    title: 'Webhook received',
    description: 'A GitHub App sends PR events to your helPRs instance. The API creates a session and posts a comment on the PR.',
    terminal: (
      <>
        <span style={{ color: TERM.green }}>$</span>{' git push origin feat/retry-logic\n'}
        <span style={{ color: TERM.dim }}>{'  \u2192 PR #42 opened\n'}</span>
        <span style={{ color: TERM.dim }}>{'  \u2192 webhook dispatched\n'}</span>
        <span style={{ color: TERM.amber }}>{'  \u2192 comment: Ready when you are'}</span>
      </>
    ),
  },
  {
    number: '02',
    title: 'Container runs skill',
    description: 'Clicking the link boots an ephemeral Docker container. Claude Code clones the repo, checks out the PR, and runs the assigned skill.',
    terminal: (
      <>
        <span style={{ color: TERM.green }}>docker</span>{' run claude-runner\n'}
        <span style={{ color: TERM.dim }}>{'  clone repo           \u2713\n'}</span>
        <span style={{ color: TERM.dim }}>{'  checkout PR #42      \u2713\n'}</span>
        <span style={{ color: TERM.amber }}>{'  \u2192 claude -p "challenge-me"'}</span>
      </>
    ),
  },
  {
    number: '03',
    title: 'Score and learn',
    description: 'Answer questions, defend decisions, get a private score. The container self-destructs. XP and badges update your profile.',
    terminal: (
      <>
        {'  depth    '}
        <span style={{ color: TERM.amber }}>{'\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588'}</span>
        {' 8/10\n'}
        {'  clarity  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588'}
        <span style={{ color: TERM.dim }}>{'\u2591\u2591'}</span>
        {' 7/10\n'}
        {'  rigor    \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588'}
        <span style={{ color: TERM.dim }}>{'\u2591'}</span>
        {' 9/10\n\n'}
        <span style={{ color: TERM.green }}>{'  +250 XP'}</span>
        <span style={{ color: TERM.dim }}>{'  container destroyed \u2713'}</span>
      </>
    ),
  },
] as const

const FEATURES = [
  {
    label: 'BYOK',
    title: 'Bring Your Own Key',
    description: 'You provide your Claude credentials once. Encrypted at rest, injected at runtime. helPRs never calls the Claude API directly.',
  },
  {
    label: 'EPHEM',
    title: 'Ephemeral containers',
    description: 'Each session runs in an isolated Docker container. It clones, runs, streams, and self-destructs. Nothing persists between sessions.',
  },
  {
    label: 'OSS',
    title: 'Open source',
    description: 'MIT licensed. Deploy on your infrastructure with Docker Compose. No vendor lock-in, no usage fees, no data leaving your network.',
  },
] as const

function ExampleCard() {
  return (
    <Card className="max-w-[560px] mt-12">
      <Overline>// example session · challenge-me</Overline>
      <div className="mt-4 space-y-3">
        <div className="border-l-[3px] border-accent pl-4 py-2">
          <p className="font-mono text-xs text-ink2 leading-relaxed">
            Your retry logic uses <code className="text-accent">asyncio.sleep(2 ** attempt)</code>.
            What happens if the upstream service returns 429 with a Retry-After header?
            Does your implementation respect it?
          </p>
        </div>
        <div className="bg-card-hi border border-rule-str rounded-[8px] pl-4 py-2 pr-4">
          <p className="font-mono text-xs text-ink2 leading-relaxed">
            Good catch. Right now it doesn't — I'd need to parse the header
            and use <code className="text-accent">max(backoff, retry_after)</code> to avoid hammering the service...
          </p>
        </div>
      </div>
    </Card>
  )
}

export default function LandingPage() {
  return (
    <div className="relative min-h-screen bg-bg text-ink font-sans">
      <GrainOverlay />

      {/* Nav */}
      <header className="relative w-full px-6 py-5">
        <div className="max-w-[960px] mx-auto flex items-center justify-between">
          <span className="font-mono text-sm font-bold text-accent tracking-tight">helPRs</span>
          <div className="flex items-center gap-4">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-xs text-dim hover:text-ink2 transition-colors"
            >
              GitHub
            </a>
            <SignInButton />
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative w-full px-6 pt-16 pb-8 md:pt-28 md:pb-12">
        <div className="max-w-[960px] mx-auto">
          <h1 className="font-mono text-[32px] md:text-[44px] lg:text-[52px] font-bold leading-[1.08] mb-6" style={{ letterSpacing: '-0.02em' }}>
            Ship a PR, get{' '}
            <span className="text-accent underline decoration-accent/40 underline-offset-[6px] decoration-2">
              interrogated
            </span>
            {' '}in plain English
          </h1>
          <p className="text-ink2 text-[17px] leading-[1.65] mb-8 max-w-[600px] font-sans">
            helPRs is an open-source developer learning companion that lives on your pull requests.
            Interactive quizzes, architecture hot seats, debugging challenges — all powered by
            ephemeral Claude Code containers on your infrastructure.
          </p>
          <div className="flex flex-col sm:flex-row items-start gap-3">
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
              <Button>View on GitHub</Button>
            </a>
            <a href={DOCS_URL} target="_blank" rel="noopener noreferrer">
              <Button variant="secondary">Self-hosting guide</Button>
            </a>
          </div>
          <p className="text-dim text-sm mt-5 font-mono">
            {'// or '}
            <a href={`${API_BASE}/api/v1/auth/github`} className="text-accent hover:underline">
              sign in
            </a>
            {' to use this instance'}
          </p>

          <ExampleCard />
        </div>
      </section>

      {/* Stats strip */}
      <section className="relative w-full px-6 py-12">
        <div className="max-w-[960px] mx-auto grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Interactive" value="100%" sub="every skill requires participation" />
          <StatCard label="Duration" value="5-10m" sub="per session" color="accent" />
          <StatCard label="Privacy" value="Local" sub="no data leaves your network" color="ok" />
          <StatCard label="License" value="MIT" sub="open source, forever" />
        </div>
      </section>

      {/* How it works */}
      <section className="relative w-full px-6 py-16 md:py-24">
        <div className="max-w-[960px] mx-auto">
          <div className="h-px bg-rule mb-16" />
          <Overline className="text-accent mb-3">{'\u25B8'} HOW IT WORKS</Overline>
          <h2 className="font-mono text-[26px] md:text-[30px] font-bold mb-12" style={{ letterSpacing: '-0.02em' }}>
            From webhook to results
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {STEPS.map((step) => (
              <div key={step.number}>
                <TerminalBlock className="mb-5">
                  <pre className="whitespace-pre">{step.terminal}</pre>
                </TerminalBlock>
                <div className="flex items-baseline gap-3 mb-2">
                  <span className="text-accent text-[24px] font-bold font-mono">{step.number}</span>
                  <h3 className="font-mono text-sm font-semibold">{step.title}</h3>
                </div>
                <p className="text-ink2 text-sm leading-[1.65] font-sans">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Self-hosted & private */}
      <section className="relative w-full px-6 py-16 md:py-24">
        <div className="max-w-[960px] mx-auto">
          <div className="h-px bg-rule mb-16" />
          <Overline className="text-accent mb-3">{'\u25B8'} SELF-HOSTED & PRIVATE</Overline>
          <h2 className="font-mono text-[26px] md:text-[30px] font-bold mb-12" style={{ letterSpacing: '-0.02em' }}>
            Your infrastructure, your data
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {FEATURES.map((item) => (
              <Card key={item.title} hover>
                <Overline className="text-accent">{item.label}</Overline>
                <h3 className="font-mono text-sm font-semibold mt-2 mb-3">{item.title}</h3>
                <p className="text-ink2 text-sm leading-[1.65] font-sans">{item.description}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Get started */}
      <section className="relative w-full px-6 py-16 md:py-24">
        <div className="max-w-[960px] mx-auto">
          <div className="h-px bg-rule mb-16" />
          <div className="md:flex md:items-start md:gap-14">
            <div className="md:flex-1 mb-10 md:mb-0">
              <Overline className="text-accent mb-3">{'\u25B8'} GET STARTED</Overline>
              <h2 className="font-mono text-[26px] md:text-[30px] font-bold mb-6" style={{ letterSpacing: '-0.02em' }}>
                Deploy in minutes
              </h2>
              <div className="space-y-4 text-ink2 text-[15px] leading-[1.65] font-sans">
                <p>
                  Clone the repo, configure your environment, and start the stack with Docker Compose.
                  Create a GitHub App, install it on your org, and you're running skills on PRs.
                </p>
                <p>
                  Write your own skills or use the built-in{' '}
                  <span className="text-ink font-medium">challenge-me</span> — a Socratic
                  comprehension quiz that probes whether you truly understand your own changes.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row items-start gap-3 mt-8">
                <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
                  <Button>View on GitHub</Button>
                </a>
                <a href={DOCS_URL} target="_blank" rel="noopener noreferrer">
                  <Button variant="secondary">Self-hosting guide</Button>
                </a>
              </div>
            </div>
            <div className="md:w-[380px]">
              <TerminalBlock title="terminal">
                <pre className="whitespace-pre">
                  <span style={{ color: TERM.green }}>$</span>{' git clone github.com/mariuspruvot/helprs\n'}
                  <span style={{ color: TERM.green }}>$</span>{' cd helprs\n'}
                  <span style={{ color: TERM.green }}>$</span>{' cp .env.example .env\n'}
                  <span style={{ color: TERM.green }}>$</span>{' docker compose up --build\n\n'}
                  <span style={{ color: TERM.dim }}>{'  API  '}</span>
                  <span style={{ color: TERM.amber }}>{'http://localhost:8000'}</span>{'\n'}
                  <span style={{ color: TERM.dim }}>{'  Web  '}</span>
                  <span style={{ color: TERM.amber }}>{'http://localhost:5173'}</span>{'\n'}
                  <span style={{ color: TERM.dim }}>{'  DB   '}</span>
                  <span style={{ color: TERM.amber }}>{'postgresql://localhost:5432'}</span>
                </pre>
              </TerminalBlock>
              <p className="text-dim text-xs mt-4 text-center font-mono">
                Already on a helPRs instance?{' '}
                <a href={INSTALL_URL} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                  Install the GitHub App
                </a>
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative w-full px-6 py-8 border-t border-rule">
        <div className="max-w-[960px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="font-mono text-xs font-bold text-accent">helPRs</span>
          <div className="flex gap-6">
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="font-mono text-xs text-dim hover:text-ink2 transition-colors">
              GitHub
            </a>
            <a href={DOCS_URL} target="_blank" rel="noopener noreferrer" className="font-mono text-xs text-dim hover:text-ink2 transition-colors">
              Docs
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
