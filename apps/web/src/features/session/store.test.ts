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
  total_questions: 3,
  diff: '',
  created_at: '2026-04-10T00:00:00Z',
  updated_at: '2026-04-10T00:00:00Z',
  progress: [],
  score: null,
  feedback: null,
}

beforeEach(() => {
  useSessionStore.setState({
    session: null,
    activeFileIndex: 0,
    panelRatio: 0.6,
    messages: [],
    streamingQuestion: null,
    streamingFeedback: null,
    answerInputDisabled: false,
    sessionCompleted: false,
    reportedQuestions: [],
    feedbackSubmitted: false,
  })
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

  test('appendQuestionToken creates streamingQuestion on first call', () => {
    useSessionStore.getState().appendQuestionToken('q1', 'Why', 1, 3)
    const state = useSessionStore.getState()
    expect(state.streamingQuestion).not.toBeNull()
    expect(state.streamingQuestion?.id).toBe('q1')
    expect(state.streamingQuestion?.text).toBe('Why')
    expect(state.streamingQuestion?.questionNumber).toBe(1)
    expect(state.streamingQuestion?.total).toBe(3)
    expect(state.streamingQuestion?.isStreaming).toBe(true)
  })

  test('appendQuestionToken appends to existing streamingQuestion text', () => {
    useSessionStore.getState().appendQuestionToken('q1', 'Why', 1, 3)
    useSessionStore.getState().appendQuestionToken('q1', ' does', 1, 3)
    useSessionStore.getState().appendQuestionToken('q1', ' it?', 1, 3)
    expect(useSessionStore.getState().streamingQuestion?.text).toBe('Why does it?')
  })

  test('commitStreamingQuestion moves streaming into messages and clears it', () => {
    useSessionStore.getState().appendQuestionToken('q1', 'Why?', 1, 3)
    useSessionStore.getState().commitStreamingQuestion({
      question_id: 'q1',
      text: 'Why does foo call bar?',
      number: 1,
      total: 3,
      file_refs: ['foo.ts'],
    })
    const state = useSessionStore.getState()
    expect(state.streamingQuestion).toBeNull()
    expect(state.messages).toHaveLength(1)
    expect(state.messages[0]?.id).toBe('q1')
    expect(state.messages[0]?.kind).toBe('ai_question')
    expect(state.messages[0]?.text).toBe('Why does foo call bar?')
    expect(state.messages[0]?.fileRefs).toEqual(['foo.ts'])
    expect(state.messages[0]?.isStreaming).toBe(false)
  })

  test('clearSession wipes messages and streamingQuestion', () => {
    useSessionStore.getState().appendQuestionToken('q1', 'partial', 1, 3)
    useSessionStore.setState({
      messages: [
        {
          id: 'q0',
          kind: 'ai_question',
          questionNumber: 1,
          total: 3,
          text: 'Old?',
          fileRefs: [],
          createdAt: '2026-04-10T00:00:00Z',
          isStreaming: false,
        },
      ],
    })
    useSessionStore.getState().clearSession()
    const state = useSessionStore.getState()
    expect(state.messages).toEqual([])
    expect(state.streamingQuestion).toBeNull()
  })

  test('resetMessages clears only messages and streamingQuestion', () => {
    useSessionStore.setState({
      session: fixture,
      messages: [
        {
          id: 'q0',
          kind: 'ai_question',
          questionNumber: 1,
          total: 3,
          text: 'Old?',
          fileRefs: [],
          createdAt: '2026-04-10T00:00:00Z',
          isStreaming: false,
        },
      ],
    })
    useSessionStore.getState().resetMessages()
    const state = useSessionStore.getState()
    expect(state.session).toBe(fixture)
    expect(state.messages).toEqual([])
    expect(state.streamingQuestion).toBeNull()
  })

  // ====================================================================
  // Story 3.4: answer + feedback actions
  // ====================================================================

  test('appendUserAnswer pushes a user_answer message immediately', () => {
    useSessionStore.getState().appendUserAnswer('q1', 'Because of caching.', 1, 3)
    const state = useSessionStore.getState()
    expect(state.messages).toHaveLength(1)
    expect(state.messages[0]?.id).toBe('q1::answer')
    expect(state.messages[0]?.kind).toBe('user_answer')
    expect(state.messages[0]?.text).toBe('Because of caching.')
    expect(state.messages[0]?.questionNumber).toBe(1)
  })

  test('appendUserAnswer is idempotent on duplicate calls', () => {
    useSessionStore.getState().appendUserAnswer('q1', 'first', 1, 3)
    useSessionStore.getState().appendUserAnswer('q1', 'second', 1, 3)
    const state = useSessionStore.getState()
    expect(state.messages).toHaveLength(1)
    expect(state.messages[0]?.text).toBe('first')
  })

  test('appendFeedbackToken accumulates streamingFeedback by answerId', () => {
    useSessionStore.getState().appendFeedbackToken('a1', 'q1', 'Good')
    useSessionStore.getState().appendFeedbackToken('a1', 'q1', ' point')
    useSessionStore.getState().appendFeedbackToken('a1', 'q1', '!')
    const state = useSessionStore.getState()
    expect(state.streamingFeedback?.id).toBe('a1')
    expect(state.streamingFeedback?.text).toBe('Good point!')
    expect(state.streamingFeedback?.kind).toBe('ai_feedback_streaming')
    expect(state.streamingFeedback?.isStreaming).toBe(true)
  })

  test('commitStreamingFeedback moves streamingFeedback into messages', () => {
    useSessionStore.getState().appendFeedbackToken('a1', 'q1', 'partial')
    useSessionStore.getState().commitStreamingFeedback({
      answer_id: 'a1',
      question_id: 'q1',
      text: 'See `retry.ts:5` for context.',
      score: null,
      gaps: [],
    })
    const state = useSessionStore.getState()
    expect(state.streamingFeedback).toBeNull()
    expect(state.messages).toHaveLength(1)
    expect(state.messages[0]?.id).toBe('a1')
    expect(state.messages[0]?.kind).toBe('ai_feedback')
    expect(state.messages[0]?.text).toBe('See `retry.ts:5` for context.')
    expect(state.messages[0]?.isStreaming).toBe(false)
  })

  test('commitStreamingFeedback dedupes on answer_id (P15 pattern)', () => {
    // First commit lands.
    useSessionStore.getState().commitStreamingFeedback({
      answer_id: 'a1',
      question_id: 'q1',
      text: 'first',
      score: null,
      gaps: [],
    })
    // Replay arrives — must REPLACE the existing message, not append.
    useSessionStore.getState().commitStreamingFeedback({
      answer_id: 'a1',
      question_id: 'q1',
      text: 'second',
      score: null,
      gaps: [],
    })
    const state = useSessionStore.getState()
    expect(state.messages).toHaveLength(1)
    expect(state.messages[0]?.text).toBe('second')
  })

  test('setAnswerInputDisabled toggles the lock', () => {
    expect(useSessionStore.getState().answerInputDisabled).toBe(false)
    useSessionStore.getState().setAnswerInputDisabled(true)
    expect(useSessionStore.getState().answerInputDisabled).toBe(true)
    useSessionStore.getState().setAnswerInputDisabled(false)
    expect(useSessionStore.getState().answerInputDisabled).toBe(false)
  })

  test('clearSession wipes Story 3.4 streamingFeedback + answerInputDisabled', () => {
    useSessionStore.setState({
      streamingFeedback: {
        id: 'a1',
        kind: 'ai_feedback_streaming',
        questionNumber: 1,
        total: 3,
        text: 'partial',
        fileRefs: [],
        createdAt: '2026-04-10T00:00:00Z',
        isStreaming: true,
      },
      answerInputDisabled: true,
    })
    useSessionStore.getState().clearSession()
    const state = useSessionStore.getState()
    expect(state.streamingFeedback).toBeNull()
    expect(state.answerInputDisabled).toBe(false)
  })
})
