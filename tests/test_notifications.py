"""Tests for the durable, configurable transactional email outbox."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from portal.database import configure, create_auth_token, create_user, dispose, get_session, init_db, revoke_auth_token
from portal.models import EmailDelivery, EmailTemplateRevision
from portal.notifications import process_due_deliveries, publish_draft, queue_notification, save_draft


@pytest.fixture(autouse=True)
async def setup_db():
    configure("sqlite+aiosqlite://")
    await init_db()
    yield
    await dispose()


@pytest.mark.anyio
async def test_notification_is_encrypted_and_retained_when_smtp_is_unconfigured(monkeypatch):
    monkeypatch.setattr("portal.notifications.settings.smtp_host", "")
    async with get_session() as session:
        delivery = await queue_notification(
            session,
            "verification",
            "person@example.com",
            {"verification_link": "https://example.invalid/auth/verify/secret"},
            idempotency_key="verification:test",
        )
        delivery_id = delivery.id

    assert await process_due_deliveries() == 1

    async with get_session() as session:
        stored = await session.get(EmailDelivery, delivery_id)
    assert stored is not None
    assert stored.status == "disabled"
    assert "secret" not in stored.encrypted_html


@pytest.mark.anyio
async def test_delivery_is_suppressed_when_its_link_token_is_revoked(monkeypatch):
    monkeypatch.setattr("portal.notifications.settings.smtp_host", "smtp.example.invalid")
    async with get_session() as session:
        user = await create_user(session, email="person@example.com", display_name="Person")
        token = await create_auth_token(session, user_id=user.id, token_type="verification", jti="revoked-link-token")
        delivery = await queue_notification(
            session,
            "verification",
            user.email,
            {"verification_link": "https://example.invalid/auth/verify/revoked-link-token"},
            auth_token_id=token.id,
        )
        await revoke_auth_token(session, jti=token.jti)
        delivery_id = delivery.id

    assert await process_due_deliveries() == 1

    async with get_session() as session:
        stored = await session.get(EmailDelivery, delivery_id)
    assert stored is not None
    assert stored.status == "suppressed"


@pytest.mark.anyio
async def test_templates_reject_unknown_variables_and_publish_an_audited_revision():
    async with get_session() as session:
        editor = await create_user(session, email="editor@example.com", display_name="Editor")
        editor_id = editor.id
    async with get_session() as session:
        with pytest.raises(ValueError, match="unsupported placeholders"):
            await save_draft(session, "verification", "Hello {{ unsupported }}", "<p>Hi</p>", editor_id=editor_id)

    async with get_session() as session:
        await save_draft(
            session,
            "verification",
            "Confirm your account",
            "<p><a href=\"{{ verification_link }}\">Confirm</a></p>",
            editor_id=editor_id,
        )
        assert await publish_draft(session, "verification", editor_id=editor_id) == 1

    async with get_session() as session:
        revisions = list((await session.scalars(select(EmailTemplateRevision))).all())
    assert len(revisions) == 1
    assert revisions[0].version == 1
