import { useEffect, useState } from 'react'

export type Viewport = 'desktop' | 'tablet' | 'mobile'

// Breakpoints (UX spec lines 96–101):
//   >= 1100 px — split-view
//   768–1099  — tabbed
//   < 768     — mobile chat-only
export const DESKTOP_BREAKPOINT = 1100
export const TABLET_BREAKPOINT = 768

export function getViewport(width: number): Viewport {
  if (width >= DESKTOP_BREAKPOINT) return 'desktop'
  if (width >= TABLET_BREAKPOINT) return 'tablet'
  return 'mobile'
}

export function useViewport(): Viewport {
  const [viewport, setViewport] = useState<Viewport>(() =>
    typeof window !== 'undefined' ? getViewport(window.innerWidth) : 'desktop',
  )

  useEffect(() => {
    if (typeof window === 'undefined') return

    let frame = 0
    const handleResize = () => {
      if (frame) cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        setViewport(getViewport(window.innerWidth))
      })
    }

    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [])

  return viewport
}
