import { useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import { apiFetch } from '../../shared/api/client'
import { Button, Card, Chip, Overline } from '../../shared/components'

type SetupStep = 'api-key' | 'labels' | 'complete'

interface BYOKResult {
  key_hint: string
  key_status: string
  validated_at: string
}

const DEFAULT_LABELS = ['hotfix', 'urgent', 'trivial']

const STEPS: { key: SetupStep; label: string }[] = [
  { key: 'api-key', label: '01 · Token' },
  { key: 'labels', label: '02 · Labels' },
  { key: 'complete', label: '03 · Done' },
]

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
  const [labelError, setLabelError] = useState<string | null>(null)

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

  const stepIndex = STEPS.findIndex((s) => s.key === step)

  return (
    <div className="max-w-lg mx-auto py-12">
      {/* Header */}
      <div className="mb-8">
        <Overline className="mb-2">{'\u25b8'} SETUP</Overline>
        <h1 className="font-mono text-2xl font-bold text-ink">helPRs Setup</h1>
        <p className="text-dim text-sm mt-1 font-sans">Configure your installation</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-3 mb-8">
        {STEPS.map((s, i) => (
          <div key={s.key} className="flex items-center gap-3">
            {i > 0 && <div className={`w-8 h-px ${i <= stepIndex ? 'bg-accent' : 'bg-rule'}`} />}
            <span
              className={`font-mono text-[11px] font-medium ${
                i < stepIndex ? 'text-ok' : i === stepIndex ? 'text-accent' : 'text-dim2'
              }`}
            >
              {i < stepIndex ? '\u2713 ' : ''}{s.label}
            </span>
          </div>
        ))}
      </div>

      {/* Step 1: API Key */}
      {step === 'api-key' && (
        <Card>
          <Overline className="mb-4">01 {'\u00b7'} Claude Token</Overline>
          <p className="text-ink2 text-sm font-sans mb-1">
            Paste your Claude OAuth token. It will be encrypted at rest.
          </p>
          <p className="text-dim text-xs font-mono mb-4">
            // generate one with: <span className="text-accent">claude setup-token</span>
          </p>

          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value.replace(/\s/g, ''))}
            placeholder="sk-ant-oat01-..."
            className="w-full px-4 py-3 rounded-button bg-bg border border-rule text-ink font-mono text-sm focus:outline-none focus:border-accent mb-4"
          />

          {error && <p className="text-danger text-sm mb-4">{error}</p>}

          <Button
            onClick={submitApiKey}
            disabled={loading || !apiKey.startsWith('sk-ant-')}
            className="w-full"
          >
            {loading ? 'Validating...' : 'Save Token'}
          </Button>
        </Card>
      )}

      {/* Step 2: Labels */}
      {step === 'labels' && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <span className="text-ok font-mono text-sm">{'\u2713'}</span>
            <span className="text-ok text-sm">Token saved, encrypted at rest</span>
          </div>

          <Overline className="mb-4">02 {'\u00b7'} Suppression Labels</Overline>
          <p className="text-ink2 text-sm font-sans mb-4">
            PRs with these labels will skip helPRs sessions. Defaults are pre-filled.
          </p>

          <div className="flex flex-wrap gap-2 mb-4">
            {labels.map((label) => (
              <Chip key={label}>
                {label}
                <button
                  onClick={() => removeLabel(label)}
                  className="text-dim hover:text-danger ml-1 cursor-pointer"
                >
                  &times;
                </button>
              </Chip>
            ))}
          </div>

          <div className="flex gap-2 mb-4">
            <input
              type="text"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addLabel()}
              placeholder="Add label..."
              className="flex-1 px-3 py-2 rounded-button bg-bg border border-rule text-ink font-mono text-sm focus:outline-none focus:border-accent"
            />
            <Button variant="secondary" onClick={addLabel}>Add</Button>
          </div>

          {labelError && <p className="text-danger text-sm mb-4">{labelError}</p>}

          <div className="flex gap-3">
            <Button onClick={saveLabels} disabled={loading} className="flex-1">
              {loading ? 'Saving...' : 'Continue'}
            </Button>
            <Button variant="ghost" onClick={() => setStep('complete')}>
              Skip
            </Button>
          </div>
        </Card>
      )}

      {/* Step 3: Complete */}
      {step === 'complete' && (
        <Card className="text-center">
          <div className="text-ok text-4xl mb-3">{'\u2713'}</div>
          <h2 className="font-mono text-lg font-bold text-ink mb-4">Setup Complete</h2>

          <div className="bg-bg rounded-[8px] border border-rule p-4 text-left space-y-2 mb-6">
            {byokResult && (
              <>
                <div className="flex justify-between text-sm">
                  <span className="text-dim font-mono">Token</span>
                  <span className="text-ok font-mono">{byokResult.key_status} ({byokResult.key_hint})</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-dim font-mono">Validated</span>
                  <span className="text-ink2 font-mono">{new Date(byokResult.validated_at).toLocaleDateString()}</span>
                </div>
              </>
            )}
            <div className="flex justify-between text-sm">
              <span className="text-dim font-mono">Labels</span>
              <span className="text-ink2 font-mono">{labels.join(', ') || 'None'}</span>
            </div>
          </div>

          <p className="text-dim text-xs font-mono mb-6">
            // your next PR will trigger a helPRs session
          </p>

          <Button
            variant="secondary"
            onClick={() => navigate(`/installations/${installationId}/settings`)}
            className="w-full"
          >
            Go to Settings
          </Button>
        </Card>
      )}
    </div>
  )
}
