import { useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import { apiFetch } from '../../shared/api/client'

type SetupStep = 'api-key' | 'labels' | 'complete'

interface BYOKResult {
  key_hint: string
  key_status: string
  validated_at: string
}

const DEFAULT_LABELS = ['hotfix', 'urgent', 'trivial']

export default function SetupView() {
  const { installationId } = useParams<{ installationId: string }>()
  const navigate = useNavigate()
  const [step, setStep] = useState<SetupStep>('api-key')
  const [apiKey, setApiKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [byokResult, setByokResult] = useState<BYOKResult | null>(null)
  const [labels, setLabels] = useState<string[]>(DEFAULT_LABELS)
  const [newLabel, setNewLabel] = useState('')

  const submitApiKey = async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await apiFetch(`/api/v1/installations/${installationId}/byok`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey }),
      })
      if (!resp.ok) {
        const data = await resp.json() as { message?: string }
        setError(data.message ?? 'API key validation failed -- check your key and try again')
        return
      }
      const data = await resp.json() as BYOKResult
      setByokResult(data)
      setStep('labels')
    } finally {
      setLoading(false)
    }
  }

  const [labelError, setLabelError] = useState<string | null>(null)

  const saveLabels = async () => {
    setLoading(true)
    setLabelError(null)
    try {
      const resp = await apiFetch(`/api/v1/installations/${installationId}/suppression-labels`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ labels }),
      })
      if (!resp.ok) {
        const data = await resp.json() as { message?: string }
        setLabelError(data.message ?? 'Failed to save suppression labels')
        return
      }
      setStep('complete')
    } finally {
      setLoading(false)
    }
  }

  const addLabel = () => {
    const trimmed = newLabel.trim()
    if (!trimmed || labels.includes(trimmed)) {
      setNewLabel('')
      return
    }
    if (labels.length >= 20) {
      setLabelError('Maximum 20 labels allowed')
      setNewLabel('')
      return
    }
    if (trimmed.length > 50) {
      setLabelError('Label must be 50 characters or less')
      setNewLabel('')
      return
    }
    if (!/^[a-zA-Z0-9-]+$/.test(trimmed)) {
      setLabelError('Only alphanumeric characters and hyphens allowed')
      setNewLabel('')
      return
    }
    setLabelError(null)
    setLabels([...labels, trimmed])
    setNewLabel('')
  }

  const removeLabel = (label: string) => {
    setLabels(labels.filter((l) => l !== label))
  }

  return (
    <div className="min-h-screen bg-primary text-text-primary font-mono flex items-center justify-center p-6">
      <div className="max-w-lg w-full space-y-8">
        <div className="text-center">
          <h1 className="text-[28px] font-bold">helPRs Setup</h1>
          <p className="text-text-secondary mt-2">Configure your installation</p>
        </div>

        {step === 'api-key' && (
          <div className="space-y-4">
            <h2 className="text-[20px] font-semibold">1. Anthropic API Key</h2>
            <p className="text-text-secondary text-[14px]">
              Paste your Anthropic API key. It will be encrypted at rest.
            </p>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-ant-api03-..."
              className="w-full px-4 py-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-surface)] text-text-primary focus:outline-none focus:border-[var(--accent)]"
            />
            {error && (
              <p className="text-[var(--warning)] text-[14px]">{error}</p>
            )}
            <button
              onClick={submitApiKey}
              disabled={loading || !apiKey.startsWith('sk-ant-')}
              className="w-full py-3 rounded-lg bg-[var(--accent)] text-white font-semibold disabled:opacity-50 hover:opacity-90 transition-opacity"
            >
              {loading ? 'Validating...' : 'Save API Key'}
            </button>
          </div>
        )}

        {step === 'labels' && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-[var(--success)]">
              <span>&#10003;</span>
              <span>Key saved, encrypted at rest</span>
            </div>

            <h2 className="text-[20px] font-semibold">2. Suppression Labels (optional)</h2>
            <p className="text-text-secondary text-[14px]">
              PRs with these labels will skip helPRs sessions. Defaults are pre-filled.
            </p>
            <div className="flex flex-wrap gap-2">
              {labels.map((label) => (
                <span
                  key={label}
                  className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-[var(--color-surface)] text-[14px]"
                >
                  {label}
                  <button
                    onClick={() => removeLabel(label)}
                    className="text-text-secondary hover:text-[var(--warning)] ml-1"
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addLabel()}
                placeholder="Add label..."
                className="flex-1 px-4 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-surface)] text-text-primary focus:outline-none focus:border-[var(--accent)]"
              />
              <button
                onClick={addLabel}
                className="px-4 py-2 rounded-lg bg-[var(--color-surface)] hover:opacity-80"
              >
                Add
              </button>
            </div>
            {labelError && (
              <p className="text-[var(--warning)] text-[14px]">{labelError}</p>
            )}
            <div className="flex gap-3 pt-2">
              <button
                onClick={saveLabels}
                disabled={loading}
                className="flex-1 py-3 rounded-lg bg-[var(--accent)] text-white font-semibold disabled:opacity-50 hover:opacity-90 transition-opacity"
              >
                {loading ? 'Saving...' : 'Continue'}
              </button>
              <button
                onClick={() => setStep('complete')}
                className="px-6 py-3 rounded-lg bg-[var(--color-surface)] text-text-secondary hover:opacity-80"
              >
                Skip
              </button>
            </div>
          </div>
        )}

        {step === 'complete' && (
          <div className="space-y-4 text-center">
            <div className="text-[var(--success)] text-[36px]">&#10003;</div>
            <h2 className="text-[20px] font-semibold">Setup Complete</h2>
            <div className="bg-[var(--color-surface)] rounded-lg p-4 text-left space-y-2 text-[14px]">
              {byokResult && (
                <>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">API Key</span>
                    <span className="text-[var(--success)]">{byokResult.key_status} ({byokResult.key_hint})</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Validated</span>
                    <span>{new Date(byokResult.validated_at).toLocaleDateString()}</span>
                  </div>
                </>
              )}
              <div className="flex justify-between">
                <span className="text-text-secondary">Suppression Labels</span>
                <span>{labels.join(', ') || 'None'}</span>
              </div>
            </div>
            <p className="text-text-secondary text-[14px]">
              Your next PR will trigger a helPRs session.
            </p>
            <button
              onClick={() => navigate(`/installations/${installationId}/settings`)}
              className="w-full py-3 rounded-lg bg-[var(--color-surface)] text-text-primary hover:opacity-80 transition-opacity"
            >
              Go to Settings
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
