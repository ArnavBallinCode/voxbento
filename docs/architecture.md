# Architecture

Voxbento is a real-time interpretation platform for live events. It provides a browser-first, zero-install experience for simultaneous interpreters.

## How it works

```
Interpreter browser
  |  iframe -> Jitsi Meet (Monitor conference floor video/audio)
  |  mic -> RTCPeerConnection -> WHIP POST
  v
MediaMTX :8889 (WHIP ingest + WHEP)   Python is never in the audio path
  |  WebRTC termination + remux
  |--> WHEP :8889 <-- attendees connect via WebRTC (sub-second latency)

Interpreter / Coordinator browser
  |  WebSocket /ws/booth/{booth_id}
  v
FastAPI portal :8000 (coordination, state, JWT, REST)
  |
  |--> Background Transcription (ffmpeg -> Deepgram/OpenAI/Local)
  |--> Background Translation (Groq/Anthropic/Gemini)

Floor Audio Bot (floor-bot)
  |  Headless Chromium -> Joins Jitsi Meeting
  |--> ffmpeg -> RTSP -> MediaMTX -> Transcription/Translation
```

## Services
* FastAPI Portal (Python 3.13)
* MediaMTX
* self-hosted Jitsi Meet
