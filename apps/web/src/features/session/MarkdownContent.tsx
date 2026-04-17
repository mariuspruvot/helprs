/**
 * MarkdownContent — renders markdown text as rich React components.
 *
 * Uses react-markdown with remark-gfm for GitHub-flavored markdown.
 * Overrides code blocks with our CodeBlock component (shiki highlighting).
 */

import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import CodeBlock from './CodeBlock'
import type { Components } from 'react-markdown'

const components: Components = {
  // Fenced code blocks and inline code
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className ?? '')
    const codeString = String(children).replace(/\n$/, '')

    // Fenced code block: has a language class from the ``` fence
    // react-markdown wraps fenced blocks in <pre><code class="language-X">
    // We detect this via the className and replace with our CodeBlock.
    if (match) {
      return <CodeBlock code={codeString} language={match[1]} />
    }

    // Inline code
    return (
      <code
        className="text-[13px] font-mono px-1.5 py-0.5 rounded"
        style={{ background: 'rgba(255, 255, 255, 0.06)', color: '#E0E0E0' }}
        {...props}
      >
        {children}
      </code>
    )
  },

  // Unwrap <pre> since CodeBlock handles its own container
  pre({ children }) {
    return <>{children}</>
  },

  // Headings
  h1({ children }) {
    return (
      <h1 className="text-[22px] font-semibold font-sans mt-6 mb-3" style={{ color: '#fdfcfc' }}>
        {children}
      </h1>
    )
  },
  h2({ children }) {
    return (
      <h2
        className="text-[18px] font-semibold font-sans mt-5 mb-2 pb-1 border-b"
        style={{ color: '#fdfcfc', borderColor: 'rgba(255, 255, 255, 0.06)' }}
      >
        {children}
      </h2>
    )
  },
  h3({ children }) {
    return (
      <h3 className="text-[15px] font-semibold font-sans mt-4 mb-2" style={{ color: '#fdfcfc' }}>
        {children}
      </h3>
    )
  },

  // Paragraphs
  p({ children }) {
    return (
      <p className="text-[14px] font-sans leading-relaxed my-2" style={{ color: '#E0E0E0' }}>
        {children}
      </p>
    )
  },

  // Links
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="underline underline-offset-2 transition-colors hover:text-accent"
        style={{ color: '#E2A039' }}
      >
        {children}
      </a>
    )
  },

  // Lists
  ul({ children }) {
    return <ul className="text-[14px] font-sans my-2 ml-5 list-disc space-y-1">{children}</ul>
  },
  ol({ children }) {
    return <ol className="text-[14px] font-sans my-2 ml-5 list-decimal space-y-1">{children}</ol>
  },
  li({ children }) {
    return <li className="leading-relaxed" style={{ color: '#E0E0E0' }}>{children}</li>
  },

  // Blockquotes
  blockquote({ children }) {
    return (
      <blockquote
        className="my-3 pl-3 border-l-2"
        style={{ borderColor: '#E2A039', color: '#9a9898' }}
      >
        {children}
      </blockquote>
    )
  },

  // Tables
  table({ children }) {
    return (
      <div className="my-3 overflow-x-auto">
        <table className="text-[13px] font-sans border-collapse w-full">{children}</table>
      </div>
    )
  },
  thead({ children }) {
    return (
      <thead style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
        {children}
      </thead>
    )
  },
  th({ children }) {
    return (
      <th
        className="text-left px-3 py-1.5 font-medium"
        style={{ color: '#fdfcfc' }}
      >
        {children}
      </th>
    )
  },
  td({ children }) {
    return (
      <td
        className="px-3 py-1.5 border-t"
        style={{ borderColor: 'rgba(255, 255, 255, 0.04)', color: '#E0E0E0' }}
      >
        {children}
      </td>
    )
  },

  // Horizontal rule
  hr() {
    return <hr className="my-4 border-0 h-px" style={{ background: 'rgba(255, 255, 255, 0.06)' }} />
  },

  // Strong and emphasis
  strong({ children }) {
    return <strong className="font-semibold" style={{ color: '#fdfcfc' }}>{children}</strong>
  },
  em({ children }) {
    return <em style={{ color: '#E0E0E0' }}>{children}</em>
  },
}

interface MarkdownContentProps {
  text: string
}

export default function MarkdownContent({ text }: MarkdownContentProps) {
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={components}>
      {text}
    </Markdown>
  )
}
