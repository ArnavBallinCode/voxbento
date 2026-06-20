# VoxBento System Architecture

Voxbento is a production-grade **browser-first interpretation booth console** for Eventyay live events.
Interpreters monitor a floor session via a self-hosted Jitsi iframe and publish audio via WebRTC/WHIP to MediaMTX.
Attendees receive sub-second audio via WHEP. All coordination flows through FastAPI WebSockets.

## Component Overview

```
Interpreter browser
  │  iframe → Jitsi Meet (Monitor conference floor video/audio)
  │  mic → RTCPeerConnection → WHIP POST
  ▼
MediaMTX :8889 (WHIP ingest + WHEP)   Python is never in the audio path
  │  WebRTC termination + remux
  └──► WHEP :8889 ←── attendees connect via WebRTC (sub-second latency)

Interpreter / Coordinator browser
  │  WebSocket /ws/booth/{booth_id}
  ▼
FastAPI portal :8000 (coordination, state, JWT, REST)
  │
  ├──► Background Transcription (ffmpeg → Deepgram/OpenAI/Local)
  └──► Background Translation (Groq/Anthropic/Gemini)

Floor Audio Bot (floor-bot)
  │  Headless Chromium → Joins Jitsi Meeting
  └──► ffmpeg → RTSP → MediaMTX → Transcription/Translation
```

## Technology Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.13+ |
| Web framework | FastAPI + uvicorn |
| Media server | MediaMTX (WHIP/WHEP/RTSP/HLS) |
| Floor monitoring | Jitsi Meet (self-hosted, receive-only iframe) |
| Database | PostgreSQL (production), SQLite (development) |
| ORM / migrations | SQLAlchemy 2.0 async + Alembic |
| Auth | PyJWT (HS256) + bcrypt |
| API key crypto | Fernet (cryptography) |
| Transcription | faster-whisper + cloud providers (OpenAI, Deepgram, ElevenLabs, NVIDIA Riva) |
| Frontend | Vanilla ES modules, Jinja2 templates |

## Core Principles

1. **One active publisher per language channel.** MediaMTX enforces `overridePublisher: yes`; Python enforces via `BoothRegistry`.
2. **Interpreter mic audio never routes to `AudioContext.destination`.** No local loopback.
3. **No OBS/RTMP/external encoder.** Browser-only ingest via WHIP.
4. **Jitsi is monitoring only** — receive-only iframe. Not the ingest transport.
5. **No framework.** Frontend is plain ES modules.
