# Web Component Inventory

Factual inventory of the React frontend under `apps/web/src/`. The high-level architecture is in [architecture.md](architecture.md). This file is useful when you need to know where a given component lives without grepping the repo.

## Layout

```
apps/web/src/
  App.tsx                 # Router + AppShell wiring
  main.tsx                # React root
  index.css, vite-env.d.ts, setupTests.ts
  features/
    auth/                 # Login, OAuth, route protection
    dashboard/            # Installation list, detail, activity, replay
    installation/         # Per-installation setup & settings
    session/              # Live session UI (SSE, markdown, scorecard)
    demo/                 # Placeholder (.gitkeep)
  shared/
    api/client.ts         # Fetch client (credentials, error handling)
    components/           # Reusable UI primitives + AppShell
```

## Routes

Declared in `apps/web/src/App.tsx`. Protected routes are wrapped in `<ProtectedRoute>` and most also in `<AppShell>`.

| Path | Component | Notes |
|------|-----------|-------|
| `/` | `AuthRedirect` | Redirects to `/installations` if logged in, else renders `LoginPage` |
| `/auth/callback` | `OAuthCallback` | GitHub OAuth code → session cookie + redirect |
| `/installations` | `InstallationList` | Dashboard home |
| `/installations/:installationId` | `InstallationDetail` | Per-install summary + recent sessions |
| `/installations/:installationId/setup` | `SetupView` | BYOK Claude token, post-results toggle |
| `/installations/:installationId/settings` | `SettingsView` | Suppression labels, misc settings |
| `/installations/:installationId/sessions/:sessionId` | `SessionReplay` | Replay a completed session from persisted events |
| `/session/:installationId/*` | `SessionView` | Live session UI (SSE) |

Route params use the **GitHub installation ID** (integer), not the internal UUID.

## features/auth/

| File | Purpose |
|------|---------|
| `LoginPage.tsx` | Minimal login page (GitHub button + OAuth redirect) |
| `LoginPage.test.tsx` | |
| `OAuthCallback.tsx` | Exchanges the OAuth code, updates the auth store, redirects |
| `OAuthCallback.test.tsx` | |
| `ProtectedRoute.tsx` | Wrapper that redirects unauthenticated users to `/` |
| `ProtectedRoute.test.tsx` | |
| `store.ts` | Zustand auth store (`isAuthenticated`, user, token helpers) |

## features/dashboard/

| File | Purpose |
|------|---------|
| `InstallationList.tsx` | Cards list of accessible GitHub installations with session stats |
| `InstallationDetail.tsx` | Detail view: installation info, recent sessions, BYOK status |
| `ActivityChart.tsx` | Bar chart of sessions per day (uses `/auth/me/stats`) |
| `SessionReplay.tsx` | Renders a completed session from persisted `session_events` |
| `dashboardApi.ts` | React Query hooks for installations, sessions, stats |
| `formatters.ts` | Date / cost / token formatting helpers |

## features/installation/

| File | Purpose |
|------|---------|
| `SetupView.tsx` | BYOK token input + post-results toggle |
| `SettingsView.tsx` | Suppression labels and misc per-install settings |

## features/session/

The live-session UI. Rendering pipeline: SSE → `StreamMessage[]` → `ConversationOutput` → `MessageBlock` → `MarkdownContent` / `CodeBlock`.

| File | Purpose |
|------|---------|
| `SessionView.tsx` | Top-level live-session screen (route entry) |
| `ContainerSession.tsx` | SSE stream wiring + session state |
| `ContainerSession.test.tsx` | |
| `containerApi.ts` | API hooks for session lifecycle, message send, scorecard |
| `containerTypes.ts` | Types for `StreamMessage`, content blocks, scorecard, etc. |
| `ConversationOutput.tsx` | Scrollable container that lays out messages |
| `ConversationOutput.test.tsx` | |
| `MessageBlock.tsx` | Dispatches on role (assistant / user / system / result) |
| `MarkdownContent.tsx` | react-markdown + remark-gfm rendering |
| `CodeBlock.tsx` | Syntax-highlighted code (shiki with JS regex engine) |
| `ProgressTracker.tsx` | Turn / token / cost progress UI |
| `SessionRail.tsx` | Side rail with session metadata |
| `ScorecardDisplay.tsx` | Renders parsed score card at session end |
| `SkillSelector.tsx` | Card grid of available skills |
| `SkillSelector.test.tsx` | |
| `shiki.ts` | Shiki highlighter, theme (`SHIKI_THEME`), supported languages |

**Testing note:** any test that renders session components must mock `./shiki` to avoid loading real TextMate grammars in jsdom.

## shared/

| Path | Purpose |
|------|---------|
| `shared/api/client.ts` | Fetch client with credentials (httpOnly cookie refresh) and error normalization |
| `shared/components/AppShell.tsx` | Header + layout wrapper for authenticated pages |
| `shared/components/Topbar.tsx` | Top navigation bar |
| `shared/components/Button.tsx` | Button primitive |
| `shared/components/Card.tsx` | Card primitive |
| `shared/components/Chip.tsx` | Chip / tag primitive |
| `shared/components/Dot.tsx` | Status dot |
| `shared/components/ErrorBoundary.tsx` | React error boundary used at the app root |
| `shared/components/GrainOverlay.tsx` | Decorative grain overlay |
| `shared/components/Overline.tsx` | Overline label text |
| `shared/components/StatCard.tsx` | Metric card |
| `shared/components/TerminalBlock.tsx` | Monospaced block for shell-like output |
| `shared/components/components.test.tsx` | |
| `shared/components/index.ts` | Barrel re-exports |

## State management

- **Auth**: Zustand store in `features/auth/store.ts`.
- **Server state**: React Query (installations, sessions, stats, scorecard) — hooks live next to their feature (`dashboardApi.ts`, `containerApi.ts`).
- **Live session**: component state + SSE reader inside `ContainerSession`, streamed into a `StreamMessage[]` array consumed by `ConversationOutput`.
