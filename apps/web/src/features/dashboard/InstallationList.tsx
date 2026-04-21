/**
 * InstallationList — dashboard landing page.
 * Shows stat strip, installation cards, and placeholder for new installs.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { useAuthStore } from '../auth/store'
import { fetchInstallations } from './dashboardApi'
import type { InstallationSummary } from './dashboardApi'
import { Card, Chip, Dot, Overline, StatCard } from '../../shared/components'

const INSTALL_URL = `https://github.com/apps/${import.meta.env.VITE_GITHUB_APP_SLUG ?? 'helprs'}/installations/new`

export default function InstallationList() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [installations, setInstallations] = useState<InstallationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchInstallations()
      setInstallations(data.items)
    } catch {
      setError('Failed to load installations')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const totalSessions = installations.reduce((sum, i) => sum + i.session_count, 0)
  const configured = installations.filter((i) => i.byok_configured).length

  function greeting(): string {
    const hour = new Date().getHours()
    if (hour < 12) return 'Good morning'
    if (hour < 18) return 'Good afternoon'
    return 'Good evening'
  }

  return (
    <div>
      {/* Greeting */}
      <div className="mb-8">
        <h1 className="font-mono text-xl font-bold mb-1">
          {greeting()}, <span className="text-accent">{user?.github_login}</span>
        </h1>
        <Overline>// your installations and recent activity</Overline>
      </div>

      {/* Stat strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <StatCard label="Installations" value={installations.length} />
        <StatCard label="Configured" value={configured} color={configured > 0 ? 'ok' : 'warn'} sub={`of ${installations.length}`} />
        <StatCard label="Total sessions" value={totalSessions} color="accent" />
        <StatCard label="Status" value={error ? 'Error' : 'Live'} color={error ? 'danger' : 'ok'} />
      </div>

      {/* Error */}
      {error && (
        <Card className="mb-6 border-danger/30">
          <p className="text-danger text-sm">{error}</p>
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <div className="text-dim text-sm py-12 text-center font-mono">
          <Dot pulse className="mr-2" /> Loading installations...
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && installations.length === 0 && (
        <Card className="text-center py-12">
          <p className="text-ink2 text-sm mb-2">No installations found.</p>
          <p className="text-dim text-xs font-mono">
            // <a href={INSTALL_URL} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">install the GitHub App</a> to get started
          </p>
        </Card>
      )}

      {/* Installation cards */}
      {!loading && installations.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {installations.map((inst) => (
            <Card
              key={inst.id}
              hover
              className="cursor-pointer"
            >
              <button
                className="w-full text-left cursor-pointer"
                onClick={() => navigate(`/installations/${inst.github_installation_id}`)}
              >
                {/* Account header */}
                <div className="flex items-center gap-2 mb-3">
                  <span className="font-mono text-sm font-semibold text-ink">
                    {inst.account_login}
                  </span>
                  <Chip>{inst.account_type}</Chip>
                </div>

                {/* Status row */}
                <div className="flex items-center gap-4 mb-3">
                  <div className="flex items-center gap-1.5">
                    <Dot color={inst.byok_configured ? 'ok' : 'warn'} />
                    <span className="text-dim text-xs">
                      {inst.byok_configured ? 'Token configured' : 'No token'}
                    </span>
                  </div>
                  <span className="text-dim text-xs font-mono">
                    {inst.session_count} session{inst.session_count !== 1 ? 's' : ''}
                  </span>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-accent font-mono font-medium">
                    View sessions
                  </span>
                  <span className="text-dim2">|</span>
                  <span
                    className="text-dim hover:text-ink2 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/installations/${inst.github_installation_id}/settings`)
                    }}
                  >
                    Settings
                  </span>
                  {!inst.byok_configured && (
                    <>
                      <span className="text-dim2">|</span>
                      <span
                        className="text-warn"
                        onClick={(e) => {
                          e.stopPropagation()
                          navigate(`/installations/${inst.github_installation_id}/setup`)
                        }}
                      >
                        Setup
                      </span>
                    </>
                  )}
                </div>
              </button>
            </Card>
          ))}

          {/* Add installation placeholder */}
          <a
            href={INSTALL_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="border border-dashed border-rule-str rounded-card p-5 flex flex-col items-center justify-center gap-2 hover:border-accent/30 transition-colors min-h-[140px]"
          >
            <span className="text-accent text-2xl font-mono">+</span>
            <span className="text-dim text-xs font-mono">Connect another account</span>
          </a>
        </div>
      )}
    </div>
  )
}
