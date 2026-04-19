const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export default function SignInButton() {
  return (
    <a
      href={`${API_BASE}/api/v1/auth/github`}
      className="text-[13px] font-medium px-4 py-2 transition-colors duration-150 hover:text-text-primary"
      style={{
        borderRadius: '8px',
        color: 'rgba(255, 255, 255, 0.6)',
        boxShadow: 'rgba(255,255,255,0.08) 0 0 0 1px',
      }}
    >
      Sign in
    </a>
  )
}
