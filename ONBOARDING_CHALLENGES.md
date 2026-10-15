# VoxBento Senior Engineer Onboarding Challenges

Welcome to VoxBento! These challenges are designed to test your understanding of our architecture, specifically the intersections between FastAPI WebSockets, our WebRTC/WHIP ingestion pipelines via MediaMTX, asynchronous background workers, and database state management.

These are realistic scenarios representing features and bug fixes that touch multiple layers of the application.

---

## Challenge 1: The "Ghost Participant" Bug

### Context
When a user joins a booth, their presence is managed via WebSockets in `portal/websockets/manager.py` (`ws_booth` endpoint). Upon connection, a unique `participant_id` is generated, and their state is stored in memory via `BoothRegistry`.

### Problem
If an interpreter is on a flaky Wi-Fi connection, their WebSocket might drop and automatically reconnect a few seconds later. When this happens, the backend assigns them a completely new `participant_id`. The room coordinator's UI now shows two participants for the same interpreter: the new active one, and a "ghost" participant from the dropped connection that remains indefinitely until the server restarts or a manual cleanup runs. If the interpreter was the `active_interpreter` when they dropped, handoff state gets confusing.

### Task
Implement a mechanism to handle WebSocket reconnections gracefully. If a participant reconnects within a short window (e.g., 30 seconds), they should resume their previous `participant_id` and role without creating a ghost.

### Expected Behavior
- When an interpreter temporarily loses connection and reconnects, the coordinator UI should not show a duplicate user.
- The `BoothRegistry` should correctly map the new WebSocket connection to the existing participant state.
- Stale, disconnected participants should be automatically cleaned up after a defined timeout period.

---

## Challenge 2: Persistent Booth State Across Server Restarts

### Context
Currently, the `BoothRegistry` in `portal/booth_state.py` stores all booth session data (active interpreter, participants, chat messages) entirely in process memory.

### Problem
If the FastAPI portal process crashes or is restarted for a deployment during a live event, all booth state is instantly lost. Active interpreters are silently dropped from the registry, chat history is gone, and MediaMTX WebRTC streams might get out of sync with the portal's understanding of who is publishing.

### Task
Modify the booth state architecture to persist essential state across restarts. You must persist the `active_interpreter_id` and essential participant metadata.

### Expected Behavior
- If the server restarts during a live event, the active interpreter remains active upon server recovery.
- Reconnecting interpreters after a restart should still see the correct state (e.g. who is active, recent chat history).
- The solution should not introduce significant latency to real-time WebSocket broadcasting.

---

## Challenge 3: Invalidation of `_created_paths` Cache

### Context
To allow interpreters to stream via WHIP, the portal dynamically creates paths on MediaMTX using the Control API. To prevent redundant API calls to MediaMTX, `portal/routers/api.py` maintains a process-global `set[str]` called `_created_paths`.

### Problem
If the MediaMTX container restarts independently of the FastAPI portal, MediaMTX loses its in-memory path configurations. The portal's `_created_paths` cache still thinks the paths exist. When an interpreter tries to start streaming, the WHIP request fails because the MediaMTX path doesn't actually exist, and the portal doesn't attempt to recreate it because it's still in the cache.

### Task
Implement a robust cache invalidation or synchronization strategy for `_created_paths`.

### Expected Behavior
- If MediaMTX restarts, the portal should detect the missing paths and successfully recreate them when an interpreter next attempts to connect, without requiring a manual restart of the FastAPI portal.
- The solution should not hammer the MediaMTX Control API with path creation requests on every WHIP connection under normal operation.

---

## Challenge 4: Audio Delay for Translated WHEP Playback

### Context
Attendees listen to translated audio via WHEP (WebRTC HTTP Egress Protocol) from MediaMTX. Sometimes, the video stream the attendees are watching (e.g., via a delayed RTMP feed to a large screen or embedded player) is delayed by several seconds compared to the real-time floor audio.

### Problem
Because VoxBento achieves sub-second latency, the translated audio arrives *before* the video action it corresponds to, creating a disjointed experience for attendees.

### Task
Utilize the newly added `rooms.audio_delay_ms` database column. The frontend listener client (`portal/static/js/whep-listener.js`) needs to know this value, and you need to implement a mechanism to apply this delay precisely on the listener side.

### Expected Behavior
- If an organizer sets `audio_delay_ms` to 2000 in the admin panel, the attendee's WHEP playback should be delayed by exactly 2 seconds relative to the incoming WebRTC packets.
- The delay must be applied client-side (in the browser) so that the MediaMTX, WHIP, and server-side transcription/translation pipelines remain unaffected.
- The delay should not introduce compounding drift over long sessions.

---

## Challenge 5: Dynamic Audio Transcription Worker Scaling

### Context
Transcription is handled by spawning background workers (`portal/transcription/worker.py`) that run `ffmpeg` to pull audio from MediaMTX via RTSP. Currently, there is a hardcoded `MAX_TOTAL_WORKERS = 10`.

### Problem
If a large event with 12 language booths starts, the 11th and 12th booths will silently fail to start transcription because the global process limit has been hit, even if the underlying server hardware is extremely powerful and could easily handle 50 concurrent workers.

### Task
Make the transcription worker limit configurable via the application settings (`portal/config.py`). Furthermore, handle the scenario where a worker *cannot* be started gracefully.

### Expected Behavior
- The maximum number of concurrent transcription workers should be defined by an environment variable (e.g., `MAX_TRANSCRIPTION_WORKERS`), defaulting to 10 if not set.
- If an interpreter joins a booth and the worker limit has been reached, the UI should explicitly inform them that transcription is currently unavailable due to server capacity limits, rather than failing silently or hanging.
- The `active_workers` tracking must remain thread/async-safe during these capacity checks.