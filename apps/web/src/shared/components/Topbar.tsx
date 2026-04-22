import { Link, useNavigate } from 'react-router'
import { useAuthStore } from '../../features/auth/store'
import { Dot } from './Dot'

export function Topbar() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  const handleSignOut = () => {
    logout()
    navigate('/')
  }

  return (
    <header className="sticky top-0 z-50 h-14 bg-bg2 border-b border-rule flex items-center px-5">
      <Link to="/installations" className="font-mono text-sm font-bold text-accent tracking-tight">
        helPRs
      </Link>

      <div className="flex-1" />

      {user && (
        <div className="flex items-center gap-3">
          <Dot color="ok" pulse />
          <span className="font-mono text-[11px] text-dim">live</span>

          <span className="text-rule-str mx-1">|</span>

          {user.avatar_url && (
            <img
              src={user.avatar_url}
              alt={user.github_login}
              className="w-6 h-6 rounded-full border border-rule"
            />
          )}
          <span className="font-mono text-xs text-ink2">{user.github_login}</span>

          <button
            onClick={handleSignOut}
            className="font-mono text-[11px] text-dim hover:text-ink2 transition-colors cursor-pointer ml-1"
          >
            sign out
          </button>
        </div>
      )}
    </header>
  )
}
