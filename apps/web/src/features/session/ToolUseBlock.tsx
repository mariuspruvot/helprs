/**
 * ToolUseBlock — collapsible display for tool_use + optional tool_result.
 *
 * Shows the tool name in a compact header. Expands to show arguments
 * and (if paired) the result.
 */

import type { ContentBlockData } from './containerTypes'

/** Friendly labels for common Claude Code tools. */
const TOOL_LABELS: Record<string, string> = {
  Read: 'Read file',
  Write: 'Write file',
  Edit: 'Edit file',
  Bash: 'Run command',
  Grep: 'Search',
  Glob: 'Find files',
  Agent: 'Sub-agent',
  WebFetch: 'Fetch URL',
  WebSearch: 'Web search',
}

function formatToolLabel(name: string, input: Record<string, unknown> | undefined): string {
  const label = TOOL_LABELS[name] ?? name
  // Add context from input when useful
  if (name === 'Read' && typeof input?.file_path === 'string') {
    const path = input.file_path as string
    const filename = path.split('/').pop() ?? path
    return `${label}: ${filename}`
  }
  if (name === 'Bash' && typeof input?.command === 'string') {
    const cmd = (input.command as string).slice(0, 60)
    return `${label}: ${cmd}${(input.command as string).length > 60 ? '...' : ''}`
  }
  if (name === 'Grep' && typeof input?.pattern === 'string') {
    return `${label}: ${input.pattern}`
  }
  if (name === 'Edit' && typeof input?.file_path === 'string') {
    const path = input.file_path as string
    const filename = path.split('/').pop() ?? path
    return `${label}: ${filename}`
  }
  return label
}

interface ToolUseBlockProps {
  block: ContentBlockData
  result?: ContentBlockData
}

export default function ToolUseBlock({ block, result }: ToolUseBlockProps) {
  const label = formatToolLabel(block.name ?? 'unknown', block.input)

  return (
    <details
      className="my-2 rounded-lg border overflow-hidden"
      style={{
        borderColor: 'rgba(255, 255, 255, 0.06)',
        background: 'rgba(255, 255, 255, 0.02)',
      }}
    >
      <summary
        className="cursor-pointer select-none px-3 py-2 text-[12px] font-mono flex items-center gap-2"
        style={{ color: '#9a9898' }}
      >
        <span
          className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: result?.is_error ? '#ff3b30' : '#E2A039' }}
        />
        {label}
      </summary>

      <div
        className="border-t px-3 py-2 space-y-2"
        style={{ borderColor: 'rgba(255, 255, 255, 0.06)' }}
      >
        {/* Tool arguments */}
        {block.input && Object.keys(block.input).length > 0 && (
          <pre
            className="text-[12px] font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap"
            style={{ color: '#9a9898' }}
          >
            {JSON.stringify(block.input, null, 2)}
          </pre>
        )}

        {/* Tool result */}
        {result && (
          <div
            className="border-t pt-2"
            style={{ borderColor: 'rgba(255, 255, 255, 0.04)' }}
          >
            <div
              className="text-[11px] font-mono mb-1"
              style={{ color: result.is_error ? '#ff6961' : '#6e6e73' }}
            >
              {result.is_error ? 'Error' : 'Result'}
            </div>
            <pre
              className="text-[12px] font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap max-h-[300px] overflow-y-auto"
              style={{ color: result.is_error ? '#ff6961' : '#E0E0E0' }}
            >
              {result.content ?? '(empty)'}
            </pre>
          </div>
        )}
      </div>
    </details>
  )
}
