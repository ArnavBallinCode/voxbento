# Eventyay Interpretation Portal

Real-time interpretation coordination for Eventyay events.
Interpreters stream live audio via WebRTC/WHIP → MediaMTX → WHEP (WebRTC playback).
HLS is retained as a fallback delivery path.
Booth coordination (who is active, relay handoff, chat) runs over WebSocket.

---

## How it works

```
Interpreter browser
  │  mic → RTCPeerConnection → WHIP POST
  ▼
MediaMTX :8889 (WHIP ingest + WHEP)   Python is never in the audio path
  │  WebRTC termination + remux
  ├──► WHEP :8889 (primary) ←── attendees connect via WebRTC (sub-second latency)
  └──► HLS  :8888 (fallback) ←── attendees pull index.m3u8 (~2-3 s latency)

Interpreter / Coordinator browser
  │  WebSocket /ws/booth/{booth_id}
  ▼
FastAPI portal :8000 (coordination, state, JWT, REST)
```

**Seamless interpreter handoff**: when the coordinator switches the active interpreter,
MediaMTX's `overridePublisher: yes` lets the incoming interpreter connect immediately
while kicking the outgoing one. MediaMTX paths are created with `alwaysAvailable: true`
via the Control API so WHEP listeners stay connected during handoff and receive the
new publisher's audio within ~1.5–3 s. HLS fallback listeners auto-recover with a
longer gap (~10–15 s).

---

## Setup

### Option 1 — Docker Compose (recommended)

Everything starts with one command. No Python, MediaMTX, or manual config needed.

```bash
git clone https://github.com/fossasia/eventyay-interpretation-portal.git
cd eventyay-interpretation-portal

# Set admin password (required for admin panel access)
echo 'ADMIN_PASSWORD=my-secure-admin-pass' >> .env

docker compose up --build
```

Open http://localhost:8000. That is it.

**Admin panel:** Go to http://localhost:8000/admin/login and enter your `ADMIN_PASSWORD`.
From there you can create events, rooms, booths, and manage users.

**User registration:** Anyone can register at http://localhost:8000/register.
New accounts get `listener` access by default. Admins can promote users to interpreter,
coordinator, or event_admin from `/admin/users/`.

| Service | Port | Purpose |
|---------|------|---------|
| FastAPI portal | 8000 | Web UI, REST API, WebSocket |
| MediaMTX WHEP/WHIP | 8889 | WebRTC playback (WHEP) and ingest (WHIP) |
| MediaMTX HLS | 8888 | HLS fallback stream for attendees |
| MediaMTX Control API | 9997 | Dynamic path management (alwaysAvailable) |
| Jitsi Web | 8443 | Self-hosted video conferencing (interpreter monitors speaker) |
| Jitsi JVB | 10000/udp | Jitsi media traffic |

To stop: `Ctrl+C` or `docker compose down`.

### Option 2 — Native (two terminals)

**Requirements**: Python 3.13+, [uv](https://github.com/astral-sh/uv), [MediaMTX](https://github.com/bluenviron/mediamtx/releases)

```bash
git clone https://github.com/fossasia/eventyay-interpretation-portal.git
cd eventyay-interpretation-portal
uv sync                      # install Python dependencies
```

Download MediaMTX for your platform from [releases](https://github.com/bluenviron/mediamtx/releases):

```bash
# macOS ARM64 example
curl -sL https://github.com/bluenviron/mediamtx/releases/download/v1.12.3/mediamtx_v1.12.3_darwin_arm64.tar.gz \
  | tar xzf - mediamtx
chmod +x mediamtx
```

**Terminal 1 — MediaMTX:**
```bash
./mediamtx mediamtx.yml
```

**Terminal 2 — FastAPI:**
```bash
# Set admin password for admin panel access
export ADMIN_PASSWORD='my-secure-admin-pass'

uv run uvicorn fastapi_app:app --host 127.0.0.1 --port 8000 --reload
```

Open http://localhost:8000.

### Verify it works

```bash
curl http://localhost:8000/healthz
# {"ok": true, "server": "fastapi", "mediamtx_ok": true}
```

### Test audio end-to-end

1. Open http://localhost:8000/interpreter/demo-booth
2. Enter a name, select **Interpreter**, click **Join Booth**
3. Click **Go Live** — allow microphone when prompted
4. Open http://localhost:8000/listener-webrtc/demo-booth in another tab (WHEP WebRTC listener, sub-second latency)
   — or http://localhost:8000/listen/demo-booth for the HLS fallback (hls.js, ~3 s delay)
   — or use VLC: File → Open Network → `http://localhost:8888/demo-booth-audio/index.m3u8`
5. Speak — you should hear yourself with <1 s delay on the WHEP listener

### Environment variables

Copy `.env.example` → `.env` and adjust as needed:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | `change-me` | JWT signing key |
| `BOOTH_ACCESS_TOKEN` | *(empty)* | Booth password (empty = open access) |
| `JITSI_DOMAIN` | `localhost:8443` | Jitsi Meet domain (self-hosted via Docker) |
| `DEFAULT_JITSI_ROOM` | `eventyay-stage-room` | Default Jitsi room for interpreter monitoring |
| `MEDIAMTX_WHIP_BASE` | `http://localhost:8889` | Browser-facing WHIP URL |
| `MEDIAMTX_HLS_BASE` | `http://localhost:8888` | Browser-facing HLS URL |
| `MEDIAMTX_INTERNAL_BASE` | *(empty)* | Python→MediaMTX URL (Docker: `http://mediamtx:8888`) |
| `MEDIAMTX_API_BASE` | `http://localhost:9997` | MediaMTX Control API for dynamic path management |
| `ADMIN_PASSWORD` | *(empty)* | Admin panel login password |
| `DATABASE_URL` | `sqlite+aiosqlite:///./interpretation.db` | Database connection string (PostgreSQL for production) |
| `JVB_AUTH_PASSWORD` | `changeme` | Jitsi JVB auth (change in production) |
| `JICOFO_AUTH_PASSWORD` | `changeme` | Jitsi Jicofo auth (change in production) |

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Home page with event list and listener links |
| `GET`  | `/register` | User registration page |
| `POST` | `/register` | Create listener account |
| `GET`  | `/login` | User login page |
| `POST` | `/login` | Authenticate and set session cookie |
| `GET`  | `/logout` | Clear session cookie |
| `GET`  | `/account` | User account page (role, status) |
| `GET`  | `/interpreter/{booth_id}` | Interpreter booth UI |
| `GET`  | `/listener-webrtc/{booth_id}` | Attendee WHEP listener (WebRTC, primary) |
| `GET`  | `/listen/{booth_id}` | Attendee HLS listener (hls.js, fallback) |
| `POST` | `/api/auth/token` | Issue a signed JWT |
| `GET`  | `/api/booth/{booth_id}/state` | Current booth snapshot |
| `GET`  | `/api/interpreter/status/{channel_id}` | MediaMTX reachability |
| `GET`  | `/healthz` | Health check |
| `WS`   | `/ws/booth/{booth_id}` | Booth coordination WebSocket |

### Admin panel routes

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/admin/login` | Admin login page |
| `POST` | `/admin/login` | Validate admin password |
| `GET`  | `/admin/` | Dashboard with event cards and live status |
| `GET`  | `/admin/events/` | Event list + create form |
| `GET`  | `/admin/events/{id}/` | Event detail with rooms and booths |
| `GET`  | `/admin/events/{id}/rooms/` | Room list + create form |
| `GET`  | `/admin/events/{id}/rooms/{id}/` | Room detail with interpreter URLs |
| `GET`  | `/admin/events/{id}/rooms/{id}/booths/` | Booth list + create form |
| `GET`  | `/admin/events/{id}/rooms/{id}/booths/{id}/` | Booth detail: WHEP URL, participants, tokens |
| `GET`  | `/admin/users/` | User management: roles, activate/deactivate |

### WebSocket messages (client → server)

| Type | Fields | Purpose |
|------|--------|---------|
| `booth:join` | `display_name`, `role`, `language`, `channel_id` | Enter a booth |
| `booth:leave` | — | Leave gracefully |
| `booth:update-state` | `mic_active`, `ingest_connected` | Report audio state |
| `booth:set-active` | `target_id` | Assign new active interpreter |
| `booth:chat` | `body` | Send chat message |

Server broadcasts `booth:state` to all connections on every state change.

---

## Development

```bash
uv sync --all-groups          # runtime + dev dependencies
uv run pytest tests/ -v       # run test suite
node --check static/js/interpreter-booth.js   # JS syntax
```

### Database

The portal uses SQLAlchemy 2.0 (async) for persistent storage and Alembic for schema migrations.
SQLite is the default for development; PostgreSQL is supported for production via `DATABASE_URL`.

```bash
# Apply migrations (creates tables if needed)
alembic upgrade head

# After changing models, generate a migration
alembic revision --autogenerate -m "describe the change"

# Apply the new migration
alembic upgrade head
```

The SQLite database file (`interpretation.db`) is git-ignored. Migration scripts in
`alembic/versions/` are committed — they are the version-controlled schema history.

In Docker, `docker compose up` runs migrations automatically on startup. The database
file is stored on a named volume (`portal-data`) that persists across `docker compose down`
/ `docker compose up` cycles.

### Project layout

```
fastapi_app.py                # FastAPI — REST, WebSocket, Jinja2
portal/
  config.py                   # pydantic-settings (env vars / .env)
  auth.py                     # JWT issue / validate
  booth_state.py              # async in-memory booth registry
  booth_identity.py           # booth ID ↔ MediaMTX path mapping
  roles.py                    # Permission enum, role-permission mapping
  models.py                   # SQLAlchemy declarative models (Event, Room, DBBooth, InviteToken, User)
  database.py                 # async engine, session factory, CRUD helpers
alembic/
  env.py                      # async-aware Alembic environment
  versions/                   # migration scripts (committed to version control)
templates/
  home.html                   # public home page with event list
  register.html               # user registration form
  login.html                  # user login form
  account.html                # user account page
  interpreter_booth.html      # Jinja2 interpreter booth page
  listener.html               # Jinja2 attendee page (hls.js fallback)
  listener-webrtc.html        # Jinja2 attendee page (WHEP WebRTC, primary)
  admin/                      # admin panel templates (dashboard, CRUD, users)
static/
  js/interpreter-booth.js     # Plain browser JS — WebRTC/WHIP + WebSocket
  js/whep-listener.js         # WHEP WebRTC listener client
  css/interpreter.css
  css/admin.css               # admin panel and auth page styles
mediamtx.yml                  # MediaMTX config (WHIP ingest, WHEP playback, HLS fallback, Control API)
docker-compose.yml            # portal + mediamtx + jitsi services
Dockerfile                    # FastAPI container (uv, Python 3.13-slim)
tests/
  test_fastapi_app.py         # REST + WebSocket integration tests
  test_booth_state.py         # booth registry unit tests
  test_booth_identity.py      # booth identity scheme tests
  test_roles.py               # permission model tests
  test_database.py            # database model + CRUD tests
  test_admin_panel.py         # admin panel route tests
  test_user_auth.py           # registration, login, account, user management tests
  test_join_flow.py           # invite-token join flow tests
```

### Admin panel setup

```bash
# Set the admin password (required for admin access)
export ADMIN_PASSWORD='your-secure-password'

# Start the server
uv run uvicorn fastapi_app:app --host 127.0.0.1 --port 8000 --reload

# Visit http://localhost:8000/admin/login and enter the password
```

### Creating events, rooms, and booths

1. Log in to the admin panel at `/admin/login`
2. Go to **Events** → create an event (slug + display name)
3. Open the event → go to **Rooms** → create a room
4. Open the room → go to **Booths** → create a booth (language code + name)
5. The booth detail page shows:
   - Interpreter page URL (share with interpreters)
   - WHEP listener URL (for attendees)
   - Invite token management

### User registration and role management

1. Users register at `/register` — they get a **listener** account by default
2. Admins go to `/admin/users/` to manage registered users
3. Change a user's role via the dropdown (listener → interpreter → coordinator → event_admin → super_admin)
4. Deactivate users to prevent login without deleting their account
