/**
 * InstallationList — dashboard landing page showing all installations.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { useAuthStore } from '../auth/store'
import { fetchInstallations } from './dashboardApi'
import type { InstallationSummary } from './dashboardApi'

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

  return (
    <div className="min-h-screen bg-primary text-text-primary">
      {/* Header */}
      <div
        className="h-14 flex items-center px-6 gap-4 border-b"
        style={{ borderColor: 'rgba(255, 255, 255, 0.06)' }}
      >
        <span
          className="text-[15px] font-mono font-bold tracking-tight"
          style={{ color: '#E2A039' }}
        >
          helPRs
        </span>
        <span className="text-text-muted text-[12px]">|</span>
        <span className="text-text-secondary text-[13px] font-sans">Dashboard</span>

        <div className="ml-auto flex items-center gap-3">
          {user?.avatar_url && (
            <img
              src={user.avatar_url}
              alt={user.github_login}
              className="w-6 h-6 rounded-full"
            />
          )}
          <span className="text-text-secondary text-[13px] font-sans">
            {user?.github_login}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-6 py-8">
        <h1 className="text-[20px] font-sans font-semibold mb-6">
          Your Installations
        </h1>

        {loading && (
          <div className="text-text-muted text-[14px] font-sans py-12 text-center">
            Loading...
          </div>
        )}

        {error && (
          <div
            className="text-[13px] px-4 py-3 rounded-lg mb-6"
            style={{ background: 'rgba(255, 59, 48, 0.08)', color: '#ff6961' }}
          >
            {error}
          </div>
        )}

        {!loading && !error && installations.length === 0 && (
          <div
            className="rounded-xl px-6 py-12 text-center"
            style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.06)' }}
          >
            <p className="text-text-secondary text-[14px] font-sans mb-4">
              No installations found.
            </p>
            <p className="text-text-muted text-[13px] font-sans">
              Install the GitHub App on your organization or account to get started.
            </p>
          </div>
        )}

        {!loading && installations.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {installations.map((inst) => (
              <button
                key={inst.id}
                onClick={() => navigate(`/installations/${inst.github_installation_id}`)}
                className="text-left rounded-xl p-5 transition-all cursor-pointer group"
                style={{
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(226, 160, 57, 0.3)'
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.04)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.06)'
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)'
                }}
              >
                {/* Account header */}
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-[15px] font-sans font-medium text-text-primary">
                    {inst.account_login}
                  </span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded font-mono uppercase"
                    style={{
                      color: '#9a9898',
                      background: 'rgba(154, 152, 152, 0.1)',
                    }}
                  >
                    {inst.account_type}
                  </span>
                </div>

                {/* Stats row */}
                <div className="flex items-center gap-4 mb-3">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{
                        background: inst.byok_configured ? '#30d158' : '#ff9f0a',
                      }}
                    />
                    <span className="text-text-muted text-[12px] font-sans">
                      {inst.byok_configured ? 'Token configured' : 'No token'}
                    </span>
                  </div>
                  <span className="text-text-muted text-[12px] font-sans">
                    {inst.session_count} session{inst.session_count !== 1 ? 's' : ''}
                  </span>
                </div>

                {/* Actions row */}
                <div className="flex items-center gap-3">
                  <span
                    className="text-[12px] font-sans group-hover:underline"
                    style={{ color: '#E2A039' }}
                  >
                    View sessions
                  </span>
                  <span className="text-text-muted text-[11px]">|</span>
                  <span
                    className="text-[12px] text-text-secondary font-sans hover:text-text-primary"
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/installations/${inst.github_installation_id}/settings`)
                    }}
                  >
                    Settings
                  </span>
                  {!inst.byok_configured && (
                    <>
                      <span className="text-text-muted text-[11px]">|</span>
                      <span
                        className="text-[12px] font-sans"
                        style={{ color: '#ff9f0a' }}
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
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
