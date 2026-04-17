# Component Inventory -- Frontend

> Updated 2026-04-17 (post-cleanup)

## Overview

The frontend is a lightweight React SPA for the container-based skill execution flow. It handles GitHub OAuth, installation management, skill selection, and real-time display of container output via SSE.

## App Shell & Routing

### App.tsx

`apps/web/src/app.tsx`

- **Props:** None (root component)
- **State:** Module-level `QueryClient` singleton
- **Providers:** `QueryClientProvider`, `BrowserRouter`

**Routes defined:**

| Path | Component | Auth Required |
|------|-----------|---------------|
| `/` | `LandingPage` | No |
| `/auth/callback` | `OAuthCallback` | No |
| `/installations/:installationId/setup` | `SetupView` | Yes (`ProtectedRoute`) |
| `/installations/:installationId/settings` | `SettingsView` | Yes (`ProtectedRoute`) |
| `/session/:installationId/*` | `SessionView` | Yes (`ProtectedRoute`) |

---

## Feature Modules

### auth/

| File | Component/Export | Description |
|------|-----------------|-------------|
| `store.ts` | `useAuthStore` (Zustand) | Auth state: accessToken, user, isAuthenticated, returnUrl |
| `OAuthCallback.tsx` | `OAuthCallback` | OAuth return handler -- exchanges code for token |
| `ProtectedRoute.tsx` | `ProtectedRoute` | Auth guard, redirects to GitHub OAuth if unauthenticated |

### landing/

| File | Component | Description |
|------|-----------|-------------|
| `LandingPage.tsx` | `LandingPage` | Product landing page |
| `LandingPage.test.tsx` | -- | Tests for LandingPage |
| `InstallCTA.tsx` | `InstallCTA` | GitHub App install button |
| `InstallCTA.test.tsx` | -- | Tests for InstallCTA |

### installation/

| File | Component | Description |
|------|-----------|-------------|
| `SetupView.tsx` | `SetupView` | Post-install credential setup wizard |
| `SettingsView.tsx` | `SettingsView` | Edit credentials + suppression labels |

### session/ -- Container Skill Execution

| File | Component | Description |
|------|-----------|-------------|
| `SessionView.tsx` | `SessionView` | Route component orchestrating SkillSelector and ContainerSession |
| `SkillSelector.tsx` | `SkillSelector` | Displays available skills as cards (challenge-me, code-review, security-audit) |
| `SkillSelector.test.tsx` | -- | Tests for SkillSelector |
| `ContainerSession.tsx` | `ContainerSession` | Manages container lifecycle: create session, connect SSE, display output, stop |
| `ContainerSession.test.tsx` | -- | Tests for ContainerSession |
| `TerminalOutput.tsx` | `TerminalOutput` | Terminal-like renderer with macOS-style window chrome, auto-scroll |
| `TerminalOutput.test.tsx` | -- | Tests for TerminalOutput |
| `containerApi.ts` | `createSession`, `getSession`, `stopSession` | API client for container endpoints |
| `containerTypes.ts` | `ContainerSessionRequest`, `ContainerSessionResponse`, `Skill`, `TerminalLine`, etc. | TypeScript types for container sessions |

### demo/

Empty feature directory (`.gitkeep` only). Reserved for future fixture-based demo flow.

---

## Shared

### api/

| File | Export | Description |
|------|--------|-------------|
| `client.ts` | `apiFetch` | Central fetch wrapper with automatic `Authorization: Bearer` header, 401 retry with token refresh, force re-auth on failure |

### components/

Empty (`.gitkeep` only). No shared components currently.

---

## State Management

### Zustand Store

| Store | File | Key State | Used By |
|-------|------|-----------|---------|
| `useAuthStore` | `features/auth/store.ts` | `accessToken, user, isAuthenticated, returnUrl` | ProtectedRoute, OAuthCallback, api/client.ts |

### React Query

Used via `QueryClientProvider` in App.tsx. No custom hooks currently defined -- queries are inline in components.

---

## Environment Variables (Vite)

| Variable | Default | Used By |
|----------|---------|---------|
| `VITE_API_URL` | `http://localhost:8000` | `api/client.ts`, `ProtectedRoute` |
| `VITE_GITHUB_APP_SLUG` | `helprs` | `InstallCTA` |
