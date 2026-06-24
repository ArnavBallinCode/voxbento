# VoxBento — Project Context

> High-level context file for coding agents, derived from `REPOSITORY_CONTEXT.md` and `AI_WORKFLOWS.md`.

## Overview
**VoxBento** is a production-grade browser-first interpretation booth console for Eventyay live events.
It provides sub-second latency via WebRTC/WHIP to MediaMTX for audio ingest, and WHEP for playback.
All coordination (auth, booth state, handoffs, and live captions) flows through FastAPI WebSockets.

## Architecture
- **Web Backend:** Python 3.13 / FastAPI / Uvicorn (async via ASGI).
- **Media Server:** MediaMTX (handles WHIP, WHEP, RTSP, HLS fallback).
- **Floor Audio:** Jitsi Meet (self-hosted iframe). `floor-bot` joins via headless Chromium to stream floor audio.
- **Database:** SQLAlchemy 2.0 async + Alembic. Dev uses SQLite (`aiosqlite`); Prod uses PostgreSQL (`asyncpg`).
- **Auth:** Custom PyJWT (HS256) implementation with bcrypt. Three token types: `session_token`, `user_token`, `admin_token`.
- **Transcription Pipeline:** RTSP pulled via ffmpeg to providers (faster-whisper, OpenAI, Deepgram, NVIDIA, ElevenLabs).
- **Translation Pipeline:** LLM-based (OpenAI, Anthropic, Groq, Gemini) translation of transcript segments, with optional Deepgram Aura TTS.

## Key Rules & Invariants
- Python must strictly be `3.13.x` and `from __future__ import annotations` is required in all files.
- No heavy frontend frameworks (Vue, React). Use vanilla ES modules in `static/js/`.
- No Socket.IO or Flask; strictly FastAPI WebSockets.
- `uv.lock` is the single source of truth for Python dependencies (`uv sync --python 3.13 --dev`).
- Role is NEVER trusted from client WebSocket payloads; use `session.granted_role`.
- `ARCHITECTURE.md` is deprecated; system design details are in `docs/how-it-works.mdx`.
- There are currently 15 Alembic migrations in the project.

For deep dives, see:
- `REPOSITORY_CONTEXT.md` (Authentication, Identity, Ports)
- `ROUTE_MAP.md` (Endpoints & WebSockets)
- `DATABASE_MAP.md` (Models & Schemas)
- `TRANSCRIPTION_MAP.md` (Audio Pipeline)
