/**
 * InstallationList — dashboard landing page.
 * Matches the R2 redesign mockup: greeting, stat strip, activity chart,
 * installation cards with avatar + status grid + action buttons.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { useAuthStore } from '../auth/store'
import { fetchInstallations, fetchUserStats } from './dashboardApi'
import type { InstallationSummary, UserStats } from './dashboardApi'
import { Button, Card, Chip, Dot, Overline, StatCard } from '../../shared/components'
import ActivityChart from './ActivityChart'

const INSTALL_URL = `https://github.com/apps/${import.meta.env.VITE_GITHUB_APP_SLUG ?? 'helprs'}/installations/new`

export default function InstallationList() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [installations, setInstallations] = useState<InstallationSummary[]>([])
  const [stats, setStats] = useState<UserStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [instData, statsData] = await Promise.all([
        fetchInstallations(),
        fetchUserStats().catch(() => null),
      ])
      setInstallations(instData.items)
      setStats(statsData)
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <StatCard label="Installations" value={installations.length} />
        <StatCard label="Configured" value={configured} color={configured > 0 ? 'ok' : 'warn'} sub={`of ${installations.length}`} />
        <StatCard label="Total sessions" value={stats?.totals.total ?? totalSessions} color="accent" />
        <StatCard label="Completed" value={stats?.totals.completed ?? 0} color="ok" />
      </div>

      {/* Activity chart */}
      {stats && (
        <Card className="mb-4">
          <div className="flex justify-between items-baseline mb-3">
            <Overline>{'\u25b8'} ACTIVITY {'\u00b7'} LAST 30 DAYS</Overline>
            <span className="font-mono text-[11px] text-dim">sessions per day</span>
          </div>
          <ActivityChart data={stats.daily_counts} />
        </Card>
      )}

      {/* Error */}
      {error && (
        <Card className="mb-4 border-danger/30">
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
            <Card key={inst.id} hover>
              {/* Header: avatar + account name + type chip */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2.5">
                  <span className="w-8 h-8 rounded-full bg-accent text-bg inline-flex items-center justify-center font-mono font-bold text-sm">
                    {inst.account_login[0]?.toLowerCase()}
                  </span>
                  <div>
                    <div className="font-mono text-[15px] font-semibold text-ink">{inst.account_login}</div>
                    <div className="font-mono text-[11px] text-dim tracking-[0.04em]">
                      installation #{inst.github_installation_id}
                    </div>
                  </div>
                </div>
                <Chip>{inst.account_type.toUpperCase()}</Chip>
              </div>

              {/* Status grid: token + sessions */}
              <div className="grid grid-cols-2 gap-2.5 mb-3.5">
                <div className="px-3 py-2.5 bg-bg2 border border-rule rounded-[6px]">
                  <div className="font-mono text-[10px] text-dim tracking-[0.12em] uppercase">Token</div>
                  <div className="font-mono text-xs mt-1 flex items-center gap-1.5">
                    <Dot color={inst.byok_configured ? 'ok' : 'warn'} />
                    <span className={inst.byok_configured ? 'text-ok' : 'text-warn'}>
                      {inst.byok_configured ? 'configured' : 'not set'}
                    </span>
                  </div>
                </div>
                <div className="px-3 py-2.5 bg-bg2 border border-rule rounded-[6px]">
                  <div className="font-mono text-[10px] text-dim tracking-[0.12em] uppercase">Sessions</div>
                  <div className="font-mono text-xs text-ink mt-1">{inst.session_count} total</div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex gap-2 pt-3.5 border-t border-rule">
                <Button
                  className="text-xs py-1.5 px-3"
                  onClick={() => navigate(`/installations/${inst.github_installation_id}`)}
                >
                  View sessions {'\u2192'}
                </Button>
                <Button
                  variant="secondary"
                  className="text-xs py-1.5 px-3"
                  onClick={() => navigate(`/installations/${inst.github_installation_id}/settings`)}
                >
                  Settings
                </Button>
                {!inst.byok_configured && (
                  <Button
                    variant="ghost"
                    className="text-xs py-1.5 px-3 text-warn"
                    onClick={() => navigate(`/installations/${inst.github_installation_id}/setup`)}
                  >
                    Setup
                  </Button>
                )}
              </div>
            </Card>
          ))}

          {/* Add installation placeholder */}
          <a
            href={INSTALL_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="border border-dashed border-rule-str rounded-card p-5 flex flex-col items-center justify-center gap-2 hover:border-accent/30 transition-colors min-h-[180px]"
          >
            <span className="text-accent text-2xl font-mono">+</span>
            <span className="text-dim text-xs font-mono">Connect another account</span>
          </a>
        </div>
      )}
    </div>
  )
}
