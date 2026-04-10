// Hand-synced with backend Pydantic schema:
//   apps/api/src/helprs/modules/comprehension/presentation/schemas.py :: SessionResponse
// TODO: delete this file once the openapi-typescript `make types` pipeline lands
// (architecture.md line 765).

export type SessionRole = 'author' | 'reviewer'
export type SessionStatus = 'pending' | 'active' | 'completed'

export interface SessionResponse {
  id: string
  repo_full_name: string
  repo_owner: string
  repo_name: string
  pr_number: number
  pr_title: string
  role: SessionRole
  status: SessionStatus
  question_count: number
  /**
   * Story 3.3: number of questions this session plans to ask.
   * Set at session creation by `estimate_question_count`; zero on
   * legacy rows created before the migration (the SSE endpoint falls
   * back to 5 in that case).
   */
  total_questions: number
  diff: string
  created_at: string
  updated_at: string
}

// Story 3.3: chat message types for the streaming ChatPanel.

export type ChatMessageKind = 'ai_question' | 'ai_question_streaming'

export interface ChatMessage {
  id: string
  kind: ChatMessageKind
  questionNumber: number
  total: number
  text: string
  fileRefs: string[]
  createdAt: string
  isStreaming: boolean
}

/**
 * Shape of the `event: question` SSE frame payload from the backend.
 * Kept snake_case to mirror the wire format so no intermediate mapping
 * is needed in the SSE hook.
 */
export interface QuestionPayload {
  question_id: string
  text: string
  number: number
  total: number
  file_refs: string[]
}
