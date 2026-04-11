import { describe, expect, test, vi } from 'vitest'
import { consumeSSEStream } from './parseSSE'

/**
 * Build a fake `ReadableStreamDefaultReader<Uint8Array>` from a series
 * of strings. Each string lands as one ``read()`` call.
 */
function fakeReader(chunks: string[]): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder()
  let i = 0
  return {
    async read() {
      if (i >= chunks.length) {
        return { done: true, value: undefined as unknown as Uint8Array }
      }
      const value = encoder.encode(chunks[i]!)
      i += 1
      return { done: false, value }
    },
    async cancel() {
      i = chunks.length
    },
    releaseLock() {},
    closed: Promise.resolve(undefined),
  } as unknown as ReadableStreamDefaultReader<Uint8Array>
}

describe('consumeSSEStream', () => {
  test('parses a single complete frame', async () => {
    const events: Array<[string, unknown]> = []
    const onEvent = vi.fn((event: string, data: unknown) => events.push([event, data]))
    const onError = vi.fn()

    await consumeSSEStream(
      fakeReader(['event: feedback_token\ndata: {"token":"hi"}\n\n']),
      { onEvent, onError },
    )

    expect(events).toEqual([['feedback_token', { token: 'hi' }]])
    expect(onError).not.toHaveBeenCalled()
  })

  test('parses multiple events in one chunk', async () => {
    const events: Array<[string, unknown]> = []
    await consumeSSEStream(
      fakeReader([
        'event: feedback_token\ndata: {"token":"a"}\n\n' +
          'event: feedback_token\ndata: {"token":"b"}\n\n' +
          'event: done\ndata: {}\n\n',
      ]),
      { onEvent: (e, d) => events.push([e, d]), onError: vi.fn() },
    )
    expect(events).toEqual([
      ['feedback_token', { token: 'a' }],
      ['feedback_token', { token: 'b' }],
      ['done', {}],
    ])
  })

  test('handles a frame split across two chunks', async () => {
    const events: Array<[string, unknown]> = []
    await consumeSSEStream(
      fakeReader(['event: feedback_token\ndata: {"tok', 'en":"hi"}\n\n']),
      { onEvent: (e, d) => events.push([e, d]), onError: vi.fn() },
    )
    expect(events).toEqual([['feedback_token', { token: 'hi' }]])
  })

  test('handles the frame separator landing on a chunk boundary', async () => {
    const events: Array<[string, unknown]> = []
    await consumeSSEStream(
      fakeReader([
        'event: feedback_token\ndata: {"token":"a"}\n',
        '\nevent: done\ndata: {}\n\n',
      ]),
      { onEvent: (e, d) => events.push([e, d]), onError: vi.fn() },
    )
    expect(events).toEqual([
      ['feedback_token', { token: 'a' }],
      ['done', {}],
    ])
  })

  test('skips frames without a JSON-parseable data line', async () => {
    const events: Array<[string, unknown]> = []
    const errors: Error[] = []
    await consumeSSEStream(
      fakeReader(['event: bad\ndata: not-json\n\nevent: ok\ndata: {"x":1}\n\n']),
      { onEvent: (e, d) => events.push([e, d]), onError: (e) => errors.push(e) },
    )
    expect(errors).toHaveLength(1)
    // The good frame still arrived.
    expect(events).toEqual([['ok', { x: 1 }]])
  })

  test('skips a malformed frame missing event or data', async () => {
    const events: Array<[string, unknown]> = []
    await consumeSSEStream(
      fakeReader([
        'data: {"orphan":1}\n\n', // no event line
        'event: lonely\n\n', // no data line
        'event: ok\ndata: {}\n\n',
      ]),
      { onEvent: (e, d) => events.push([e, d]), onError: vi.fn() },
    )
    expect(events).toEqual([['ok', {}]])
  })

  test('flushes a trailing frame on stream close (no final \\n\\n)', async () => {
    const events: Array<[string, unknown]> = []
    await consumeSSEStream(
      fakeReader(['event: done\ndata: {"x":1}']),
      { onEvent: (e, d) => events.push([e, d]), onError: vi.fn() },
    )
    expect(events).toEqual([['done', { x: 1 }]])
  })
})
