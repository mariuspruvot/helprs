import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router'
import { apiFetch } from '../../shared/api/client'
import { Button, Card, Chip, Dot, Overline } from '../../shared/components'

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

const GITHUB_APP_SLUG = import.meta.env.VITE_GITHUB_APP_SLUG ?? 'helprs'

export default function SettingsView() {
  const { installationId } = useParams<{ installationId: string }>()
  const [installation, setInstallation] = useState<InstallationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [showKeyInput, setShowKeyInput] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [keyLoading, setKeyLoading] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)
  const [keySuccess, setKeySuccess] = useState<string | null>(null)

  const [labels, setLabels] = useState<string[]>([])
  const [newLabel, setNewLabel] = useState('')
  const [labelsLoading, setLabelsLoading] = useState(false)
  const [labelsError, setLabelsError] = useState<string | null>(null)

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
      setKeySuccess('Token updated and encrypted at rest')
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
      <div className="flex items-center justify-center py-20">
        <div className="text-dim text-sm font-mono">
          <Dot pulse className="mr-2" /> Loading settings...
        </div>
      </div>
    )
  }

  if (error || !installation) {
    return (
      <div className="flex items-center justify-center py-20">
        <Card className="border-danger/30">
          <p className="text-danger text-sm">{error ?? 'Installation not found'}</p>
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto py-8">
      {/* Header */}
      <div className="mb-8">
        <Overline className="mb-2">{'\u25b8'} SETTINGS</Overline>
        <h1 className="font-mono text-2xl font-bold text-ink">Installation Settings</h1>
        <p className="text-dim text-sm mt-1 font-sans">
          {installation.account_login} {'\u00b7'} {installation.account_type}
        </p>
      </div>

      {/* Claude Token Section */}
      <Card className="mb-6">
        <Overline className="mb-4">Claude Token</Overline>

        {installation.byok_configured ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-dim font-mono">Status</span>
              <div className="flex items-center gap-2">
                <Dot color="ok" />
                <span className="text-ok font-mono">
                  {installation.byok_key_status} ({installation.byok_key_hint})
                </span>
              </div>
            </div>
            {installation.byok_validated_at && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-dim font-mono">Validated</span>
                <span className="text-ink2 font-mono">
                  {new Date(installation.byok_validated_at).toLocaleDateString()}
                </span>
              </div>
            )}
            <div className="flex gap-2 pt-2">
              <Button onClick={() => setShowKeyInput(!showKeyInput)}>
                Update Token
              </Button>
              <Button variant="danger" onClick={() => setShowDeleteConfirm(true)}>
                Remove
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm">
              <Dot color="warn" />
              <span className="text-warn">No token configured</span>
            </div>
            <Button onClick={() => setShowKeyInput(true)}>
              Add Token
            </Button>
          </div>
        )}

        {showKeyInput && (
          <div className="mt-4 pt-4 border-t border-rule space-y-3">
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value.replace(/\s/g, ''))}
              placeholder="sk-ant-oat01-..."
              className="w-full px-4 py-3 rounded-button bg-bg border border-rule text-ink font-mono text-sm focus:outline-none focus:border-accent"
            />
            {keyError && <p className="text-danger text-sm">{keyError}</p>}
            {keySuccess && <p className="text-ok text-sm">{keySuccess}</p>}
            <div className="flex gap-2">
              <Button
                onClick={updateApiKey}
                disabled={keyLoading || !apiKey.startsWith('sk-ant-')}
              >
                {keyLoading ? 'Validating...' : 'Save'}
              </Button>
              <Button
                variant="ghost"
                onClick={() => { setShowKeyInput(false); setApiKey(''); setKeyError(null) }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {showDeleteConfirm && (
          <div className="mt-4 pt-4 border-t border-rule space-y-3">
            <p className="text-danger text-sm">
              Are you sure? helPRs won't work without a token.
            </p>
            <div className="flex gap-2">
              <Button
                variant="danger"
                onClick={deleteApiKey}
                disabled={keyLoading}
              >
                {keyLoading ? 'Removing...' : 'Confirm Remove'}
              </Button>
              <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Suppression Labels Section */}
      <Card className="mb-6">
        <Overline className="mb-4">Suppression Labels</Overline>
        <p className="text-ink2 text-sm font-sans mb-4">
          PRs with these labels will skip helPRs sessions.
        </p>

        <div className="flex flex-wrap gap-2 mb-4">
          {labels.map((label) => (
            <Chip key={label}>
              {label}
              <button
                onClick={() => removeLabel(label)}
                disabled={labelsLoading}
                className="text-dim hover:text-danger ml-1 cursor-pointer disabled:opacity-50"
              >
                &times;
              </button>
            </Chip>
          ))}
          {labels.length === 0 && (
            <span className="text-dim text-xs font-mono">// no labels configured</span>
          )}
        </div>

        {labelsError && <p className="text-danger text-sm mb-4">{labelsError}</p>}

        <div className="flex gap-2">
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addLabel()}
            placeholder="Add label..."
            className="flex-1 px-3 py-2 rounded-button bg-bg border border-rule text-ink font-mono text-sm focus:outline-none focus:border-accent"
          />
          <Button
            variant="secondary"
            onClick={addLabel}
            disabled={labelsLoading || !newLabel.trim()}
          >
            Add
          </Button>
        </div>
      </Card>

      {/* Repository Access */}
      <Card className="mb-6">
        <Overline className="mb-4">Repository Access</Overline>
        <p className="text-ink2 text-sm font-sans mb-4">
          Manage which repositories helPRs has access to.
        </p>
        <a
          href={`https://github.com/settings/installations/${installationId}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent text-sm font-mono hover:underline"
        >
          Configure on GitHub {'\u2197'}
        </a>
      </Card>

      {/* Danger Zone */}
      <Card className="border-danger/20">
        <Overline className="mb-4 text-danger">Danger Zone</Overline>
        <p className="text-ink2 text-sm font-sans mb-4">
          Uninstall helPRs from this account. This will remove all configuration.
        </p>
        <a
          href={`https://github.com/apps/${GITHUB_APP_SLUG}/installations/${installationId}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          <Button variant="danger">
            Uninstall on GitHub {'\u2197'}
          </Button>
        </a>
      </Card>
    </div>
  )
}
