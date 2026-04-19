# Debug: SSE multi-turn result event delivery

## Goal

Verify that the `result` event from the Claude Code container reaches the frontend and that `isThinking` toggles to `false`, stopping the pulsing cursor. Use Playwright MCP browser tools and Chrome DevTools to observe the live SSE stream.

## Context

### Architecture
1. Ephemeral Docker container runs `claude -p "$PROMPT" --output-format stream-json`
2. API reads container stdout via `docker logs --follow`, relays as SSE (`GET /api/v1/containers/sessions/{id}/stream`)
3. Frontend connects via `EventSource`, parses stream-json events, renders conversation
4. After first turn, entrypoint enters `while read` loop on FIFO waiting for user messages
5. Container stays alive between turns; SSE stream stays open

### What we know
- Container logs confirm the `result` event IS emitted (`docker logs <id> | grep '"type":"result"'`)
- SSE stream delivers 80+ events to the browser (visible in Network tab)
- Frontend correctly hides `tool_use`, `tool_result`, `system/task_progress` events (by design)
- Only `assistant` events with `text` content blocks are rendered (typically 2-3 lines during analysis phase)
- A buffer flush fix was applied in `stream_events()` to prevent the last line (often the `result` event) from being silently dropped when docker log stream ends without trailing `\n`
- An `isThinking` state was added to `ContainerSession.tsx` that should toggle `false` on `result` events and `true` on `assistant` events

### Symptoms to confirm/deny
1. Does the `result` event appear in the SSE response body in Chrome DevTools Network tab?
2. Does the `onmessage` handler fire for the `result` event?
3. Does `isThinking` change to `false`?
4. Does the cursor stop pulsing?
5. After cursor stops, can the user type and send a message?
6. Does `claude -c -p` (continue) start in the container when a message is sent?

## Reproduction steps

1. Navigate to `http://localhost:5173`
2. Start a new challenge-me session on any PR (e.g., PR #10 on mariuspruvot/helprs)
3. Wait for Claude to finish its analysis (1-3 minutes of tool_use activity)
4. Observe: does the cursor stop pulsing? Does the final question text appear?

## Debug plan

### Step 1: Open the session page
Use Playwright to navigate to an active session URL or create a new one from the installation page.

### Step 2: Monitor SSE events in real-time
Take a browser snapshot to see the current UI state. Check console for errors. Use browser_network_requests to see the SSE stream status (pending vs completed).

### Step 3: Wait for Claude to finish
The container runs `claude -p` which takes 1-3 minutes (tool_use rounds reading the PR). Wait for events to stop flowing. Use browser_console_messages to check for any JS errors.

### Step 4: Check for the result event
After Claude finishes, examine:
- The Network tab response for the stream request — search for `"type":"result"` in the response body
- Console messages or errors related to parsing
- The DOM state — is the cursor element still visible? (`[data-testid="conversation-cursor"]`)

### Step 5: Verify isThinking state
Inject a check via browser_evaluate:
```javascript
// Check React state (may need React DevTools approach)
document.querySelector('[data-testid="conversation-cursor"]') !== null
```
If cursor is present, `isThinking` is still `true` (bug). If absent, the fix works.

### Step 6: Test sending a message
If cursor stopped, type a message in the input and send it. Check:
- Does the message appear in the conversation?
- Does the cursor start pulsing again?
- Does `docker logs` show a new `claude -c -p` invocation?

### Step 7: Check container state
Use browser_evaluate to call the session status API:
```javascript
const resp = await fetch('/api/v1/containers/sessions/<SESSION_ID>')
const data = await resp.json()
data.status // should be 'running'
```

## Key files

| File | What to check |
|------|--------------|
| `apps/web/src/features/session/ContainerSession.tsx` | `isThinking` state, `onmessage` handler (lines 224-245), `done` listener (lines 262-273) |
| `apps/web/src/features/session/containerTypes.ts` | `parseStreamMessage()` — `result` case returns `null` for success (line 216), only surfaces errors |
| `apps/api/src/helprs/modules/container/service.py` | `stream_events()` buffer flush after `StopAsyncIteration` (lines 330-338) |
| `apps/api/src/helprs/modules/container/router.py` | `_event_stream()` — emits `event: done` after stream ends (lines 153-167) |

## Likely outcomes

### If result event IS in SSE response but cursor still pulses
The `onmessage` handler receives the event and parses `raw.type === 'result'`, but `setIsThinking(false)` doesn't trigger a re-render or the state is overridden. Check React state.

### If result event is NOT in SSE response
The buffer flush fix didn't work, or the container's stdout buffering prevents the last line from being flushed before docker closes the log stream. Check `docker logs <container_id> | tail -5` to confirm the result event exists in container output.

### If result event arrives but much later
Docker log driver buffering delay. The result might arrive after a keepalive cycle (15s). Wait longer.

### If everything works but question text doesn't render
The `assistant` event containing the question text might have `content` blocks with only `thinking` type (no `text`). Check the raw SSE data for the last `assistant` event — does it have a `text` content block?
