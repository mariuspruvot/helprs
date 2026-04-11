import { create } from 'zustand'
import type {
  ChatMessage,
  FeedbackPayload,
  QuestionPayload,
  SessionResponse,
} from './types'

export interface SessionUIState {
  session: SessionResponse | null
  activeFileIndex: number
  // chat panel's share of the available width, 0..1, default 0.6.
  panelRatio: number
  // Story 3.3: committed chat messages + the in-flight streaming question.
  messages: ChatMessage[]
  streamingQuestion: ChatMessage | null
  // Story 3.4: in-flight streaming feedback message + answer-input lock.
  streamingFeedback: ChatMessage | null
  answerInputDisabled: boolean
  // Story 3.3 (AC #11): monotonic counter that ticks every time a
  // question commit cites a file. DiffViewer watches this and flashes
  // the active file tab's bottom border to #007aff for ~600ms with a
  // 300ms fade, without coupling to the tab-click / keyboard-nav code
  // paths (which must NOT flash). Starts at 0 so the initial render
  // does not trigger a bogus flash.
  highlightFileTrigger: number

  setSession: (s: SessionResponse | null) => void
  clearSession: () => void
  setActiveFile: (index: number) => void
  highlightActiveFile: (index: number) => void
  setPanelRatio: (n: number) => void

  // Story 3.3: chat-message mutations. Kept as explicit actions (not a
  // free-for-all `setState`) so the store's invariants live in one place.
  appendQuestionToken: (
    questionId: string,
    token: string,
    number: number,
    total: number,
  ) => void
  commitStreamingQuestion: (payload: QuestionPayload) => void
  resetMessages: () => void

  // Story 3.4: answer + feedback actions.
  appendUserAnswer: (
    questionId: string,
    text: string,
    questionNumber: number,
    total: number,
  ) => void
  appendFeedbackToken: (answerId: string, questionId: string, token: string) => void
  commitStreamingFeedback: (payload: FeedbackPayload) => void
  setAnswerInputDisabled: (disabled: boolean) => void
  // Story 3.4 v1.2.0 (code-review F3): full-reset of all per-session
  // chat state when the user navigates from one session to another.
  // Without this, the module-level store leaks messages from session A
  // into session B's rendered chat when the ChatPanel remounts on a
  // route change (``seededForSessionRef`` would see ``messages.length > 0``
  // and silently mark B as "seeded" without wiping A's content).
  resetForNewSession: () => void
}

// Clamping lives in the store so drag handlers, keyboard handlers, and direct
// callers all obey the same invariant (AC #3: neither panel may collapse).
const clampPanelRatio = (n: number) => Math.min(0.8, Math.max(0.3, n))

export const useSessionStore = create<SessionUIState>((set) => ({
  session: null,
  activeFileIndex: 0,
  panelRatio: 0.6,
  messages: [],
  streamingQuestion: null,
  streamingFeedback: null,
  answerInputDisabled: false,
  highlightFileTrigger: 0,

  setSession: (s) => set({ session: s, activeFileIndex: 0 }),
  clearSession: () =>
    set({
      session: null,
      activeFileIndex: 0,
      panelRatio: 0.6,
      messages: [],
      streamingQuestion: null,
      streamingFeedback: null,
      answerInputDisabled: false,
      highlightFileTrigger: 0,
    }),
  setActiveFile: (index) => set({ activeFileIndex: index }),
  // AC #11: selects the file AND ticks the highlight counter so the
  // DiffViewer flashes the tab. Used by ChatPanel on question commit;
  // user-driven nav (click / arrow keys) keeps using ``setActiveFile``
  // so it never triggers the flash.
  highlightActiveFile: (index) =>
    set((state) => ({
      activeFileIndex: index,
      highlightFileTrigger: state.highlightFileTrigger + 1,
    })),
  setPanelRatio: (n) => set({ panelRatio: clampPanelRatio(n) }),

  // First call with a given questionId creates a streamingQuestion with
  // the token as its entire text. Subsequent calls with the SAME id
  // append the token to the existing text. A new id replaces the
  // in-flight message (should not happen in practice because the
  // backend commits between questions, but we're defensive here).
  appendQuestionToken: (questionId, token, number, total) =>
    set((state) => {
      const existing = state.streamingQuestion
      if (existing && existing.id === questionId) {
        return {
          streamingQuestion: {
            ...existing,
            text: existing.text + token,
          },
        }
      }
      return {
        streamingQuestion: {
          id: questionId,
          kind: 'ai_question_streaming',
          questionNumber: number,
          total,
          text: token,
          fileRefs: [],
          createdAt: new Date().toISOString(),
          isStreaming: true,
        },
      }
    }),

  // Commits the streamingQuestion into the messages list using the
  // authoritative text + file refs from the server's `event: question`
  // payload. Using the server text (not the token concatenation)
  // protects against any normalization the backend might do.
  //
  // P15 (story-3.3 review): dedupe on `question_id`. If the SSE stream
  // ever replays a question we've already committed (e.g. after a
  // reconnect where the server resumed from its own snapshot rather
  // than ours), we replace the existing row in place instead of
  // appending a duplicate. Progress indicators and scroll position
  // stay sane, and the committed text is always the latest server
  // payload.
  commitStreamingQuestion: (payload) =>
    set((state) => {
      const existingIndex = state.messages.findIndex((m) => m.id === payload.question_id)
      const createdAt =
        existingIndex >= 0
          ? state.messages[existingIndex]!.createdAt
          : state.streamingQuestion?.createdAt ?? new Date().toISOString()
      const committed: ChatMessage = {
        id: payload.question_id,
        kind: 'ai_question',
        questionNumber: payload.number,
        total: payload.total,
        text: payload.text,
        fileRefs: payload.file_refs,
        createdAt,
        isStreaming: false,
      }
      const messages =
        existingIndex >= 0
          ? state.messages.map((m, i) => (i === existingIndex ? committed : m))
          : [...state.messages, committed]
      return {
        messages,
        streamingQuestion: null,
      }
    }),

  resetMessages: () => set({ messages: [], streamingQuestion: null }),

  // Story 3.4 actions ------------------------------------------------

  // Optimistic: pushes a `user_answer` message into ``messages``
  // immediately so the UI reflects the submission before the network
  // round-trip completes (UX-DR20). The id is `${questionId}::answer`
  // so subsequent re-renders are stable across the message list.
  appendUserAnswer: (questionId, text, questionNumber, total) =>
    set((state) => {
      const id = `${questionId}::answer`
      const message: ChatMessage = {
        id,
        kind: 'user_answer',
        questionNumber,
        total,
        text,
        fileRefs: [],
        createdAt: new Date().toISOString(),
        isStreaming: false,
      }
      // Dedupe in case the user double-fires the submit handler.
      if (state.messages.some((m) => m.id === id)) {
        return state
      }
      return { messages: [...state.messages, message] }
    }),

  // Mirror of appendQuestionToken but for the feedback stream. The
  // streaming feedback message id is keyed off the answer_id so a
  // replay (rare) replaces in place rather than producing a duplicate.
  appendFeedbackToken: (answerId, questionId, token) =>
    set((state) => {
      const existing = state.streamingFeedback
      if (existing && existing.id === answerId) {
        return {
          streamingFeedback: {
            ...existing,
            text: existing.text + token,
          },
        }
      }
      // Find the matching question to inherit number/total — keeps the
      // feedback message's progress label consistent with the cycle.
      const matchingQuestion = state.messages.find((m) => m.id === questionId)
      return {
        streamingFeedback: {
          id: answerId,
          kind: 'ai_feedback_streaming',
          questionNumber: matchingQuestion?.questionNumber ?? 0,
          total: matchingQuestion?.total ?? 0,
          text: token,
          fileRefs: [],
          createdAt: new Date().toISOString(),
          isStreaming: true,
        },
      }
    }),

  // Commits the streamingFeedback into the messages list with the
  // authoritative server text + code refs. Mirror of
  // commitStreamingQuestion's P15 dedupe — re-committing the same
  // answer_id replaces in place.
  commitStreamingFeedback: (payload) =>
    set((state) => {
      const existingIndex = state.messages.findIndex((m) => m.id === payload.answer_id)
      const createdAt =
        existingIndex >= 0
          ? state.messages[existingIndex]!.createdAt
          : state.streamingFeedback?.createdAt ?? new Date().toISOString()
      // Inherit number/total from the streaming row (or the matching
      // question) so the rendered "AI feedback" header still pairs
      // with the right cycle.
      const matchingQuestion = state.messages.find((m) => m.id === payload.question_id)
      const committed: ChatMessage = {
        id: payload.answer_id,
        kind: 'ai_feedback',
        questionNumber:
          state.streamingFeedback?.questionNumber ?? matchingQuestion?.questionNumber ?? 0,
        total: state.streamingFeedback?.total ?? matchingQuestion?.total ?? 0,
        text: payload.text,
        fileRefs: [],
        createdAt,
        isStreaming: false,
      }
      const messages =
        existingIndex >= 0
          ? state.messages.map((m, i) => (i === existingIndex ? committed : m))
          : [...state.messages, committed]
      return {
        messages,
        streamingFeedback: null,
      }
    }),

  setAnswerInputDisabled: (disabled) => set({ answerInputDisabled: disabled }),

  // Story 3.4 v1.2.0 (code-review F3): clear every per-session chat
  // field so the next session starts with a blank slate. Preserves
  // ``session``, ``activeFileIndex``, ``panelRatio``,
  // ``highlightFileTrigger`` — those are either owned by the new
  // session loader or UI-layout preferences unrelated to chat content.
  resetForNewSession: () =>
    set({
      messages: [],
      streamingQuestion: null,
      streamingFeedback: null,
      answerInputDisabled: false,
    }),
}))
