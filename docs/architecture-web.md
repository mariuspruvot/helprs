# Architecture — Frontend (web)

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## Executive Summary

React SPA frontend for **helPRs** providing GitHub OAuth login, installation setup/settings, a marketing landing page, and the core interactive comprehension session UI with real-time SSE streaming, diff viewing, and scoring.

## Technology Stack

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| Framework | React | 19.2 | UI library |
| Language | TypeScript | 6.0 | Type-safe development |
| Build | Vite | 8.0 | Dev server + bundler |
| Styling | Tailwind CSS | 4.2 | Utility-first CSS |
| State | Zustand | 5.0 | Lightweight state management |
| Data Fetching | TanStack React Query | 5.97 | Server state + caching |
| Routing | React Router | 7.14 | Client-side routing |
| Markdown | react-markdown + remark-gfm | 10.1 | Chat message rendering |
| Diff Viewer | react-diff-view + refractor | 3.3 | Unified diff display with syntax highlighting |
| Panels | react-resizable-panels | 4.9 | Resizable split layout |
| Testing | Vitest + Testing Library | 4.1 | Unit/component testing |
| Linting | ESLint + typescript-eslint | 10.2 | Code quality |

## Architecture Pattern

**Feature-based architecture** with collocated components, state, and API logic per feature module.

```
src/
  app.tsx              -- Router + QueryClient provider
  features/
    auth/              -- OAuth flow + auth state
    installation/      -- Setup wizard + settings CRUD
    landing/           -- Marketing landing page
    session/           -- Core comprehension session (17 components)
    demo/              -- (placeholder)
  shared/
    api/client.ts      -- Authenticated fetch wrapper (apiFetch)
    hooks/             -- useViewport, useReducedMotion, useSSE, parseSSE
    theme/tokens.ts    -- Design tokens (dark theme, amber accent)
```

## Routing

| Path | Component | Guard | Description |
|------|-----------|-------|-------------|
| `/` | `LandingPage` | None | Marketing landing page |
| `/auth/callback` | `OAuthCallback` | None | GitHub OAuth callback handler |
| `/installations/:installationId/setup` | `SetupView` | `ProtectedRoute` | First-time setup wizard |
| `/installations/:installationId/settings` | `SettingsView` | `ProtectedRoute` | Installation settings CRUD |
| `/sessions/:sessionId` | `ChatView` | `ProtectedRoute` | Main comprehension session |

`ProtectedRoute` checks `useAuthStore.isAuthenticated`; unauthenticated users are redirected to `{API_BASE}/api/v1/auth/github` (full-page OAuth redirect). Return URL is preserved in `sessionStorage`.

## State Management

### Zustand Stores

#### `useAuthStore`

```typescript
{
  accessToken: string | null
  user: User | null
  isAuthenticated: boolean
  returnUrl: string | null
}
```

Actions: `login(token)`, `logout()`, `setUser(user)`, `setReturnUrl(url)`

#### `useSessionStore`

```typescript
{
  session: SessionResponse | null
  activeFileIndex: number
  panelRatio: number              // 0.3..0.8, default 0.6
  messages: ChatMessage[]
  streamingQuestion: ChatMessage | null
  streamingFeedback: ChatMessage | null
  answerInputDisabled: boolean
  sessionCompleted: boolean
  reportedQuestions: number[]
  feedbackSubmitted: boolean
  highlightFileTrigger: number
  diffCollapsed: boolean
}
```

18 actions for session lifecycle, file navigation, layout, streaming, answer flow, scoring, and reporting.

### React Query

Single query: `['session', sessionId]` with `staleTime: 60s`, custom retry (no retry on 4xx, max 2 on 5xx).

## API Integration

### Transport: `apiFetch`

Central authenticated fetch wrapper at `shared/api/client.ts`:

- Base URL from `VITE_API_URL` (default: `http://localhost:8000`)
- Auto-injects `Authorization: Bearer {token}` from auth store
- On 401: silent refresh via `POST /api/v1/auth/refresh`, retry original request
- On refresh failure: `logout()` + OAuth redirect
- `credentials: 'include'` on all requests

### SSE Transport

Two mechanisms:

1. **EventSource** (`useSSE` hook): For `GET /stream`. Token as `?access_token=` query param. Exponential backoff reconnection (500ms to 16s).
2. **Fetch + ReadableStream** (`consumeSSEStream`): For `POST /answers`. Uses `AbortController` for cleanup.

## Responsive Layout Strategy

| Viewport | Width | Layout | Implementation |
|----------|-------|--------|----------------|
| Desktop | >= 1100px | `SplitLayout` | Horizontal resizable split (60/40 default) via react-resizable-panels |
| Tablet | 768-1099px | `TabbedLayout` | Tab bar switching Chat/Diff, ARIA tablist |
| Mobile | < 768px | `MobileLayout` | Chat only with desktop suggestion banner |

Viewport detection via `useViewport` hook (rAF-throttled resize listener).

## Context Providers (Session)

| Context | Type | Purpose |
|---------|------|---------|
| `DiffFilePathsContext` | `readonly string[]` | File paths from diff for code-link detection |
| `CodeLinkActionsContext` | `{scrollTo, preview, clearPreview}` | Proxy to DiffViewer imperative handle |
| `DiffViewerHandleRefContext` | `MutableRefObject<DiffViewerHandle>` | DiffViewer registration |

## Design System

- **Theme**: Dark background with amber accent (punctuation only)
- **Typography**: Inter body + monospace headlines
- **Design tokens**: Centralized in `shared/theme/tokens.ts`
- **Style**: Raycast-inspired depth, macOS terminal blocks on landing page
- **Syntax highlighting**: 10 languages registered via refractor (TS, JS, Python, Go, Rust, JSON, YAML, MD, JSX, TSX)
