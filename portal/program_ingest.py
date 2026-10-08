"""Program floor ownership, native MediaMTX authorization, and reconciliation.

Single portal process, like BoothRegistry. Media never traverses this module.
Credentials are 256-bit random secrets; only a deliberately expensive digest is persisted.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import re
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from portal.booth_identity import make_booth_id, make_mediamtx_path
from portal.config import settings
from portal.database import get_session
from portal.globals import get_http_client
from portal.models import Event, Room
from portal.transcription.process import audio_progress
from portal.transcription.providers.base import ProviderConfig, ProviderEnum, get_api_key
from portal.transcription.worker import start_transcription_worker, stop_transcription_worker
from portal.websockets.manager import broadcast_transcription

logger = logging.getLogger(__name__)
ownership_lock = asyncio.Lock()
FLOOR_PATH = re.compile(r"([a-z0-9]+(?:-[a-z0-9]+)*)/([1-9][0-9]*)/floor")


class MediaAuth(BaseModel):
    action: str
    path: str = Field(default="", max_length=500)
    protocol: str = ""
    id: str = ""
    ip: str = ""
    token: str = Field(default="", max_length=512, repr=False)
    password: str = Field(default="", max_length=512, repr=False)
    query: str = Field(default="", max_length=4096, repr=False)


class MediaSource(BaseModel):
    type: str
    id: str


class MediaPath(BaseModel):
    name: str
    available: bool = False
    source: MediaSource | None = None
    tracks: list[str] = Field(default_factory=list)
    inbound_bytes: int = Field(default=0, validation_alias="inboundBytes")

    @model_validator(mode="before")
    @classmethod
    def normalize_media_path(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "available" not in normalized:
            normalized["available"] = normalized.get("ready", False)
        if not normalized.get("tracks") and normalized.get("tracks2"):
            normalized["tracks"] = [track.get("codec", "") for track in normalized["tracks2"] if isinstance(track, dict)]
        if "inboundBytes" not in normalized and "bytesReceived" in normalized:
            normalized["inboundBytes"] = normalized["bytesReceived"]
        return normalized

    @property
    def ready(self) -> bool:
        return self.available

    @property
    def bytesReceived(self) -> int:
        return self.inbound_bytes


@dataclass
class IngestHealth:
    state: str = "waiting"
    reason: str = "Waiting for an authenticated encoder."
    codecs: list[str] = field(default_factory=list)
    last_bytes: int = -1
    last_progress: float = field(default_factory=time.monotonic)
    missing_since: float | None = None
    worker_config: tuple | None = None
    worker_started_at: float | None = None


health: dict[int, IngestHealth] = {}
failures: OrderedDict[str, tuple[float, int]] = OrderedDict()
PROGRAM_SECRET_KDF_ROUNDS = 120_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def digest_program_secret(secret: str) -> str:
    """Derive the stored token digest with password-storage-grade work factor."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        settings.effective_jwt_secret.encode("utf-8"),
        PROGRAM_SECRET_KDF_ROUNDS,
    ).hex()


def key_valid(room: Room, secret: str) -> bool:
    digest = digest_program_secret(secret)
    return bool(
        room.floor_source == "program_ingest"
        and room.program_key_hash
        and secrets.compare_digest(room.program_key_hash, digest)
        and room.program_key_expires_at
        and aware(room.program_key_expires_at) > utc_now()
    )


def deny(ip: str) -> None:
    now = time.monotonic()
    start, count = failures.get(ip, (now, 0))
    if now - start >= 60:
        start, count = now, 0
    failures[ip] = (start, count + 1)
    failures.move_to_end(ip)
    while len(failures) > 2048:
        failures.popitem(last=False)
    raise HTTPException(401, "Publish authorization failed")


async def authorize_publish(data: MediaAuth) -> None:
    """Only called by MediaMTX on the private network. Never log request data."""
    if data.action != "publish":
        raise HTTPException(403, "Unsupported action")
    # Preserve legacy interpreter publishing. Floor-like spellings fail closed
    # instead of falling through to legacy authorization.
    trimmed_path = data.path.rstrip("/")
    final_component = trimmed_path.rsplit("/", 1)[-1].casefold()
    if final_component == "floor":
        if data.path.endswith("/") or not data.path.endswith("/floor"):
            raise HTTPException(403, "Canonical floor path required")
    else:
        return
    start, count = failures.get(data.ip, (0, 0))
    if count >= 10 and time.monotonic() - start < 60:
        raise HTTPException(429, "Publish authorization failed")
    match = FLOOR_PATH.fullmatch(data.path)
    if not match:
        deny(data.ip)
    slug, room_id = match.groups()
    async with ownership_lock, get_session() as session:
        row = (
            await session.execute(
                select(Room, Event)
                .join(Event)
                .where(
                    Room.id == int(room_id),
                    Event.slug == slug,
                )
            )
        ).first()
        if row is None:
            deny(data.ip)
        room, _event = row
        if room.floor_source == "jitsi_bot":
            # RTSP is not publicly exposed. WHIP must never impersonate the bot.
            try:
                private = ipaddress.ip_address(data.ip).is_private
            except ValueError:
                private = False
            if data.protocol == "rtsp" and private:
                return
            deny(data.ip)
        secret = data.token or data.password
        if (
            not settings.program_ingest_enabled
            or data.protocol != "webrtc"
            or data.query
            or not key_valid(room, secret)
        ):
            deny(data.ip)
        try:
            session_id = str(UUID(data.id))
        except ValueError:
            deny(data.ip)
        # A DB reservation can outlive a MediaMTX session across a process restart.
        # Clear it immediately when the path confirms that no source remains;
        # an active MediaMTX source retains the existing conflict response.
        reservation = health.get(room.id)
        reservation_recent = bool(
            reservation and reservation.missing_since and time.monotonic() - reservation.missing_since < 5.0
        )
        if room.program_session_id and room.program_session_id != session_id and not reservation_recent:
            live_path = await media_path(make_mediamtx_path(_event.slug, room.id, "floor"))
            if live_path is None or live_path.source is None:
                room.program_session_id = None
                health.pop(room.id, None)
        # Authorization reserves capacity before ICE negotiation completes.
        if room.program_session_id and room.program_session_id != session_id:
            raise HTTPException(409, "A floor publisher is already connected or connecting")
        count = await session.scalar(
            select(func.count())
            .select_from(Room)
            .where(
                Room.program_session_id.is_not(None),
                Room.floor_source == "program_ingest",
            )
        )
        if not room.program_session_id and count >= settings.program_ingest_max_rooms:
            raise HTTPException(503, "Program ingest capacity reached")
        room.program_session_id = session_id
        current = health.setdefault(room.id, IngestHealth())
        if current.missing_since is None:
            current.missing_since = time.monotonic()


async def media_path(path: str) -> MediaPath | None:
    response = await get_http_client().get(f"{settings.mediamtx_api_base}/v3/paths/get/{path}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return MediaPath.model_validate(response.json())


async def kick(source: MediaSource | None) -> None:
    if source is None:
        return
    endpoint = {"webRTCSession": "webrtcsessions", "rtspSession": "rtspsessions"}.get(source.type)
    if endpoint is None:
        raise HTTPException(409, "Unsupported existing floor publisher; stop it before switching source")
    session_id = str(UUID(source.id))
    response = await get_http_client().post(f"{settings.mediamtx_api_base}/v3/{endpoint}/kick/{session_id}")
    if response.status_code != 404:
        response.raise_for_status()


async def configure_source(room: Room, event: Event, action: str, offset_ms: int) -> str | None:
    """Caller holds ownership_lock and DB transaction; return a new secret only once."""
    path = make_mediamtx_path(event.slug, room.id, "floor")
    client = get_http_client()
    # Media-level duplicate protection also applies to named paths created by legacy helpers.
    response = await client.patch(
        f"{settings.mediamtx_api_base}/v3/config/paths/patch/{path}",
        json={"overridePublisher": False, "alwaysAvailable": False},
    )
    if response.status_code == 404:
        response = await client.post(
            f"{settings.mediamtx_api_base}/v3/config/paths/add/{path}",
            json={"overridePublisher": False, "alwaysAvailable": False},
        )
    response.raise_for_status()
    if room.floor_source == "jitsi_bot" and action == "enable":
        response = await client.post(
            f"{settings.floor_bot_base}/stop", json={"event_slug": event.slug, "room_id": room.id}
        )
        response.raise_for_status()
    current_path = await media_path(path)
    had_connection = bool(room.program_session_id or (current_path and current_path.source))
    await kick(current_path.source if current_path else None)
    # Also kill a reserved session that has not negotiated audio yet.
    if room.program_session_id:
        await kick(MediaSource(type="webRTCSession", id=room.program_session_id))
    await stop_transcription_worker(make_booth_id(event.slug, room.id, "floor"))
    room.program_session_id = None
    if had_connection:
        room.program_disconnected_at = utc_now()
    room.program_sync_offset_ms = offset_ms
    room.program_key_hash = None
    room.program_key_expires_at = None
    room.floor_source = "jitsi_bot" if action == "disable" else "program_ingest"
    health.pop(room.id, None)
    secret = None
    if action in {"enable", "rotate"}:
        secret = secrets.token_urlsafe(32)
        room.program_key_hash = digest_program_secret(secret)
        room.program_key_expires_at = utc_now() + timedelta(days=30)
    logger.info("program_ingest action=%s room_id=%s", action, room.id)
    return secret


async def reconcile_room(room: Room, event: Event) -> None:
    current = health.setdefault(room.id, IngestHealth())
    path = await media_path(make_mediamtx_path(event.slug, room.id, "floor"))
    booth_id = make_booth_id(event.slug, room.id, "floor")
    now = time.monotonic()
    permitted = bool(
        settings.program_ingest_enabled
        and room.program_key_hash
        and room.program_key_expires_at
        and aware(room.program_key_expires_at) > utc_now()
    )
    if path and path.source and (not permitted or path.source.id != room.program_session_id):
        await kick(path.source)
        path = None
    if not path or not path.ready or not path.source:
        current.missing_since = current.missing_since if current.missing_since is not None else now
        current.state = "disconnected" if room.program_connected_at else "waiting"
        current.reason = (
            "No publisher. Reconnect the encoder."
            if permitted
            else "Credential revoked or expired; rotate it to publish."
        )
        if now - current.missing_since >= settings.program_ingest_disconnect_grace_secs:
            await stop_transcription_worker(booth_id)
            current.worker_config = None
            if room.program_session_id:
                await kick(MediaSource(type="webRTCSession", id=room.program_session_id))
                room.program_session_id = None
                room.program_disconnected_at = utc_now()
        return
    if current.missing_since is not None or current.last_bytes == -1:
        room.program_connected_at = utc_now()
        current.last_progress = now
    current.missing_since = None
    current.codecs = path.tracks
    if path.bytesReceived != current.last_bytes:
        current.last_bytes = path.bytesReceived
        current.last_progress = now
    problem = None
    if not any(codec in {"Opus", "G711", "G722", "LPCM"} for codec in path.tracks):
        problem = "No supported audio track. Configure the WHIP encoder to send Opus audio."
    elif now - current.last_progress >= settings.program_ingest_stall_secs:
        problem = "Media has stalled. Check the encoder and network."
    elif not room.floor_transcription_enabled or room.floor_transcription_provider == "none":
        problem = "Floor transcription is disabled. Enable it in the room AI settings."
    elif not room.floor_language_code:
        problem = "Select the floor source language in the room AI settings."
    if problem:
        current.state, current.reason = "degraded", problem
        await stop_transcription_worker(booth_id)
        current.worker_config = None
        return
    current.state, current.reason = "receiving", "Audio received; starting transcription."
    provider = ProviderEnum(room.floor_transcription_provider)
    api_key = get_api_key(event, provider)
    if provider != ProviderEnum.LOCAL and (not event.transcription_api_enabled or not api_key):
        current.state, current.reason = "degraded", "Enable the event transcription API and configure its provider key."
        await stop_transcription_worker(booth_id)
        current.worker_config = None
        return
    config = (room.floor_transcription_provider, room.floor_transcription_model, room.floor_language_code)
    if current.worker_config and current.worker_config != config:
        await stop_transcription_worker(booth_id)
    await start_transcription_worker(
        event_slug=event.slug,
        language_code="floor",
        booth_id=booth_id,
        broadcast_callback=broadcast_transcription,
        provider=room.floor_transcription_provider,
        model_size=room.floor_transcription_model,
        config=ProviderConfig(api_key=api_key),
        transcription_language=room.floor_language_code,
        room_id=room.id,
    )
    current.worker_config = config
    if current.worker_started_at is None:
        current.worker_started_at = now
    last_audio = audio_progress.get(booth_id)
    if now - (last_audio or current.worker_started_at) > settings.program_ingest_stall_secs:
        current.state, current.reason = "degraded", "Audio decoder stalled or failed; restarting the processing worker."
        await stop_transcription_worker(booth_id)
        current.worker_started_at = None
        current.worker_config = None
    elif last_audio:
        current.state, current.reason = "processing", "Decoded audio received; transcription worker active."


async def reconcile_once() -> None:
    async with get_session() as session:
        ids = list(await session.scalars(select(Room.id).where(Room.floor_source == "program_ingest")))
    for room_id in ids:
        try:
            async with ownership_lock, get_session() as session:
                row = (await session.execute(select(Room, Event).join(Event).where(Room.id == room_id))).first()
                if row and row[0].floor_source == "program_ingest":
                    await reconcile_room(*row)
        except (httpx.HTTPError, ValueError, SQLAlchemyError):
            current = health.setdefault(room_id, IngestHealth())
            current.state, current.reason = (
                "degraded",
                "Media control or processing unavailable; retrying automatically.",
            )
            # Do not log exception bodies: upstream errors may contain credentials.
            logger.warning("program_ingest reconcile_failed room_id=%s", room_id)
    for room_id in set(health) - set(ids):
        health.pop(room_id, None)


async def reconcile_loop() -> None:
    while True:
        try:
            await reconcile_once()
        except SQLAlchemyError:
            logger.warning("program_ingest database_unavailable")
        await asyncio.sleep(2)
