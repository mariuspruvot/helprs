# Component Inventory -- Frontend

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Overview

The frontend is being adapted for the container-based architecture. Core auth, dashboard, and installation components remain unchanged. The session feature will evolve to display container skill output instead of the previous Socratic Q&A flow.

## App Shell & Routing

### App.tsx

`apps/web/src/app.tsx`

- **Props:** None (root component)
- **State:** Module-level `QueryClient` singleton
- **Providers:** `QueryClientProvider`, `BrowserRouter`

**Routes defined:**

| Path | Component | Auth Required | Layout |
|------|-----------|---------------|--------|
| `/` | `LandingPage` | No | None |
| `/auth/callback` | `OAuthCallback` | No | None |
| `/dashboard` | `DashboardPage` | Yes | `AppShell` (via `ProtectedRoute`) |
| `/installations/:installationId/setup` | `SetupView` | Yes | `AppShell` |
| `/installations/:installationId/settings` | `SettingsView` | Yes | `AppShell` |
| `/sessions/:sessionId` | `SessionView` | Yes | `AppShell` |

---

## Feature Modules

### auth/

| File | Component/Export | Description |
|------|-----------------|-------------|
| `store.ts` | `useAuthStore` (Zustand) | Auth state: accessToken, user, isAuthenticated, returnUrl |
| `OAuthCallback.tsx` | `OAuthCallback` | OAuth return handler |
| `ProtectedRoute.tsx` | `ProtectedRoute` | Auth guard -> redirect to GitHub OAuth |

### landing/

| File | Component | Description |
|------|-----------|-------------|
| `LandingPage.tsx` | `LandingPage` | Marketing page |
| `InstallCTA.tsx` | `InstallCTA` | GitHub App install button |

### dashboard/

| File | Component | Description |
|------|-----------|-------------|
| `DashboardPage.tsx` | `DashboardPage` | Lists installations with status |

### installation/

| File | Component | Description |
|------|-----------|-------------|
| `SetupView.tsx` | `SetupView` | First-time credential setup wizard |
| `SettingsView.tsx` | `SettingsView` | Edit credentials + suppression labels |

### session/ -- Adapting for Container Output

The session feature is being refactored to display container skill results. The existing chat/diff viewer infrastructure will be adapted:

- **Skill selection UI** -- user picks which skill to run. *Coming in Phase 2.*
- **Container output stream** -- real-time display of Claude Code output via SSE relay
- **Result display** -- formatted output from completed skill execution

Existing components that will be adapted or replaced:

| Component | Current Purpose | Post-Pivot Status |
|-----------|----------------|-------------------|
| `ChatPanel.tsx` | Socratic Q&A chat | Will become container output display |
| `DiffViewer.tsx` | PR diff viewer | Retained -- still useful for context |
| `SessionHeader.tsx` | Progress bar + PR info | Adapted for skill execution status |
| `SplitLayout.tsx` | Desktop resizable panels | Retained |
| `TabbedLayout.tsx` | Tablet tabs | Retained |
| `MobileLayout.tsx` | Mobile layout | Retained |
| `ScoreCard.tsx` | Score breakdown | Removed (no more scoring) |
| `AnswerInput.tsx` | Answer textarea | Removed (no more Q&A) |
| `ReportButton.tsx` | Question report | Removed |
| `SessionFeedback.tsx` | Thumbs up/down | May be retained for skill feedback |

---

## Shared Components

| File | Component | Used By | Description |
|------|-----------|---------|-------------|
| `AppShell.tsx` | `AppShell` | `App.tsx` | Top nav bar (logo, Dashboard link, avatar, Logout) |

---

## State Management

### Zustand Stores

| Store | File | Key State | Used By |
|-------|------|-----------|---------|
| `useAuthStore` | `features/auth/store.ts` | `accessToken, user, isAuthenticated, returnUrl` | ProtectedRoute, OAuthCallback, AppShell, api/client.ts |
| `useSessionStore` | `features/session/store.ts` | Session UI state (adapting for container output) | Session feature components |

### React Query

| Query | Endpoint | Hook | Used By |
|-------|----------|------|---------|
| Session | `GET /api/v1/sessions/:id` | `useSession(sessionId)` | `SessionView` |

---

## API Client Layer

### `apiFetch` (shared/api/client.ts)

Central fetch wrapper with:

- Automatic `Authorization: Bearer` header from auth store
- 401 retry with token refresh
- Force re-auth redirect on refresh failure
- `credentials: 'include'` on all requests

---

## Shared Hooks

| Hook | File | Purpose |
|------|------|---------|
| `useSSE` | `shared/hooks/useSSE.ts` | EventSource wrapper (will be reused for container output relay) |
| `parseSSE` | `shared/hooks/parseSSE.ts` | SSE stream consumer |
| `useViewport` | `shared/hooks/useViewport.ts` | Responsive breakpoint detection |
| `useReducedMotion` | `shared/hooks/useReducedMotion.ts` | Accessibility hook |

---

## Environment Variables (Vite)

| Variable | Default | Used By |
|----------|---------|---------|
| `VITE_API_URL` | `http://localhost:8000` | `api/client.ts`, `ProtectedRoute` |
| `VITE_GITHUB_APP_SLUG` | `helprs` | `InstallCTA`, `DashboardPage` |
