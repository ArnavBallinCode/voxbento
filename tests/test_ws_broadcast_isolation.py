"""Regression tests: booth broadcasts reach only booth-authorized sockets.

Sockets are added to the booth room at WebSocket-connect time, but
ConnectionManager.broadcast delivers only to sockets whose session carries
a role granted for that booth. A socket with no booth role — unauthenticated,
or holding only another booth's invitation — stays connected yet receives no
booth:state or booth:chat broadcasts, even when BOOTH_ACCESS_TOKEN is unset.
"""

from __future__ import annotations

import json
import os
import threading

# Unset access token: the configuration under test (open handshake mode).
os.environ["BOOTH_ACCESS_TOKEN"] = ""

import pytest
from fastapi.testclient import TestClient

from fastapi_app import app
from portal.auth import create_participant_token, create_user_token
from portal.websockets.manager import manager

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    import anyio

    from portal.database import configure, dispose, init_db

    configure("sqlite+aiosqlite://")
    anyio.run(init_db)
    yield
    anyio.run(dispose)


def _invite_cookie(event_slug: str, room_id: int, language_code: str) -> dict:
    tok = create_participant_token(
        booth_id=1,
        role="interpreter",
        event_slug=event_slug,
        room_id=room_id,
        language_code=language_code,
    )
    return {"session_token": tok}


def _admin_cookie() -> dict:
    return {"user_token": create_user_token(user_id=1, email="admin@test.com", is_admin=True)}


def _join(ws, display_name: str = "Pat", role: str = "interpreter", language: str = "French") -> dict:
    ws.send_text(
        json.dumps(
            {
                "type": "booth:join",
                "display_name": display_name,
                "role": role,
                "language": language,
            }
        )
    )
    joined = json.loads(ws.receive_text())
    assert joined["type"] == "booth:joined"
    # A booth:state broadcast always follows a successful join; drain it so
    # later reads observe only subsequently triggered broadcasts.
    state = json.loads(ws.receive_text())
    assert state["type"] == "booth:state"
    return joined


def _room_size(bid: str) -> int:
    return len(manager._rooms.get(bid, set()))


def _try_receive(ws, timeout: float) -> list:
    """Collect messages for up to timeout seconds without hanging the test."""
    got: list = []
    stop = threading.Event()

    def _recv() -> None:
        try:
            while not stop.is_set():
                got.append(ws.receive_text())
        except Exception:
            pass

    t = threading.Thread(target=_recv, daemon=True)
    t.start()
    t.join(timeout=timeout)
    stop.set()
    return got


def test_joined_participant_receives_chat_broadcast():
    """An authorized participant joins and receives its booth's broadcasts."""
    bid = "iso-11-en"
    with client.websocket_connect(f"/ws/booth/{bid}", cookies=_invite_cookie("iso", 11, "en")) as ws:
        _join(ws)
        assert _room_size(bid) == 1
        ws.send_text(json.dumps({"type": "booth:chat", "body": "hello booth"}))
        chat = json.loads(ws.receive_text())
        assert chat["type"] == "booth:chat"
        assert chat["message"]["body"] == "hello booth"


def test_authorized_not_joined_still_receives_state():
    """An authorized socket observes membership changes before joining.

    Multi-party flows (standby/coordinator observers) depend on queued
    join broadcasts; booth authorization — not join state — gates delivery.
    """
    bid = "iso-12-en"
    with client.websocket_connect(f"/ws/booth/{bid}", cookies=_admin_cookie()) as observer:
        with client.websocket_connect(f"/ws/booth/{bid}", cookies=_admin_cookie()) as actor:
            _join(actor, display_name="Actor")
        got = _try_receive(observer, timeout=2.0)
        assert any(json.loads(m).get("type") == "booth:state" for m in got)


def test_unauthenticated_socket_receives_no_state_broadcast():
    """A socket with no session gets no booth:state."""
    bid = "iso-13-en"
    with client.websocket_connect(f"/ws/booth/{bid}") as passive:
        with client.websocket_connect(f"/ws/booth/{bid}", cookies=_admin_cookie()) as actor:
            _join(actor, display_name="Actor")
        got = _try_receive(passive, timeout=2.0)
        assert got == []


def test_unauthenticated_socket_receives_no_chat_broadcast():
    """A socket with no session gets no booth:chat."""
    bid = "iso-14-en"
    with client.websocket_connect(f"/ws/booth/{bid}") as passive:
        with client.websocket_connect(f"/ws/booth/{bid}", cookies=_admin_cookie()) as actor:
            _join(actor, display_name="Actor")
            actor.send_text(json.dumps({"type": "booth:chat", "body": "secret chatter"}))
            echo = json.loads(actor.receive_text())
            assert echo["type"] == "booth:chat"
        got = _try_receive(passive, timeout=2.0)
        assert got == []


def test_cross_booth_invite_receives_no_broadcasts():
    """An invite for booth A yields no broadcasts on booth B."""
    bid_b = "iso-15-fr"
    with client.websocket_connect(f"/ws/booth/{bid_b}", cookies=_invite_cookie("iso", 15, "en")) as passive:
        with client.websocket_connect(f"/ws/booth/{bid_b}", cookies=_admin_cookie()) as actor:
            _join(actor, display_name="Actor", language="German")
            actor.send_text(json.dumps({"type": "booth:chat", "body": "booth B private"}))
            assert json.loads(actor.receive_text())["type"] == "booth:chat"
        got = _try_receive(passive, timeout=2.0)
        assert got == []


def test_unauthorized_join_receives_nothing_afterwards():
    """A rejected join is followed by no broadcasts to that socket."""
    bid = "iso-16-en"
    with client.websocket_connect(f"/ws/booth/{bid}") as ws:
        ws.send_text(
            json.dumps({"type": "booth:join", "display_name": "Hacker", "role": "interpreter", "language": "French"})
        )
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "booth:error"
        with client.websocket_connect(f"/ws/booth/{bid}", cookies=_admin_cookie()) as actor:
            _join(actor, display_name="Actor")
            actor.send_text(json.dumps({"type": "booth:chat", "body": "after rejected join"}))
        got = _try_receive(ws, timeout=2.0)
        assert got == []


def test_disconnect_leaves_no_stale_membership():
    """Join then disconnect removes the socket from the room."""
    import time

    bid = "iso-17-en"
    with client.websocket_connect(f"/ws/booth/{bid}", cookies=_admin_cookie()) as ws:
        _join(ws)
        assert _room_size(bid) == 1
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if _room_size(bid) == 0:
            break
        time.sleep(0.05)
    assert _room_size(bid) == 0


def test_silent_socket_receives_nothing_at_connect_time():
    """A socket that connects into an already-active booth and never joins
    receives no booth data (connect-time delivery check).

    The unknown-type ping is a sync barrier, not a join: its booth:error
    reply proves the server task has run and manager.add() completed, so a
    subsequent broadcast cannot slip past before registration.
    """
    bid = "iso-19-en"
    with client.websocket_connect(f"/ws/booth/{bid}", cookies=_admin_cookie()) as actor:
        _join(actor, display_name="Actor")
        with client.websocket_connect(f"/ws/booth/{bid}") as passive:
            passive.send_text(json.dumps({"type": "booth:ping-sync"}))
            sync_reply = json.loads(passive.receive_text())
            assert sync_reply["type"] == "booth:error"
            actor.send_text(json.dumps({"type": "booth:chat", "body": "after passive arrived"}))
            assert json.loads(actor.receive_text())["type"] == "booth:chat"
            got = _try_receive(passive, timeout=2.0)
            assert got == []


def test_coordinator_join_behavior_intact():
    """A coordinator join still works and receives broadcasts."""
    bid = "iso-18-en"
    with client.websocket_connect(f"/ws/booth/{bid}", cookies=_admin_cookie()) as ws:
        _join(ws, display_name="Coord", role="room_coordinator", language="French")
        ws.send_text(json.dumps({"type": "booth:chat", "body": "coord note"}))
        assert json.loads(ws.receive_text())["type"] == "booth:chat"
