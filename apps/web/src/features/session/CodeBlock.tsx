/**
 * CodeBlock — syntax-highlighted fenced code block with copy button.
 *
 * Uses shiki for VS Code-quality highlighting. Falls back to plain
 * monospace for unknown languages. Special handling for `diff` language
 * with line-level +/- coloring.
 */

import { useCallback, useState } from 'react'
import { highlighter, SHIKI_THEME, SUPPORTED_LANGS } from './shiki'

interface CodeBlockProps {
  code: string
  language?: string
}

function DiffBlock({ code }: { code: string }) {
  const lines = code.split('\n')
  return (
    <div className="text-[13px] font-mono leading-relaxed overflow-x-auto">
      {lines.map((line, i) => {
        let style: React.CSSProperties = { color: '#E0E0E0' }
        if (line.startsWith('+') && !line.startsWith('+++')) {
          style = { color: '#3fb950', background: 'rgba(46, 160, 67, 0.12)' }
        } else if (line.startsWith('-') && !line.startsWith('---')) {
          style = { color: '#f85149', background: 'rgba(248, 81, 73, 0.12)' }
        } else if (line.startsWith('@@')) {
          style = { color: '#8b949e', background: 'rgba(139, 148, 158, 0.08)' }
        }
        return (
          <div key={i} className="whitespace-pre px-3" style={style}>
            {line}
          </div>
        )
      })}
    </div>
  )
}

export default function CodeBlock({ code, language }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [code])

  const isDiff = language === 'diff'
  const lang = language?.toLowerCase() ?? ''
  const canHighlight = !isDiff && SUPPORTED_LANGS.has(lang)

  return (
    <div
      className="my-3 rounded-lg border overflow-hidden"
      style={{
        borderColor: 'rgba(255, 255, 255, 0.06)',
        background: '#1a1717',
      }}
    >
      {/* Header: language label + copy button */}
      <div
        className="flex items-center justify-between px-3 py-1.5 border-b"
        style={{
          borderColor: 'rgba(255, 255, 255, 0.06)',
          background: 'rgba(255, 255, 255, 0.02)',
        }}
      >
        <span className="text-[11px] font-mono" style={{ color: '#6e6e73' }}>
          {language ?? 'text'}
        </span>
        <button
          onClick={handleCopy}
          className="text-[11px] font-mono px-1.5 py-0.5 rounded transition-colors cursor-pointer hover:bg-white/5"
          style={{ color: copied ? '#30d158' : '#6e6e73' }}
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>

      {/* Code content */}
      <div className="overflow-x-auto">
        {isDiff ? (
          <DiffBlock code={code} />
        ) : canHighlight ? (
          <div
            className="text-[13px] leading-relaxed [&_pre]:!bg-transparent [&_pre]:!m-0 [&_pre]:!p-3 [&_code]:!bg-transparent"
            dangerouslySetInnerHTML={{
              __html: highlighter.codeToHtml(code, { lang, theme: SHIKI_THEME }),
            }}
          />
        ) : (
          <pre className="text-[13px] font-mono leading-relaxed p-3 overflow-x-auto whitespace-pre" style={{ color: '#E0E0E0' }}>
            <code>{code}</code>
          </pre>
        )}
      </div>
    </div>
  )
}
