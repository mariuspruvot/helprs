import { useCodeLinkActions } from './codeLinkContext'

interface CodeLinkProps {
  file: string
  line: number
}

/**
 * Story 3.4: an inline accent-blue button that scrolls the
 * `DiffViewer` to a specific `(file, line)` when clicked.
 *
 * Replaces the inline ``<code>`` rendering of `path:line` substrings
 * inside feedback messages. Hover triggers a hover preview on the
 * target line; click scrolls + highlights for ~1.5 s.
 *
 * Styling intentionally inline so a missing CSS variable cannot turn
 * the button into invisible text — UX-DR6 specifies the exact accent
 * blue and font weight.
 */
export default function CodeLink({ file, line }: CodeLinkProps) {
  const { scrollTo, preview, clearPreview } = useCodeLinkActions()
  const label = `${file}:${line}`
  return (
    <button
      type="button"
      data-testid={`code-link-${file}-${line}`}
      onClick={() => scrollTo(file, line)}
      onMouseEnter={() => preview(file, line)}
      onMouseLeave={() => clearPreview()}
      onFocus={() => preview(file, line)}
      onBlur={() => clearPreview()}
      aria-label={`Jump to ${file} line ${line}`}
      style={{
        color: '#007aff',
        fontWeight: 500,
        background: 'none',
        border: 'none',
        padding: 0,
        margin: 0,
        cursor: 'pointer',
        fontFamily: 'inherit',
        fontSize: 'inherit',
        textDecoration: 'underline dotted',
        textUnderlineOffset: 2,
      }}
    >
      <code style={{ background: 'none', padding: 0, color: '#007aff' }}>{label}</code>
    </button>
  )
}
