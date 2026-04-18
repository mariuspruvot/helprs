/**
 * SessionReplay — thin wrapper that loads a completed session for replay.
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router'
import { getContainerSession } from '../session/containerApi'
import type { ContainerSessionResponse } from '../session/containerTypes'
import ContainerSession from '../session/ContainerSession'

export default function SessionReplay() {
  const { installationId, sessionId } = useParams<{
    installationId: string
    sessionId: string
  }>()
  const navigate = useNavigate()
  const [sessionData, setSessionData] = useState<ContainerSessionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) return
    getContainerSession(sessionId)
      .then(setSessionData)
      .catch(() => setError('Failed to load session'))
  }, [sessionId])

  if (error) {
    return (
      <div className="min-h-screen bg-primary text-text-primary flex items-center justify-center">
        <div className="text-center">
          <p className="text-[14px] font-sans mb-4" style={{ color: '#ff6961' }}>{error}</p>
          <button
            onClick={() => navigate(`/installations/${installationId}`)}
            className="text-[13px] font-sans text-text-secondary hover:text-text-primary transition-colors cursor-pointer"
          >
            &larr; Back to sessions
          </button>
        </div>
      </div>
    )
  }

  if (!sessionData) {
    return (
      <div className="min-h-screen bg-primary text-text-primary flex items-center justify-center">
        <span className="text-text-muted text-[14px] font-sans">Loading session...</span>
      </div>
    )
  }

  return (
    <ContainerSession
      installationId={sessionData.installation_id}
      repoFullName={sessionData.repo_full_name}
      prNumber={sessionData.pr_number}
      skillName={sessionData.skill_name}
      onBack={() => navigate(`/installations/${installationId}`)}
      existingSessionId={sessionId}
    />
  )
}
