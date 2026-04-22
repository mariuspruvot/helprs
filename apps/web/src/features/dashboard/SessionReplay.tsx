/**
 * SessionReplay — thin wrapper that loads a completed session for replay.
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router'
import { getContainerSession } from '../session/containerApi'
import type { ContainerSessionResponse } from '../session/containerTypes'
import ContainerSession from '../session/ContainerSession'
import { Dot } from '../../shared/components'

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
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <p className="text-danger text-sm font-sans mb-4">{error}</p>
          <button
            onClick={() => navigate(`/installations/${installationId}`)}
            className="text-dim text-sm font-mono hover:text-ink2 transition-colors cursor-pointer"
          >
            {'\u2190'} Back to sessions
          </button>
        </div>
      </div>
    )
  }

  if (!sessionData) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="text-dim text-sm font-mono">
          <Dot pulse className="mr-2" /> Loading session...
        </span>
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
