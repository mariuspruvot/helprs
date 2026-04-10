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
  diff: string
  created_at: string
  updated_at: string
}
