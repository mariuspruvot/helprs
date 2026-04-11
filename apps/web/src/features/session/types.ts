// Hand-synced with backend Pydantic schema:
//   apps/api/src/helprs/modules/comprehension/presentation/schemas.py :: SessionResponse
// TODO: delete this file once the openapi-typescript `make types` pipeline lands
// (architecture.md line 765).

export type SessionRole = 'author' | 'reviewer'
export type SessionStatus = 'pending' | 'active' | 'completed'

/**
 * Story 3.4: per-question progress entry returned in `SessionResponse.progress`.
 * Drives the frontend's resume-from-reload UX. The verbatim text is
 * intentionally absent — FR35/NFR14 means we cannot show past content
 * on resume; the frontend renders past cycles as compact "(text not
 * retained)" placeholders.
 */
export interface QuestionProgress {
  number: number
  status: 'answered' | 'in_flight'
  topic: string
}

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
  /** Story 3.4: per-question progress for the resume-from-reload UX. */
  progress: QuestionProgress[]
}

// Story 3.3: chat message types for the streaming ChatPanel.
// Story 3.4: extended with user_answer + ai_feedback variants.

export type ChatMessageKind =
  | 'ai_question'
  | 'ai_question_streaming'
  | 'user_answer'
  | 'ai_feedback'
  | 'ai_feedback_streaming'

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

/**
 * Story 3.4: shape of the `event: feedback` SSE frame payload.
 * `score` and `gaps` are placeholders Story 4.1 will populate.
 * Story 3.4 D2 (code-review): the backend-side `code_refs` field
 * was deleted. Code-link detection is done in `ChatMessage.tsx`
 * from the rendered markdown, using `DiffFilePathsContext` to
 * filter against the actual diff.
 */
export interface FeedbackPayload {
  answer_id: string
  question_id: string
  text: string
  score: number | null
  gaps: string[]
}
