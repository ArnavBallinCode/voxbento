# Admin & User Guide — Eventyay Interpretation Portal

## Quick Start

### 1. Set the admin password

```bash
# In .env or as environment variable
ADMIN_PASSWORD=your-secure-password
```

### 2. Start the portal

```bash
# Docker (recommended)
docker compose up --build

# Or native
uv run uvicorn fastapi_app:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Access the admin panel

1. Open http://localhost:8000/admin/login
2. Enter the `ADMIN_PASSWORD` you set
3. You're in the dashboard

---

## Admin Panel Guide

### Dashboard (`/admin/`)

Shows all events with live booth status and MediaMTX health indicator.

### Creating an Event

1. Go to **Events** → fill in slug (URL-safe, e.g. `pycon2026`) and display name
2. Click **Create Event**
3. Open the event to add rooms and booths

### Creating Rooms

1. Open an event → click **Rooms**
2. Enter room name → **Add Room**

### Creating Booths

1. Open a room → click **Booths**
2. Enter language code (2-letter ISO 639-1, e.g. `en`, `fr`, `es`) and language name
3. Click **Add Booth**

### Booth Detail Page

Each booth detail page shows:
- **Interpreter Page URL** — share this with interpreters
- **WHEP Listener URL** — for attendees (copy button provided)
- **MediaMTX Stream Path** — internal MediaMTX identifier
- **Live Status** — whether an interpreter is currently broadcasting
- **Active Interpreter** — who is currently live
- **Participant Roster** — all connected users with roles
- **Invite Tokens** — manage booth access tokens

---

## User Registration

### How users register

1. Visit http://localhost:8000/register
2. Fill in email, display name, password (min 8 characters)
3. Account is created with **listener** role
4. Redirected to account page

### What listeners can do

- Browse events on the home page
- Listen to live interpretation streams via WebRTC (WHEP)
- View their account info at `/account`

### What listeners cannot do

- Access the admin panel
- Go live as an interpreter
- Manage booths or events
- Self-assign higher roles

---

## Role Management

### Available roles (ordered by privilege)

| Role | Permissions |
|------|-------------|
| `listener` | View booths, listen to streams, send chat messages |
| `interpreter` | All listener permissions + go live (publish audio via WHIP) |
| `coordinator` | All listener permissions + assign active interpreter, manage handoffs |
| `event_admin` | All coordinator permissions + manage booths and generate invite tokens |
| `super_admin` | Full access to everything |

### Promoting a user

1. Log in to admin panel → go to **Users** (`/admin/users/`)
2. Find the user in the table
3. Use the **Role** dropdown to select the new role → auto-saves
4. The user's permissions update on their next page load

### Deactivating a user

1. Go to `/admin/users/`
2. Click **Deactivate** next to the user
3. The user can no longer log in
4. Click **Activate** to re-enable

### Deleting a user

1. Go to `/admin/users/`
2. Click **Delete** → confirm in the dialog
3. This is permanent and cannot be undone

---

## Typical Workflow for an Event

### Before the event

1. **Admin** creates event, rooms, and booths in the admin panel
2. **Admin** promotes registered users to `interpreter` or `coordinator` roles
3. **Admin** optionally generates invite tokens for booth access
4. **Admin** shares interpreter page URLs with interpreters

### During the event

1. **Interpreters** open their booth URL, join, and go live
2. **Listeners** visit the home page, find their event, and click "Listen"
3. **Coordinators** manage interpreter handoffs within booths
4. **Admin** monitors live status from the dashboard

### After the event

1. Booths stop automatically when interpreters disconnect
2. Admin can delete events/rooms/booths to clean up
3. User accounts persist for future events

---

## Environment Variables Reference

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `ADMIN_PASSWORD` | *(empty)* | Yes (for admin access) | Password for admin panel login |
| `SECRET_KEY` | `change-me` | Yes (production) | JWT signing key — use 64+ random chars |
| `DATABASE_URL` | `sqlite+aiosqlite:///./interpretation.db` | No | Database connection string |
| `MEDIAMTX_WHIP_BASE` | `http://localhost:8889` | No | Browser-facing WHIP/WHEP URL |
| `MEDIAMTX_HLS_BASE` | `http://localhost:8888` | No | Browser-facing HLS URL |
| `JITSI_DOMAIN` | `localhost:8080` | No | Jitsi Meet domain |

---

## Database Commands

```bash
# Apply all migrations (creates tables)
alembic upgrade head

# Check current migration version
alembic current

# After adding/changing models, generate a new migration
alembic revision --autogenerate -m "describe the change"
```

In Docker, migrations run automatically on container startup.
