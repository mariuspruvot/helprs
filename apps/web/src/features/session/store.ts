import { create } from 'zustand'
import type { SessionResponse } from './types'

export interface SessionUIState {
  session: SessionResponse | null
  activeFileIndex: number
  // chat panel's share of the available width, 0..1, default 0.6.
  panelRatio: number
  setSession: (s: SessionResponse | null) => void
  clearSession: () => void
  setActiveFile: (index: number) => void
  setPanelRatio: (n: number) => void
}

// Clamping lives in the store so drag handlers, keyboard handlers, and direct
// callers all obey the same invariant (AC #3: neither panel may collapse).
const clampPanelRatio = (n: number) => Math.min(0.8, Math.max(0.3, n))

export const useSessionStore = create<SessionUIState>((set) => ({
  session: null,
  activeFileIndex: 0,
  panelRatio: 0.6,
  setSession: (s) => set({ session: s, activeFileIndex: 0 }),
  clearSession: () => set({ session: null, activeFileIndex: 0, panelRatio: 0.6 }),
  setActiveFile: (index) => set({ activeFileIndex: index }),
  setPanelRatio: (n) => set({ panelRatio: clampPanelRatio(n) }),
}))
