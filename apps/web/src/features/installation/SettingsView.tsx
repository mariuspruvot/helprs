import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router'
import { apiFetch } from '../../shared/api/client'

interface InstallationDetail {
  id: string
  github_installation_id: number
  account_login: string
  account_type: string
  repository_selection: string
  byok_configured: boolean
  byok_key_hint: string | null
  byok_key_status: string | null
  byok_validated_at: string | null
  suppression_labels: string[]
}

export default function SettingsView() {
  const { installationId } = useParams<{ installationId: string }>()
  const [installation, setInstallation] = useState<InstallationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // BYOK update state
  const [showKeyInput, setShowKeyInput] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [keyLoading, setKeyLoading] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)
  const [keySuccess, setKeySuccess] = useState<string | null>(null)

  // Suppression labels state
  const [labels, setLabels] = useState<string[]>([])
  const [newLabel, setNewLabel] = useState('')
  const [labelsLoading, setLabelsLoading] = useState(false)
  const [labelsError, setLabelsError] = useState<string | null>(null)

  // Delete confirmation
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const fetchInstallation = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await apiFetch(`/api/v1/installations/${installationId}`)
      if (!resp.ok) {
        setError('Failed to load installation settings')
        return
      }
      const data = await resp.json() as InstallationDetail
      setInstallation(data)
      setLabels(data.suppression_labels)
    } finally {
      setLoading(false)
    }
  }, [installationId])

  useEffect(() => {
    fetchInstallation()
  }, [fetchInstallation])

  const updateApiKey = async () => {
    setKeyLoading(true)
    setKeyError(null)
    setKeySuccess(null)
    try {
      const resp = await apiFetch(`/api/v1/installations/${installationId}/byok`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey }),
      })
      if (!resp.ok) {
        const data = await resp.json() as { message?: string }
        setKeyError(data.message ?? 'API key validation failed -- check your key and try again')
        return
      }
      setKeySuccess('API key updated and encrypted at rest')
      setApiKey('')
      setShowKeyInput(false)
      await fetchInstallation()
    } finally {
      setKeyLoading(false)
    }
  }

  const deleteApiKey = async () => {
    setKeyLoading(true)
    try {
      await apiFetch(`/api/v1/installations/${installationId}/byok`, {
        method: 'DELETE',
      })
      setShowDeleteConfirm(false)
      await fetchInstallation()
    } finally {
      setKeyLoading(false)
    }
  }

  const saveLabels = async (updatedLabels: string[]) => {
    setLabelsLoading(true)
    setLabelsError(null)
    try {
      const resp = await apiFetch(`/api/v1/installations/${installationId}/suppression-labels`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ labels: updatedLabels }),
      })
      if (!resp.ok) {
        const data = await resp.json() as { message?: string }
        setLabelsError(data.message ?? 'Failed to save labels')
        return
      }
      setLabels(updatedLabels)
    } finally {
      setLabelsLoading(false)
    }
  }

  const addLabel = () => {
    const trimmed = newLabel.trim()
    if (!trimmed || labels.includes(trimmed)) {
      setNewLabel('')
      return
    }
    if (labels.length >= 20) {
      setLabelsError('Maximum 20 labels allowed')
      setNewLabel('')
      return
    }
    if (trimmed.length > 50) {
      setLabelsError('Label must be 50 characters or less')
      setNewLabel('')
      return
    }
    if (!/^[a-zA-Z0-9-]+$/.test(trimmed)) {
      setLabelsError('Only alphanumeric characters and hyphens allowed')
      setNewLabel('')
      return
    }
    setLabelsError(null)
    const updated = [...labels, trimmed]
    setLabels(updated)
    saveLabels(updated)
    setNewLabel('')
  }

  const removeLabel = (label: string) => {
    const updated = labels.filter((l) => l !== label)
    setLabels(updated)
    saveLabels(updated)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-primary text-text-primary font-mono flex items-center justify-center">
        <p className="text-text-secondary">Loading settings...</p>
      </div>
    )
  }

  if (error || !installation) {
    return (
      <div className="min-h-screen bg-primary text-text-primary font-mono flex items-center justify-center">
        <p className="text-[var(--warning)]">{error ?? 'Installation not found'}</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-primary text-text-primary font-mono p-6">
      <div className="max-w-2xl mx-auto space-y-8">
        <div>
          <h1 className="text-[28px] font-bold">Installation Settings</h1>
          <p className="text-text-secondary mt-1">
            {installation.account_login} ({installation.account_type})
          </p>
        </div>

        {/* BYOK Section */}
        <section className="bg-[var(--color-surface)] rounded-lg p-6 space-y-4">
          <h2 className="text-[18px] font-semibold">Anthropic API Key</h2>

          {installation.byok_configured ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-[14px]">
                <span className="text-text-secondary">Key</span>
                <span className="text-[var(--success)]">
                  {installation.byok_key_status} ({installation.byok_key_hint})
                </span>
              </div>
              {installation.byok_validated_at && (
                <div className="flex items-center justify-between text-[14px]">
                  <span className="text-text-secondary">Last validated</span>
                  <span>{new Date(installation.byok_validated_at).toLocaleDateString()}</span>
                </div>
              )}
              <div className="flex gap-2 pt-2">
                <button
                  onClick={() => setShowKeyInput(!showKeyInput)}
                  className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-[14px] hover:opacity-90"
                >
                  Update API Key
                </button>
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className="px-4 py-2 rounded-lg bg-transparent border border-[var(--warning)] text-[var(--warning)] text-[14px] hover:opacity-80"
                >
                  Remove Key
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-text-secondary text-[14px]">No API key configured.</p>
              <button
                onClick={() => setShowKeyInput(true)}
                className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-[14px] hover:opacity-90"
              >
                Add API Key
              </button>
            </div>
          )}

          {showKeyInput && (
            <div className="space-y-3 pt-2">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-ant-api03-..."
                className="w-full px-4 py-3 rounded-lg bg-primary border border-[var(--color-surface)] text-text-primary focus:outline-none focus:border-[var(--accent)]"
              />
              {keyError && <p className="text-[var(--warning)] text-[14px]">{keyError}</p>}
              {keySuccess && <p className="text-[var(--success)] text-[14px]">{keySuccess}</p>}
              <div className="flex gap-2">
                <button
                  onClick={updateApiKey}
                  disabled={keyLoading || !apiKey.startsWith('sk-ant-')}
                  className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-[14px] disabled:opacity-50 hover:opacity-90"
                >
                  {keyLoading ? 'Validating...' : 'Save'}
                </button>
                <button
                  onClick={() => { setShowKeyInput(false); setApiKey(''); setKeyError(null) }}
                  className="px-4 py-2 rounded-lg bg-primary text-text-secondary text-[14px] hover:opacity-80"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {showDeleteConfirm && (
            <div className="bg-primary rounded-lg p-4 space-y-3">
              <p className="text-[14px] text-[var(--warning)]">
                Are you sure? helPRs won't work without an API key.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={deleteApiKey}
                  disabled={keyLoading}
                  className="px-4 py-2 rounded-lg bg-[var(--warning)] text-white text-[14px] disabled:opacity-50"
                >
                  {keyLoading ? 'Removing...' : 'Confirm Remove'}
                </button>
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-4 py-2 rounded-lg bg-[var(--color-surface)] text-text-secondary text-[14px]"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Suppression Labels Section */}
        <section className="bg-[var(--color-surface)] rounded-lg p-6 space-y-4">
          <h2 className="text-[18px] font-semibold">Suppression Labels</h2>
          <p className="text-text-secondary text-[14px]">
            PRs with these labels will skip helPRs sessions.
          </p>
          <div className="flex flex-wrap gap-2">
            {labels.map((label) => (
              <span
                key={label}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-primary text-[14px]"
              >
                {label}
                <button
                  onClick={() => removeLabel(label)}
                  disabled={labelsLoading}
                  className="text-text-secondary hover:text-[var(--warning)] ml-1"
                >
                  &times;
                </button>
              </span>
            ))}
            {labels.length === 0 && (
              <span className="text-text-secondary text-[14px]">No labels configured</span>
            )}
          </div>
          {labelsError && (
            <p className="text-[var(--warning)] text-[14px]">{labelsError}</p>
          )}
          <div className="flex gap-2">
            <input
              type="text"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addLabel()}
              placeholder="Add label..."
              className="flex-1 px-4 py-2 rounded-lg bg-primary border border-primary text-text-primary focus:outline-none focus:border-[var(--accent)]"
            />
            <button
              onClick={addLabel}
              disabled={labelsLoading || !newLabel.trim()}
              className="px-4 py-2 rounded-lg bg-primary text-text-primary hover:opacity-80 disabled:opacity-50"
            >
              Add
            </button>
          </div>
        </section>
      </div>
    </div>
  )
}
