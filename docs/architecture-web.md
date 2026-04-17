# Architecture -- Frontend (web)

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Executive Summary

React 19 single-page application providing the UI for helPRs. Feature-based module architecture with Zustand for state management, React Query for server state, and SSE for real-time container output streaming. The frontend is being adapted for skill selection and container-based result display.

## Technology Stack

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| Language | TypeScript | 6.0 | Type-safe development |
| Framework | React | 19 | UI framework |
| Build | Vite | 8 | Dev server + bundler |
| Styling | Tailwind CSS | 4 | Utility-first CSS |
| Routing | react-router | 7 | Client-side routing |
| State | Zustand | 5 | Client state management |
| Server State | @tanstack/react-query | 5 | Data fetching + caching |
| Diff Viewer | react-diff-view | 3.3 | PR diff rendering |
| Markdown | react-markdown + remark-gfm | 10.1 | Message rendering |
| Syntax Highlighting | refractor | 4.9 | Code block highlighting |
| Resizable Panels | react-resizable-panels | 4.9 | Desktop split layout |
| Testing | vitest + @testing-library/react | 4.1 / 16.3 | Test framework |
| Linting | eslint + typescript-eslint | 10 / 8 | Code quality |

## Architecture Pattern

```
src/
+-- main.tsx              # Entry point (StrictMode + App)
+-- app.tsx               # Routes + providers (QueryClient, BrowserRouter)
+-- index.css             # Global styles (Tailwind 4 + design tokens)
|
+-- features/             # Feature modules (domain-organized)
|   +-- auth/             # OAuth flow + auth state
|   +-- landing/          # Marketing page
|   +-- dashboard/        # Installation grid
|   +-- installation/     # Credential setup + settings
|   +-- session/          # Container result display + skill execution
|       +-- hooks/        # Session-specific hooks
|       +-- store.ts      # Zustand session UI state
|
+-- shared/               # Cross-feature infrastructure
    +-- api/client.ts     # apiFetch wrapper (auth + retry)
    +-- components/       # AppShell layout
    +-- hooks/            # useSSE, parseSSE, useViewport, useReducedMotion
    +-- theme/tokens.ts   # Design system tokens
    +-- types/            # Shared TypeScript types
    +-- utils/            # Validation utilities
```

## Routing Architecture

```
BrowserRouter
+-- /                          -> LandingPage (public)
+-- /auth/callback             -> OAuthCallback (public)
+-- ProtectedRoute             -> Requires isAuthenticated
    +-- AppShell               -> Top nav + <Outlet>
        +-- /dashboard         -> DashboardPage
        +-- /installations/:id/setup    -> SetupView
        +-- /installations/:id/settings -> SettingsView
        +-- /sessions/:id      -> SessionView (container results)
```

**Auth flow:**

1. `ProtectedRoute` checks `useAuthStore.isAuthenticated`
2. If false: saves `returnUrl` to sessionStorage, redirects to GitHub OAuth
3. `OAuthCallback` receives `?access_token=`, calls `GET /auth/me`, stores user
4. Navigates to saved `returnUrl` or `/dashboard`

## State Management

### Zustand Stores

**`useAuthStore`** -- Authentication state

```typescript
{ accessToken, user, isAuthenticated, returnUrl }
// Actions: login(token), logout(), setUser(user), setReturnUrl(url)
```

**`useSessionStore`** -- Session UI state

The session store is being adapted for container-based output. Currently manages streaming state, messages, and result display. *Exact shape will evolve as container module is implemented.*

### React Query

Single query: `useSession(sessionId)` wrapping `GET /api/v1/sessions/:id`

## Real-time Streaming Architecture (Post-Pivot)

The frontend receives SSE events relayed from ephemeral containers through the backend:

```
SessionView
  +-- useSSE(url, handlers)
        +-- EventSource(container relay endpoint)
              +-- Container output events (streamed via API passthrough)
              +-- done -> container completed
              +-- error -> show error banner
```

The exact SSE event types will be defined when the container module is implemented. The existing `useSSE` and `parseSSE` hooks will be reused for the passthrough stream.

## Responsive Layout Strategy

| Viewport | Breakpoint | Component | Behavior |
|----------|-----------|-----------|----------|
| Desktop | >= 1100px | `SplitLayout` | Resizable result/diff panels |
| Tablet | 768-1099px | `TabbedLayout` | Result/Diff tabs with keyboard navigation |
| Mobile | < 768px | `MobileLayout` | Results only + "open on desktop" banner |

Detection: `useViewport()` hook with `matchMedia` listeners.

## API Client (`shared/api/client.ts`)

Central `apiFetch` function:

1. Reads JWT from `useAuthStore`
2. Sets `Authorization: Bearer` header
3. On 401: attempts `POST /auth/refresh` with httpOnly cookie
4. On refresh success: retries original request with new token
5. On refresh failure: clears store, redirects to GitHub OAuth
6. All requests include `credentials: 'include'`

## Session Persistence

| Key | Storage | Purpose |
|-----|---------|---------|
| `helprs.returnUrl` | sessionStorage | Persist OAuth return URL |

## Environment Variables (Vite)

| Variable | Default | Used By |
|----------|---------|---------|
| `VITE_API_URL` | `http://localhost:8000` | `api/client.ts`, `ProtectedRoute` |
| `VITE_GITHUB_APP_SLUG` | `helprs` | `InstallCTA`, `DashboardPage` |

## Key Design Decisions

1. **Feature-based organization**: each feature is self-contained with components, hooks, and state
2. **Zustand over Redux**: simpler API, no boilerplate, sufficient for this app's complexity
3. **SSE passthrough**: frontend consumes the same SSE protocol, now backed by container relay instead of direct AI generation
4. **Three responsive layouts**: separate components (not CSS-only) for each viewport
5. **Path aliases**: `@/*` maps to `./src/*` via tsconfig + Vite
