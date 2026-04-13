import InstallCTA from './InstallCTA'

/*
 * Dark theme — Raycast-inspired with amber accent and real terminal blocks.
 * Uses CSS theme vars for dark surfaces, direct colors for terminals.
 */

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

const TERM = {
  green: '#5af78e',
  amber: '#E2A039',
  muted: '#555',
} as const

const STEPS = [
  {
    number: '01',
    title: 'PR opened',
    description: 'helPRs automatically creates a comprehension session for every pull request.',
    terminal: (
      <>
        <span style={{ color: TERM.green }}>$</span>{' git push origin feature/auth\n'}
        <span style={{ color: TERM.muted }}>{'  \u2192 PR #42 opened\n'}</span>
        <span style={{ color: TERM.green }}>{'  \u2192 helPRs session created'}</span>
      </>
    ),
  },
  {
    number: '02',
    title: 'Answer Socratic questions',
    description: 'AI asks targeted questions about your code decisions \u2014 both author and reviewer.',
    terminal: (
      <>
        <span style={{ color: TERM.amber }}>?</span>{' Why did you choose a\n  recursive approach here\n  instead of iterative?'}
      </>
    ),
  },
  {
    number: '03',
    title: 'Get your score',
    description: 'Private comprehension score with specific knowledge gaps identified.',
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
      </>
    ),
  },
] as const

const BYOK_ITEMS = [
  {
    label: 'BYOK',
    title: 'Bring Your Own Key',
    description: 'You provide your Anthropic API key. We never touch it beyond forwarding requests.',
  },
  {
    label: 'ZERO',
    title: 'Zero data retention',
    description: 'No question or answer text stored. Metadata only \u2014 hashes, scores, timestamps.',
  },
  {
    label: 'PRIV',
    title: 'Private by default',
    description: 'Scores are visible only to you. Growth-oriented, never punitive.',
  },
] as const

const CARD = {
  borderRadius: '12px',
  background: '#2a2626',
  boxShadow: [
    'rgba(255,255,255,0.04) 0 1px 0 0 inset',
    'rgba(0,0,0,0.25) 0 2px 4px',
    'rgba(0,0,0,0.15) 0 8px 24px -8px',
    'rgba(255,255,255,0.06) 0 0 0 1px',
  ].join(', '),
} as const

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
      {/* Hero */}
      <Section className="pt-28 pb-24 md:pt-44 md:pb-36">
        <div className="mb-8">
          <span
            className="inline-block text-text-secondary text-[13px] font-medium px-3.5 py-1.5"
            style={{
              borderRadius: '9999px',
              boxShadow: 'rgba(255,255,255,0.08) 0 0 0 1px',
              letterSpacing: '0.04em',
            }}
          >
            For teams shipping AI-generated code
          </span>
        </div>
        <h1
          className="text-[32px] md:text-[40px] lg:text-[52px] font-semibold leading-[1.08] mb-7 font-mono"
          style={{ letterSpacing: '-0.02em' }}
        >
          Do you{' '}
          <span
            style={{
              textDecoration: 'underline',
              textDecorationColor: 'var(--color-accent)',
              textUnderlineOffset: '6px',
              textDecorationThickness: '2px',
            }}
          >
            understand
          </span>
          <br className="hidden md:block" />
          {' '}the code you ship?
        </h1>
        <p className="text-text-secondary text-[17px] leading-[1.65] mb-12 max-w-[540px]">
          helPRs creates Socratic comprehension sessions for every pull request — challenging both author and reviewer to prove they understand the code before it merges.
        </p>
        <div className="flex flex-col sm:flex-row items-start gap-5">
          <InstallCTA className="w-full sm:w-auto" />
          <span className="text-text-muted text-[14px] self-center">
            Set up in under a minute
          </span>
        </div>
      </Section>

      {/* How it works */}
      <Section className="py-20 md:py-28">
        <Divider />
        <Overline>How it works</Overline>
        <h2 className="text-[26px] md:text-[30px] font-semibold mb-14 font-mono" style={{ letterSpacing: '-0.02em' }}>
          Three steps to comprehension
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {STEPS.map((step) => (
            <div key={step.number}>
              <div className="mb-6">
                <Terminal>{step.terminal}</Terminal>
              </div>
              <div className="flex items-baseline gap-3 mb-2">
                <span className="text-accent text-[28px] font-bold leading-none font-mono">{step.number}</span>
                <h3 className="text-[16px] font-semibold font-mono" style={{ letterSpacing: '-0.01em' }}>{step.title}</h3>
              </div>
              <p className="text-text-secondary text-[15px] leading-[1.65]">{step.description}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* BYOK / Privacy */}
      <Section className="py-20 md:py-28">
        <Divider />
        <Overline>Privacy-first</Overline>
        <h2 className="text-[26px] md:text-[30px] font-semibold mb-14 font-mono" style={{ letterSpacing: '-0.02em' }}>
          Your keys, your data, your control
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {BYOK_ITEMS.map((item) => (
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

      {/* Problem statement */}
      <Section className="py-20 md:py-28">
        <Divider />
        <div className="md:flex md:items-start md:gap-14">
          <div className="md:flex-1 mb-10 md:mb-0">
            <Overline>The problem</Overline>
            <h2 className="text-[26px] md:text-[30px] font-semibold mb-7 font-mono" style={{ letterSpacing: '-0.02em' }}>
              Comprehension debt is the new tech debt
            </h2>
            <div className="space-y-5 text-text-secondary text-[15px] leading-[1.65]">
              <p>
                AI generates code 5-7x faster than developers understand it.
                The gap between shipping speed and comprehension is growing every quarter.
              </p>
              <p>
                helPRs is the only tool that asks: does the person merging this PR actually understand what it does?
              </p>
            </div>
          </div>
          <div className="md:w-[300px] p-7" style={CARD}>
            <p
              className="text-text-muted text-[12px] uppercase font-medium mb-6"
              style={{ letterSpacing: '0.12em' }}
            >
              Why it matters
            </p>
            <div className="space-y-0">
              <div className="pb-5">
                <p className="text-accent text-[28px] font-bold font-mono" style={{ letterSpacing: '-0.02em' }}>5-7x</p>
                <p className="text-text-secondary text-[14px] leading-[1.55] mt-1">faster code generation than comprehension</p>
              </div>
              <div className="py-5" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <p className="text-text-primary text-[28px] font-bold font-mono" style={{ letterSpacing: '-0.02em' }}>2 roles</p>
                <p className="text-text-secondary text-[14px] leading-[1.55] mt-1">both author and reviewer are challenged</p>
              </div>
              <div className="pt-5" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <p className="text-success text-[28px] font-bold font-mono" style={{ letterSpacing: '-0.02em' }}>Private</p>
                <p className="text-text-secondary text-[14px] leading-[1.55] mt-1">scores visible only to you — empowerment, not surveillance</p>
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* Bottom CTA */}
      <Section className="py-24 md:py-36 text-center">
        <Divider />
        <h2 className="text-[28px] md:text-[34px] font-semibold mb-5 font-mono" style={{ letterSpacing: '-0.02em' }}>
          Start understanding your code
        </h2>
        <p className="text-text-secondary text-[17px] mb-12 leading-[1.65]">
          Install on your GitHub org in under a minute.
        </p>
        <InstallCTA className="w-full sm:w-auto" />
      </Section>

      {/* Footer */}
      <footer className="w-full px-6 py-10" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div className="max-w-[960px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-text-muted text-[13px]">
          <span className="text-text-secondary font-medium font-mono" style={{ letterSpacing: '-0.01em' }}>helPRs</span>
          <div className="flex gap-6">
            <a
              href="https://github.com/mariuspruvot/helprs"
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
