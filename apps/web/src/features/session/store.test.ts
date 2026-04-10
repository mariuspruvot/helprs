import { beforeEach, describe, expect, test } from 'vitest'
import { useSessionStore } from './store'
import type { SessionResponse } from './types'

const fixture: SessionResponse = {
  id: 'abc',
  repo_full_name: 'org/repo',
  repo_owner: 'org',
  repo_name: 'repo',
  pr_number: 1,
  pr_title: 'Example PR',
  role: 'author',
  status: 'pending',
  question_count: 0,
  diff: '',
  created_at: '2026-04-10T00:00:00Z',
  updated_at: '2026-04-10T00:00:00Z',
}

beforeEach(() => {
  useSessionStore.setState({ session: null, activeFileIndex: 0, panelRatio: 0.6 })
})

describe('useSessionStore', () => {
  test('setSession stores session and resets activeFileIndex', () => {
    useSessionStore.setState({ activeFileIndex: 3 })
    useSessionStore.getState().setSession(fixture)
    expect(useSessionStore.getState().session).toBe(fixture)
    expect(useSessionStore.getState().activeFileIndex).toBe(0)
  })

  test('setActiveFile updates the active file index', () => {
    useSessionStore.getState().setActiveFile(2)
    expect(useSessionStore.getState().activeFileIndex).toBe(2)
  })

  test('setPanelRatio clamps below 0.3', () => {
    useSessionStore.getState().setPanelRatio(0.1)
    expect(useSessionStore.getState().panelRatio).toBe(0.3)
  })

  test('setPanelRatio clamps above 0.8', () => {
    useSessionStore.getState().setPanelRatio(0.95)
    expect(useSessionStore.getState().panelRatio).toBe(0.8)
  })

  test('setPanelRatio accepts values inside the valid range', () => {
    useSessionStore.getState().setPanelRatio(0.5)
    expect(useSessionStore.getState().panelRatio).toBe(0.5)
  })

  test('clearSession resets panelRatio to 0.6', () => {
    useSessionStore.setState({ session: fixture, activeFileIndex: 5, panelRatio: 0.8 })
    useSessionStore.getState().clearSession()
    const state = useSessionStore.getState()
    expect(state.session).toBeNull()
    expect(state.activeFileIndex).toBe(0)
    expect(state.panelRatio).toBe(0.6)
  })
})
