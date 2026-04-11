/**
 * Story 3.4: pure async parser for an SSE byte stream over a `fetch`
 * `ReadableStream`. Used by the answer-submission flow because the POST
 * endpoint streams `text/event-stream` and `EventSource` is GET-only.
 *
 * Lives next to ``useSSE.ts`` because both deal with SSE — but this is
 * NOT a React hook. It's a plain async function the caller wraps in
 * whatever lifecycle management it needs (a `useEffect`, a one-shot
 * promise, etc.).
 *
 * Frame format (single source of truth — backend `_sse_frame` writes
 * exactly this shape):
 *
 *     event: <name>\n
 *     data: <json>\n
 *     \n
 *
 * Multiple frames are separated by ``\n\n``. The parser buffers
 * cross-chunk frame boundaries.
 */

export interface ParseSSEHandlers {
  /**
   * Called once per fully-parsed SSE frame. ``data`` is the result of
   * `JSON.parse` on the frame's data line — the caller is responsible
   * for type-narrowing per ``event``.
   */
  onEvent: (event: string, data: unknown) => void
  /**
   * Called for any error during parsing — typically a malformed JSON
   * data line. The reader keeps going; the caller decides whether to
   * abort the stream.
   */
  onError: (err: Error) => void
}

/**
 * Drain a `ReadableStreamDefaultReader<Uint8Array>` of SSE frames,
 * dispatching each parsed frame via ``handlers.onEvent``.
 *
 * Returns when the underlying stream closes (reader.read() resolves
 * to ``done: true``). The caller should call ``reader.cancel()`` if
 * it wants to stop early.
 */
export async function consumeSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  handlers: ParseSSEHandlers,
): Promise<void> {
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      // Story 3.4 P22 (code-review B16): a proxy that truncates the
      // final frame mid-``event:`` or mid-``data:`` leaves us with a
      // partial tail. Only dispatch if the tail parses as a well-formed
      // frame (has both ``event:`` and ``data:``); otherwise surface
      // via ``onError`` so the caller can log / react.
      if (buffer.trim()) {
        dispatchFrame(buffer, handlers, /* allowPartial */ false)
      }
      return
    }
    buffer += decoder.decode(value, { stream: true })
    // Split out every complete frame in the buffer. The trailing
    // partial frame (if any) stays in ``buffer`` for the next chunk.
    let separatorIdx = buffer.indexOf('\n\n')
    while (separatorIdx !== -1) {
      const frame = buffer.slice(0, separatorIdx)
      buffer = buffer.slice(separatorIdx + 2)
      if (frame.trim()) {
        dispatchFrame(frame, handlers, /* allowPartial */ false)
      }
      separatorIdx = buffer.indexOf('\n\n')
    }
  }
}

function dispatchFrame(
  frame: string,
  handlers: ParseSSEHandlers,
  allowPartial: boolean,
): void {
  let eventName: string | null = null
  let dataLine: string | null = null
  let hadUnknownField = false
  for (const line of frame.split('\n')) {
    if (line.length === 0) continue
    // Story 3.4 P22 (code-review B15): SSE spec fields we don't use
    // but shouldn't fail on: ``id:``, ``retry:``, and comment lines
    // (``:`` prefix — used by proxies as keepalive). Accept and skip.
    if (line.startsWith(':')) continue
    if (line.startsWith('id:') || line.startsWith('retry:')) continue
    if (line.startsWith('event: ')) {
      eventName = line.slice('event: '.length).trim()
    } else if (line.startsWith('data: ')) {
      // Concatenate multi-line ``data:`` payloads (the SSE spec
      // technically allows them, though our backend only emits
      // single-line JSON). Joining with ``\n`` keeps fidelity even
      // for the multi-line case.
      const part = line.slice('data: '.length)
      dataLine = dataLine === null ? part : `${dataLine}\n${part}`
    } else {
      hadUnknownField = true
    }
  }
  if (!eventName || dataLine === null) {
    if (!allowPartial) {
      handlers.onError(
        new Error(
          hadUnknownField
            ? 'SSE frame has unknown fields and no event/data pair'
            : 'SSE frame missing event or data line (truncated tail?)',
        ),
      )
    }
    return
  }
  try {
    const parsed = JSON.parse(dataLine) as unknown
    handlers.onEvent(eventName, parsed)
  } catch (err) {
    handlers.onError(err instanceof Error ? err : new Error(String(err)))
  }
}
