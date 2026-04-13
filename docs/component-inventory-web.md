# Component Inventory — Frontend (web)

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## Layout Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `SplitLayout` | `session/SplitLayout.tsx` | Desktop (>=1100px) horizontal resizable split via react-resizable-panels |
| `TabbedLayout` | `session/TabbedLayout.tsx` | Tablet (768-1099px) tab bar switching Chat/Diff, ARIA tablist |
| `MobileLayout` | `session/MobileLayout.tsx` | Mobile (<768px) chat-only with desktop suggestion banner |

## Feature Components

### Auth

| Component | Location | Purpose |
|-----------|----------|---------|
| `OAuthCallback` | `auth/OAuthCallback.tsx` | Reads `access_token` from query params, fetches user, navigates to return URL |
| `ProtectedRoute` | `auth/ProtectedRoute.tsx` | Auth guard — redirects unauthenticated to GitHub OAuth |

### Installation

| Component | Location | Purpose |
|-----------|----------|---------|
| `SetupView` | `installation/SetupView.tsx` | 3-step wizard: API key -> suppression labels -> completion |
| `SettingsView` | `installation/SettingsView.tsx` | Full CRUD: BYOK status, update/delete key, manage labels |

### Landing

| Component | Location | Purpose |
|-----------|----------|---------|
| `LandingPage` | `landing/LandingPage.tsx` | Hero, how-it-works, BYOK/privacy, problem statement, CTA, footer |
| `InstallCTA` | `landing/InstallCTA.tsx` | Amber button linking to GitHub App install |

### Session (Core — 17 components)

| Component | Location | Props | Purpose |
|-----------|----------|-------|---------|
| `ChatView` | `session/ChatView.tsx` | `:sessionId` from URL | Top-level page. Error screens for 403/404/422/429. |
| `ChatPanel` | `session/ChatPanel.tsx` | `session: SessionResponse` | Message list + SSE + answer submission |
| `ChatMessage` | `session/ChatMessage.tsx` | `message: ChatMessageType` | Markdown bubble (react-markdown + remark-gfm) |
| `AnswerInput` | `session/AnswerInput.tsx` | `disabled, sessionCompleted, onSubmit` | Auto-resizing textarea, Enter-to-submit |
| `SessionHeader` | `session/SessionHeader.tsx` | `session: SessionResponse` | Fixed 48px header: repo, PR, role badge, progress |
| `DiffViewer` | `session/DiffViewer.tsx` | `session, onClose?` | Unified diff with file nav, syntax highlighting, imperative API |
| `CodeLink` | `session/CodeLink.tsx` | `file, line` | Inline file:line button — click scrolls, hover previews |
| `ScoreCard` | `session/ScoreCard.tsx` | `score: ScoreData` | 4 dimension bars, verdict badge, gaps list, animated |
| `ReportButton` | `session/ReportButton.tsx` | `sessionId, questionNumber, alreadyReported?` | Flag icon + reason selector dropdown (6 reasons) |
| `SessionFeedback` | `session/SessionFeedback.tsx` | `sessionId, existingFeedback?` | Post-session thumbs up/down + optional comment |

### Landing Internal Components (not exported)

| Component | Location | Purpose |
|-----------|----------|---------|
| `Section` | `landing/LandingPage.tsx` | Centered max-width section wrapper |
| `Divider` | `landing/LandingPage.tsx` | Subtle horizontal rule |
| `Overline` | `landing/LandingPage.tsx` | Amber uppercase section label |
| `Terminal` | `landing/LandingPage.tsx` | macOS-style terminal block |

### ChatView Internal Components (not exported)

| Component | Location | Purpose |
|-----------|----------|---------|
| `ErrorScreen` | `session/ChatView.tsx` | Error display with optional retry |
| `SessionSkeleton` | `session/ChatView.tsx` | Loading skeleton (header + panels) |
| `LoadedLayout` | `session/ChatView.tsx` | Viewport detection + context providers |

## Shared Hooks

| Hook | Location | Purpose |
|------|----------|---------|
| `useViewport` | `shared/hooks/useViewport.ts` | Returns `desktop` / `tablet` / `mobile`. Breakpoints: 1100px, 768px. rAF-throttled. |
| `useReducedMotion` | `shared/hooks/useReducedMotion.ts` | Tracks `prefers-reduced-motion: reduce` |
| `useSSE` | `shared/hooks/useSSE.ts` | EventSource wrapper with exponential backoff reconnection |
| `parseSSE` / `consumeSSEStream` | `shared/hooks/parseSSE.ts` | Async SSE byte-stream parser for fetch ReadableStream |

## Shared Utilities

| Module | Location | Purpose |
|--------|----------|---------|
| `apiFetch` | `shared/api/client.ts` | Authenticated fetch wrapper with auto-refresh |
| `tokens` | `shared/theme/tokens.ts` | Design tokens: colors, spacing, radius, typography |
| `refractorSetup` | `session/refractorSetup.ts` | 10 languages for syntax highlighting |

## Context Providers

| Context | Type | Purpose |
|---------|------|---------|
| `DiffFilePathsContext` | `readonly string[]` | File paths from diff for code-link detection |
| `CodeLinkActionsContext` | `{scrollTo, preview, clearPreview}` | Proxy to DiffViewer imperative handle |
| `DiffViewerHandleRefContext` | `MutableRefObject<DiffViewerHandle>` | DiffViewer registration |
