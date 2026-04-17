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
  kind?: 'text' | 'error' | 'user' | 'result'
}

/**
 * Parse a Claude Code stream-json line into displayable text.
 * Returns null for events that should be hidden (internal system events).
 */
export function parseStreamEvent(raw: string): { text: string; kind: TerminalLine['kind'] } | null {
  let event: Record<string, unknown>
  try {
    event = JSON.parse(raw)
  } catch {
    // Not JSON — suppress everything.  Non-JSON lines are either Docker
    // log frame fragments or entrypoint plumbing (git clone, branch
    // checkout, etc.).  Only the parsed conversation matters.
    return null
  }

  const type = event.type as string

  // Assistant text messages — only show text blocks (the conversation).
  // tool_use blocks are internal activity and should not be visible.
  if (type === 'assistant') {
    const message = event.message as Record<string, unknown> | undefined
    const content = (message?.content ?? []) as Array<Record<string, unknown>>
    const parts: string[] = []
    for (const block of content) {
      if (block.type === 'text' && typeof block.text === 'string') {
        parts.push(block.text)
      }
    }
    if (parts.length === 0) return null
    return { text: parts.join('\n'), kind: 'text' }
  }

  // Tool results (user turn with tool_result)
  if (type === 'user') {
    const message = event.message as Record<string, unknown> | undefined
    const content = (message?.content ?? []) as Array<Record<string, unknown>>
    for (const block of content) {
      if (block.type === 'tool_result') {
        // Don't show full tool results -- too verbose
        return null
      }
    }
    // Regular user message (e.g. the initial prompt)
    return null
  }

  // Final result
  if (type === 'result') {
    const result = event.result as string | undefined
    if (result) {
      return { text: result, kind: 'result' }
    }
    const isError = event.is_error as boolean
    if (isError) {
      return { text: `Session ended with error`, kind: 'error' }
    }
    return null
  }

  // System events — hide all (init, rate_limit, task_progress, etc.)
  if (type === 'system') return null

  // Rate limit events -- hide
  if (type === 'rate_limit_event') return null

  // Hide all other internal/unknown event types (tool_use, tool_result,
  // content_block_start/delta/stop, message_start/delta/stop, etc.)
  // Only explicitly handled types above should reach the terminal.
  return null
}
