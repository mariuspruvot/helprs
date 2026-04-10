import { create } from 'zustand'
import type { ChatMessage, QuestionPayload, SessionResponse } from './types'

export interface SessionUIState {
  session: SessionResponse | null
  activeFileIndex: number
  // chat panel's share of the available width, 0..1, default 0.6.
  panelRatio: number
  // Story 3.3: committed chat messages + the in-flight streaming question.
  messages: ChatMessage[]
  streamingQuestion: ChatMessage | null

  setSession: (s: SessionResponse | null) => void
  clearSession: () => void
  setActiveFile: (index: number) => void
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

  setSession: (s) => set({ session: s, activeFileIndex: 0 }),
  clearSession: () =>
    set({
      session: null,
      activeFileIndex: 0,
      panelRatio: 0.6,
      messages: [],
      streamingQuestion: null,
    }),
  setActiveFile: (index) => set({ activeFileIndex: index }),
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
  commitStreamingQuestion: (payload) =>
    set((state) => {
      const committed: ChatMessage = {
        id: payload.question_id,
        kind: 'ai_question',
        questionNumber: payload.number,
        total: payload.total,
        text: payload.text,
        fileRefs: payload.file_refs,
        createdAt: state.streamingQuestion?.createdAt ?? new Date().toISOString(),
        isStreaming: false,
      }
      return {
        messages: [...state.messages, committed],
        streamingQuestion: null,
      }
    }),

  resetMessages: () => set({ messages: [], streamingQuestion: null }),
}))
