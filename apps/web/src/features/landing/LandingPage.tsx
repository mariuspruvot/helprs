import SignInButton from './SignInButton'

function Section({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`w-full px-6 ${className}`}>
      <div className="max-w-[960px] mx-auto">{children}</div>
    </section>
  )
}

function Divider() {
  return <div className="w-full h-px mb-20 md:mb-28" style={{ background: 'rgba(255,255,255,0.06)' }} />
}

function Overline({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-accent text-[13px] font-medium mb-4 uppercase" style={{ letterSpacing: '0.1em' }}>
      {children}
    </p>
  )
}

function Terminal({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="overflow-hidden"
      style={{
        borderRadius: '10px',
        background: '#141414',
        boxShadow:
          '0 0 0 1px rgba(255,255,255,0.06), 0 4px 16px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.2)',
      }}
    >
      <div className="flex items-center gap-[7px] px-4 py-3" style={{ background: '#1e1e1e' }}>
        <span className="w-[11px] h-[11px] rounded-full" style={{ background: '#ff5f57' }} />
        <span className="w-[11px] h-[11px] rounded-full" style={{ background: '#febc2e' }} />
        <span className="w-[11px] h-[11px] rounded-full" style={{ background: '#28c840' }} />
      </div>
      <div className="px-5 py-4">
        <pre className="text-[13px] leading-[1.7] whitespace-pre font-mono select-none" style={{ color: '#b0b0b0' }}>
          {children}
        </pre>
      </div>
    </div>
  )
}

function LinkButton({
  href,
  variant = 'primary',
  children,
  className = '',
}: {
  href: string
  variant?: 'primary' | 'secondary'
  children: React.ReactNode
  className?: string
}) {
  const styles =
    variant === 'primary'
      ? {
          borderRadius: '8px',
          color: '#1a1400',
          background: '#E2A039',
          boxShadow:
            'rgba(226,160,57,0.4) 0 0 0 1px, inset rgba(255,255,255,0.15) 0 1px 0 0, rgba(0,0,0,0.2) 0 2px 4px',
        }
      : {
          borderRadius: '8px',
          boxShadow: 'rgba(255,255,255,0.1) 0 0 0 1px',
        }

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-block text-[15px] font-semibold py-3 px-6 text-center transition-all duration-150 active:scale-[0.98] ${variant === 'secondary' ? 'text-text-secondary hover:text-text-primary' : ''} ${className}`}
      style={styles}
    >
      {children}
    </a>
  )
}

const TERM = {
  green: '#5af78e',
  amber: '#E2A039',
  muted: '#555',
} as const

const GITHUB_URL = 'https://github.com/mariuspruvot/helprs'
const DOCS_URL = `${GITHUB_URL}/blob/main/docs/self-hosting.md`
const INSTALL_URL = `https://github.com/apps/${import.meta.env.VITE_GITHUB_APP_SLUG ?? 'helprs'}/installations/new`

const STEPS = [
  {
    number: '01',
    title: 'Webhook received',
    description:
      'A GitHub App sends PR events to your helPRs instance. The API creates a session and posts a comment on the PR with a link.',
    terminal: (
      <>
        <span style={{ color: TERM.green }}>$</span>
        {' git push origin feat/retry-logic\n'}
        <span style={{ color: TERM.muted }}>{'  \u2192 PR #42 opened\n'}</span>
        <span style={{ color: TERM.muted }}>{'  \u2192 webhook received\n'}</span>
        <span style={{ color: TERM.amber }}>{'  \u2192 comment: Ready when you are'}</span>
      </>
    ),
  },
  {
    number: '02',
    title: 'Container runs skill',
    description:
      'Clicking the link boots an ephemeral Docker container. Claude Code clones the repo, checks out the PR, and executes the assigned skill.',
    terminal: (
      <>
        <span style={{ color: TERM.green }}>docker</span>
        {' run claude-runner\n'}
        <span style={{ color: TERM.muted }}>{'  clone repo           \u2713\n'}</span>
        <span style={{ color: TERM.muted }}>{'  checkout PR #42      \u2713\n'}</span>
        <span style={{ color: TERM.amber }}>{'  \u2192 claude -p "challenge-me"'}</span>
      </>
    ),
  },
  {
    number: '03',
    title: 'Live results, then cleanup',
    description:
      'The session streams to the web UI via SSE. Answer questions, discuss trade-offs, get a private score. Container self-destructs when done.',
    terminal: (
      <>
        {'  depth    '}
        <span style={{ color: TERM.amber }}>{'\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588'}</span>
        {' 8/10\n'}
        {'  insight  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588'}
        <span style={{ color: TERM.muted }}>{'\u2591\u2591'}</span>
        {' 7/10\n'}
        {'  verdict: '}
        <span style={{ color: TERM.green }}>strong</span>
        {'\n\n'}
        <span style={{ color: TERM.muted }}>{'  container destroyed \u2713'}</span>
      </>
    ),
  },
] as const

const FEATURES = [
  {
    label: 'BYOK',
    title: 'Bring Your Own Key',
    description:
      'You provide your Claude credentials once. Encrypted at rest, injected at runtime. helPRs never calls the Claude API \u2014 containers use your credentials natively.',
  },
  {
    label: 'EPHEM',
    title: 'Ephemeral containers',
    description:
      'Each session runs in an isolated Docker container. It clones, runs, streams, and self-destructs. Nothing persists between sessions.',
  },
  {
    label: 'OSS',
    title: 'Open source',
    description:
      'MIT licensed. Deploy on your infrastructure with Docker Compose. No vendor lock-in, no usage fees, no data leaving your network.',
  },
] as const

const SUBTLE_CARD = {
  borderRadius: '12px',
  background: '#252121',
  boxShadow: 'rgba(255,255,255,0.05) 0 0 0 1px',
} as const

export default function LandingPage() {
  return (
    <div
      className="min-h-screen bg-primary text-text-primary"
      style={{ fontFamily: 'var(--font-family-sans)', letterSpacing: '0.2px' }}
    >
      {/* Nav */}
      <header className="w-full px-6 py-5">
        <div className="max-w-[960px] mx-auto flex items-center justify-between">
          <span className="text-text-secondary font-semibold font-mono text-[15px]" style={{ letterSpacing: '-0.01em' }}>
            <span style={{ color: '#E2A039' }}>helPRs</span>
          </span>
          <div className="flex items-center gap-4">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[13px] font-medium text-text-muted hover:text-text-primary transition-colors duration-150"
            >
              GitHub
            </a>
            <SignInButton />
          </div>
        </div>
      </header>

      {/* Hero */}
      <Section className="pt-16 pb-24 md:pt-28 md:pb-36">
        <h1
          className="text-[32px] md:text-[40px] lg:text-[52px] font-semibold leading-[1.08] mb-7 font-mono"
          style={{ letterSpacing: '-0.02em' }}
        >
          AI skills for every{' '}
          <span
            style={{
              textDecoration: 'underline',
              textDecorationColor: 'var(--color-accent)',
              textUnderlineOffset: '6px',
              textDecorationThickness: '2px',
            }}
          >
            pull request
          </span>
        </h1>
        <p className="text-text-secondary text-[17px] leading-[1.65] mb-12 max-w-[600px]">
          helPRs is an open-source tool that spins up ephemeral Docker containers with{' '}
          <a
            href="https://docs.anthropic.com/en/docs/claude-code"
            target="_blank"
            rel="noopener noreferrer"
            className="text-text-primary hover:text-accent transition-colors duration-150"
            style={{
              textDecoration: 'underline',
              textDecorationColor: 'rgba(255,255,255,0.3)',
              textUnderlineOffset: '3px',
            }}
          >
            Claude Code
          </a>{' '}
          on your pull requests. Comprehension quizzes, code reviews, or any custom skill
          &mdash; self-hosted, on your infrastructure.
        </p>
        <div className="flex flex-col sm:flex-row items-start gap-4">
          <LinkButton href={GITHUB_URL}>View on GitHub</LinkButton>
          <LinkButton href={DOCS_URL} variant="secondary">
            Self-hosting guide
          </LinkButton>
        </div>
      </Section>

      {/* How it works */}
      <Section className="py-20 md:py-28">
        <Divider />
        <Overline>How it works</Overline>
        <h2
          className="text-[26px] md:text-[30px] font-semibold mb-14 font-mono"
          style={{ letterSpacing: '-0.02em' }}
        >
          From webhook to results
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {STEPS.map((step) => (
            <div key={step.number}>
              <div className="mb-6">
                <Terminal>{step.terminal}</Terminal>
              </div>
              <div className="flex items-baseline gap-3 mb-2">
                <span className="text-accent text-[28px] font-bold leading-none font-mono">
                  {step.number}
                </span>
                <h3 className="text-[16px] font-semibold font-mono" style={{ letterSpacing: '-0.01em' }}>
                  {step.title}
                </h3>
              </div>
              <p className="text-text-secondary text-[15px] leading-[1.65]">{step.description}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Self-hosted & Private */}
      <Section className="py-20 md:py-28">
        <Divider />
        <Overline>Self-hosted & private</Overline>
        <h2
          className="text-[26px] md:text-[30px] font-semibold mb-14 font-mono"
          style={{ letterSpacing: '-0.02em' }}
        >
          Your infrastructure, your data
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {FEATURES.map((item) => (
            <div key={item.title} className="p-6" style={SUBTLE_CARD}>
              <span className="text-accent text-[12px] font-semibold" style={{ letterSpacing: '0.12em' }}>
                {item.label}
              </span>
              <h3 className="text-[16px] font-semibold mt-2 mb-3 font-mono" style={{ letterSpacing: '-0.01em' }}>
                {item.title}
              </h3>
              <p className="text-text-secondary text-[15px] leading-[1.65]">{item.description}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Get started */}
      <Section className="py-20 md:py-28">
        <Divider />
        <div className="md:flex md:items-start md:gap-14">
          <div className="md:flex-1 mb-10 md:mb-0">
            <Overline>Get started</Overline>
            <h2
              className="text-[26px] md:text-[30px] font-semibold mb-7 font-mono"
              style={{ letterSpacing: '-0.02em' }}
            >
              Deploy in minutes
            </h2>
            <div className="space-y-5 text-text-secondary text-[15px] leading-[1.65]">
              <p>
                Clone the repo, configure your environment, and start the stack with Docker Compose. Then create
                a GitHub App, install it on your org, and you're running skills on PRs.
              </p>
              <p>
                Write your own skills or use the built-in{' '}
                <span className="text-text-primary font-medium">challenge-me</span> &mdash; a Socratic
                comprehension quiz that probes whether the PR author truly understands their changes.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row items-start gap-4 mt-8">
              <LinkButton href={GITHUB_URL}>View on GitHub</LinkButton>
              <LinkButton href={DOCS_URL} variant="secondary">
                Self-hosting guide
              </LinkButton>
            </div>
          </div>
          <div className="md:w-[380px]">
            <Terminal>
              <span style={{ color: TERM.green }}>$</span>
              {' git clone github.com/mariuspruvot/helprs\n'}
              <span style={{ color: TERM.green }}>$</span>
              {' cd helprs\n'}
              <span style={{ color: TERM.green }}>$</span>
              {' cp .env.example .env\n'}
              <span style={{ color: TERM.green }}>$</span>
              {' docker compose up --build\n\n'}
              <span style={{ color: TERM.muted }}>{'  API  '}</span>
              <span style={{ color: TERM.amber }}>{'http://localhost:8000'}</span>
              {'\n'}
              <span style={{ color: TERM.muted }}>{'  Web  '}</span>
              <span style={{ color: TERM.amber }}>{'http://localhost:5173'}</span>
              {'\n'}
              <span style={{ color: TERM.muted }}>{'  DB   '}</span>
              <span style={{ color: TERM.amber }}>{'postgresql://localhost:5432'}</span>
            </Terminal>
            <p className="text-text-muted text-[13px] mt-4 text-center">
              Already on a helPRs instance?{' '}
              <a
                href={INSTALL_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline"
              >
                Install the GitHub App
              </a>
            </p>
          </div>
        </div>
      </Section>

      {/* Footer */}
      <footer className="w-full px-6 py-10" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div className="max-w-[960px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-text-muted text-[13px]">
          <span className="text-text-secondary font-medium font-mono" style={{ letterSpacing: '-0.01em' }}>
            helPRs
          </span>
          <div className="flex gap-6">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-text-primary transition-colors duration-150"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
