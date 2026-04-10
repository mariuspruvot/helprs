import React from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { vi } from 'vitest'
import { useAuthStore } from '../auth/store'
import { useSessionStore } from './store'
import type { SessionResponse } from './types'

export const SESSION_ID = '11111111-1111-1111-1111-111111111111'

export const MULTI_FILE_DIFF = `diff --git a/foo.ts b/foo.ts
index 1111111..2222222 100644
--- a/foo.ts
+++ b/foo.ts
@@ -1,3 +1,3 @@
 const a = 1
-const b = 2
+const b = 3
 const c = 4
diff --git a/bar.py b/bar.py
index 3333333..4444444 100644
--- a/bar.py
+++ b/bar.py
@@ -1,2 +1,3 @@
 def hello():
-    return 1
+    return 2
+    # trailing
`

export function makeSession(overrides: Partial<SessionResponse> = {}): SessionResponse {
  return {
    id: SESSION_ID,
    repo_full_name: 'acme/helprs',
    repo_owner: 'acme',
    repo_name: 'helprs',
    pr_number: 42,
    pr_title: 'Improve caching',
    role: 'author',
    status: 'pending',
    question_count: 0,
    total_questions: 3,
    diff: MULTI_FILE_DIFF,
    created_at: '2026-04-10T00:00:00Z',
    updated_at: '2026-04-10T00:00:00Z',
    ...overrides,
  }
}

export function resetStores() {
  useSessionStore.setState({
    session: null,
    activeFileIndex: 0,
    panelRatio: 0.6,
    messages: [],
    streamingQuestion: null,
  })
  useAuthStore.setState({
    accessToken: 'test-token',
    user: null,
    isAuthenticated: true,
    returnUrl: null,
  })
}

interface RenderOptions {
  path?: string
  sessionId?: string
}

export function renderAtSessionRoute(
  element: React.ReactElement,
  { sessionId = SESSION_ID, path = `/sessions/${sessionId}` }: RenderOptions = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/sessions/:sessionId" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

export function mockApiFetchOnce(mockFetch: ReturnType<typeof vi.fn>, response: Response) {
  mockFetch.mockResolvedValueOnce(response)
}

export function setWindowWidth(width: number) {
  // jsdom allows `window.innerWidth` to be written directly.
  // Required to drive the useViewport hook in component tests.
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width,
  })
  window.dispatchEvent(new Event('resize'))
}
