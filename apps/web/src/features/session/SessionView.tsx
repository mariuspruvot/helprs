/**
 * SessionView — entry point for a PR session.
 *
 * Routes: /session/:installationId/:repoFullName/:prNumber
 *
 * Phase 1: SkillSelector — user picks which skill to run.
 * Phase 2: ContainerSession — container runs the skill, output streams.
 */

import { useCallback, useState } from 'react'
import { useParams } from 'react-router'
import ContainerSession from './ContainerSession'
import SkillSelector from './SkillSelector'

export default function SessionView() {
  const { installationId, '*': repoFullNameAndPr } = useParams<{
    installationId: string
    '*': string
  }>()

  // Parse the wildcard: "owner/repo/42" -> repoFullName="owner/repo", prNumber=42
  const segments = (repoFullNameAndPr ?? '').split('/')
  const prNumber = parseInt(segments.pop() ?? '0', 10)
  const repoFullName = segments.join('/')

  const [selectedSkill, setSelectedSkill] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const handleSelectSkill = useCallback((skillName: string) => {
    setCreating(true)
    setSelectedSkill(skillName)
  }, [])

  const handleBack = useCallback(() => {
    setSelectedSkill(null)
    setCreating(false)
  }, [])

  if (!installationId || !repoFullName || !prNumber) {
    return (
      <div className="min-h-screen bg-primary text-text-primary font-mono flex items-center justify-center px-6">
        <div className="max-w-md text-center space-y-4">
          <h1 className="text-[16px] font-bold">Invalid session link</h1>
          <p className="text-[14px] text-text-secondary">
            This session link is malformed. Check the URL and try again.
          </p>
        </div>
      </div>
    )
  }

  if (selectedSkill) {
    return (
      <ContainerSession
        installationId={installationId}
        repoFullName={repoFullName}
        prNumber={prNumber}
        skillName={selectedSkill}
        onBack={handleBack}
      />
    )
  }

  return (
    <SkillSelector
      repoFullName={repoFullName}
      prNumber={prNumber}
      onSelectSkill={handleSelectSkill}
      disabled={creating}
    />
  )
}
