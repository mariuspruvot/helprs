const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export default function SignInButton() {
  return (
    <a
      href={`${API_BASE}/api/v1/auth/github`}
      className="font-mono text-xs font-medium px-4 py-2 rounded-button border border-rule-str text-dim hover:text-ink2 transition-colors"
    >
      sign in
    </a>
  )
}
