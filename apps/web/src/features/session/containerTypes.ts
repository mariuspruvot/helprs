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

export interface SessionEventItem {
  event_id: number
  data: Record<string, unknown>
  created_at: string
}

export interface SessionEventsListResponse {
  session_id: string
  events: SessionEventItem[]
  total: number
}

export interface Skill {
  name: string
  label: string
  description: string
  duration: string
}

// ---------------------------------------------------------------------------
// Stream message model — structured representation of Claude Code events
// ---------------------------------------------------------------------------

export interface ContentBlockData {
  type: 'text' | 'thinking' | 'tool_use' | 'tool_result'
  text?: string
  name?: string           // tool_use: tool name (e.g. "Read", "Bash", "Grep")
  input?: Record<string, unknown>  // tool_use: arguments
  content?: string        // tool_result: output text
  is_error?: boolean      // tool_result: whether the tool errored
  tool_use_id?: string    // tool_result: links back to the tool_use
}

export interface StreamMessage {
  id: number
  timestamp: number
  role: 'assistant' | 'user' | 'system' | 'result'
  blocks: ContentBlockData[]
  // System-specific
  subtype?: string
  // Result-specific
  isError?: boolean
  totalCostUsd?: number
  numTurns?: number
  durationMs?: number
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
  name?: string
  input?: Record<string, unknown>
  tool_use_id?: string
  content?: string | Array<{ type: string; text?: string }>
  is_error?: boolean
}

interface AssistantEvent {
  type: 'assistant'
  message: { content: ContentBlock[] }
}

interface UserEvent {
  type: 'user'
  message?: { content: ContentBlock[] }
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
  | UserEvent
  | { type: 'rate_limit_event' }
  | { type: 'stream_event' }
  | { type: string }

/**
 * Parse a Claude Code stream-json line into a structured StreamMessage.
 *
 * Returns null for events that should be hidden (init, compact_boundary,
 * rate_limit_event, stream_event, unknown types).
 *
 * The result event's `result` field duplicates the last assistant text —
 * only surface errors or session-end metadata, never the text.
 */
export function parseStreamMessage(raw: string): Omit<StreamMessage, 'id' | 'timestamp'> | null {
  let event: StreamJsonEvent
  try {
    event = JSON.parse(raw) as StreamJsonEvent
  } catch {
    // Not JSON — Docker log frame fragments or entrypoint plumbing.
    return null
  }

  switch (event.type) {
    case 'assistant': {
      const content = (event as AssistantEvent).message?.content ?? []
      const blocks: ContentBlockData[] = []

      for (const block of content) {
        // Only extract text blocks — tool_use and thinking are internal
        // activity that we don't display to users.
        if (block.type === 'text' && typeof block.text === 'string') {
          blocks.push({ type: 'text', text: block.text })
        }
      }

      if (blocks.length === 0) return null
      return { role: 'assistant', blocks }
    }

    // user events are tool_result blocks (internal activity) — hide them
    case 'user':
      return null

    case 'system': {
      const sys = event as SystemEvent
      if (sys.subtype === 'api_retry') {
        const msg = `API retry (attempt ${sys.attempt ?? '?'}/${sys.max_retries ?? '?'})`
        return {
          role: 'system',
          blocks: [{ type: 'text', text: msg }],
          subtype: 'api_retry',
        }
      }
      // init, compact_boundary, plugin_install — hide
      return null
    }

    case 'result': {
      const res = event as ResultEvent
      if (res.is_error) {
        return {
          role: 'result',
          blocks: [{ type: 'text', text: 'Session ended with error' }],
          isError: true,
          totalCostUsd: res.total_cost_usd,
          numTurns: res.num_turns,
          durationMs: res.duration_ms,
        }
      }
      // Success — only emit if we have metadata to show
      if (res.num_turns !== undefined || res.duration_ms !== undefined) {
        return {
          role: 'result',
          blocks: [],
          isError: false,
          totalCostUsd: res.total_cost_usd,
          numTurns: res.num_turns,
          durationMs: res.duration_ms,
        }
      }
      return null
    }

    // rate_limit_event, stream_event, unknown — hide
    default:
      return null
  }
}

/**
 * Parse a persisted event (already-parsed JSONB) into a StreamMessage.
 * Re-serializes to JSON and delegates to {@link parseStreamMessage}.
 */
export function parseStoredMessage(data: Record<string, unknown>): Omit<StreamMessage, 'id' | 'timestamp'> | null {
  return parseStreamMessage(JSON.stringify(data))
}
