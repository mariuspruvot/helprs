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
}
