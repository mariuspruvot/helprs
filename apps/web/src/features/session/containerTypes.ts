/**
 * Types for the container-based skill execution flow.
 * Hand-synced with backend schemas:
 *   apps/api/src/helprs/modules/container/schemas.py
 */

export interface ContainerSessionRequest {
  installation_id: string
  pr_number: number
  repo_full_name: string
  skill_name: string
}

export interface ContainerSessionResponse {
  id: string
  installation_id: string
  user_id: string | null
  pr_number: number
  repo_full_name: string
  skill_name: string
  container_id: string | null
  status: ContainerStatus
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export type ContainerStatus = 'pending' | 'starting' | 'running' | 'completed' | 'failed' | 'stopped'

export interface StopSessionResponse {
  id: string
  status: string
  message: string
}

export interface Skill {
  name: string
  label: string
  description: string
  duration: string
}

export interface TerminalLine {
  id: number
  text: string
  timestamp: number
  kind?: 'text' | 'error' | 'status'
}

// ---------------------------------------------------------------------------
// Claude Code stream-json protocol (NDJSON, one JSON object per line)
//
// Without --include-partial-messages (our config), 5 top-level event types:
//
//   system     — lifecycle: init, api_retry, compact_boundary, plugin_install
//   assistant  — one event per content block (thinking, text, tool_use).
//                Each block is a separate event sharing the same message.id.
//   user       — tool_result blocks and user input
//   result     — final event; result field duplicates the last assistant text
//   rate_limit_event — rate limit info
//
// With --include-partial-messages, a 6th type appears:
//   stream_event — raw Claude API deltas (content_block_delta, etc.)
//
// See: https://code.claude.com/docs/en/headless (Stream responses)
//      https://code.claude.com/docs/en/agent-sdk/streaming-output
// ---------------------------------------------------------------------------

interface ContentBlock {
  type: string
  text?: string
}

interface AssistantEvent {
  type: 'assistant'
  message: { content: ContentBlock[] }
}

interface SystemEvent {
  type: 'system'
  subtype: string
  attempt?: number
  max_retries?: number
  error?: string
}

interface ResultEvent {
  type: 'result'
  subtype: string
  is_error: boolean
  result?: string
  total_cost_usd?: number
  num_turns?: number
  duration_ms?: number
}

type StreamJsonEvent =
  | AssistantEvent
  | SystemEvent
  | ResultEvent
  | { type: 'user' }
  | { type: 'rate_limit_event' }
  | { type: 'stream_event' }
  | { type: string }

/**
 * Parse a Claude Code stream-json line into displayable content.
 *
 * Returns null for events that should be hidden from the terminal.
 * The result event is used for session-end signaling only — its `result`
 * field duplicates the last assistant text and must NOT be displayed.
 */
export function parseStreamEvent(raw: string): { text: string; kind: TerminalLine['kind'] } | null {
  let event: StreamJsonEvent
  try {
    event = JSON.parse(raw) as StreamJsonEvent
  } catch {
    // Not JSON — Docker log frame fragments or entrypoint plumbing.
    return null
  }

  switch (event.type) {
    // Assistant content blocks — only display text blocks.
    // thinking and tool_use blocks are internal activity.
    case 'assistant': {
      const content = (event as AssistantEvent).message?.content ?? []
      const parts: string[] = []
      for (const block of content) {
        if (block.type === 'text' && typeof block.text === 'string') {
          parts.push(block.text)
        }
      }
      if (parts.length === 0) return null
      return { text: parts.join('\n'), kind: 'text' }
    }

    // System events — surface API retries so the user knows why it's slow.
    case 'system': {
      const sys = event as SystemEvent
      if (sys.subtype === 'api_retry') {
        const msg = `API retry (attempt ${sys.attempt ?? '?'}/${sys.max_retries ?? '?'})`
        return { text: msg, kind: 'status' }
      }
      // init, compact_boundary, plugin_install — hide
      return null
    }

    // Result event — session-end signal only.
    // The result.result field duplicates the last assistant text, so we
    // intentionally do NOT display it.  Only surface errors.
    case 'result': {
      const res = event as ResultEvent
      if (res.is_error) {
        return { text: 'Session ended with error', kind: 'error' }
      }
      // Success — no display (avoids duplicating the last assistant text)
      return null
    }

    // user, rate_limit_event, stream_event, unknown — hide
    default:
      return null
  }
}
