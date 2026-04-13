const INSTALL_URL = `https://github.com/apps/${import.meta.env.VITE_GITHUB_APP_SLUG ?? 'helprs'}/installations/new`

export default function InstallCTA({ className = '' }: { className?: string }) {
  return (
    <a
      href={INSTALL_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-block text-[15px] font-semibold py-3 px-6 text-center transition-all duration-150 active:scale-[0.98] ${className}`}
      style={{
        borderRadius: '8px',
        color: '#1a1400',
        background: '#E2A039',
        boxShadow:
          'rgba(226,160,57,0.4) 0 0 0 1px, inset rgba(255,255,255,0.15) 0 1px 0 0, rgba(0,0,0,0.2) 0 2px 4px',
      }}
    >
      Install GitHub App
    </a>
  )
}
