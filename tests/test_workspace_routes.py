"""Regression tests for organizer workspace routing."""

from __future__ import annotations

import os

import pytest

from portal.auth import create_admin_token, create_user_token

os.environ["BOOTH_ACCESS_TOKEN"] = ""
os.environ["ADMIN_PASSWORD"] = "test-admin-pass"


@pytest.fixture(autouse=True)
async def setup_db():
    from portal.database import configure, dispose, init_db

    configure("sqlite+aiosqlite://")
    await init_db()
    yield
    await dispose()


def client():
    from httpx import ASGITransport, AsyncClient

    from fastapi_app import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def organizer():
    from portal.database import create_event, create_user, get_session, set_event_membership

    async with get_session() as session:
        event = await create_event(session, slug="shared-event", display_name="Shared Event")
        user = await create_user(session, email="owner@example.com", display_name="Event Owner")
        await set_event_membership(session, user_id=user.id, event_id=event.id, role="event_owner")
        event_id = event.id
        user_id = user.id
        email = user.email

    return {
        "event_id": event_id,
        "cookies": {"user_token": create_user_token(user_id=user_id, email=email)},
    }


@pytest.mark.anyio
async def test_event_owner_manages_event_from_workspace_namespace(organizer):
    async with client() as http:
        response = await http.get(
            f"/workspace/events/{organizer['event_id']}/",
            cookies=organizer["cookies"],
        )

    assert response.status_code == 200
    assert "Shared Event" in response.text
    assert f'/workspace/events/{organizer["event_id"]}/rooms/' in response.text
    assert f'/admin/events/{organizer["event_id"]}/rooms/' not in response.text


@pytest.mark.anyio
async def test_legacy_admin_event_url_redirects_owner_and_preserves_query(organizer):
    async with client() as http:
        response = await http.get(
            f"/admin/events/{organizer['event_id']}/rooms/?search=main%20hall",
            cookies=organizer["cookies"],
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == (
        f"/workspace/events/{organizer['event_id']}/rooms/?search=main%20hall"
    )


@pytest.mark.anyio
async def test_workspace_form_submission_stays_in_workspace_namespace(organizer):
    async with client() as http:
        response = await http.post(
            f"/workspace/events/{organizer['event_id']}/rooms/",
            data={"display_name": "Main Hall"},
            cookies=organizer["cookies"],
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/workspace/events/{organizer['event_id']}/rooms/"


@pytest.mark.anyio
async def test_super_admin_retains_admin_namespace(organizer):
    async with client() as http:
        response = await http.get(
            f"/admin/events/{organizer['event_id']}/",
            cookies={"admin_token": create_admin_token()},
            follow_redirects=False,
        )

    assert response.status_code == 200
    assert f'/admin/events/{organizer["event_id"]}/rooms/' in response.text
    assert f'/workspace/events/{organizer["event_id"]}/rooms/' not in response.text


@pytest.mark.anyio
async def test_workspace_api_uses_workspace_namespace(organizer):
    async with client() as http:
        response = await http.get(
            f"/workspace/api/events/{organizer['event_id']}/api-keys",
            cookies=organizer["cookies"],
        )
        legacy = await http.get(
            f"/admin/api/events/{organizer['event_id']}/api-keys",
            cookies=organizer["cookies"],
            follow_redirects=False,
        )

    assert response.status_code == 200
    assert response.json() == []
    assert legacy.status_code == 307
    assert legacy.headers["location"] == f"/workspace/api/events/{organizer['event_id']}/api-keys"


@pytest.mark.anyio
async def test_workspace_does_not_expose_system_admin_routes(organizer):
    async with client() as http:
        response = await http.get("/workspace/users/", cookies=organizer["cookies"])

    assert response.status_code == 404


@pytest.mark.anyio
async def test_workspace_trailing_slash_redirect_stays_in_workspace(organizer):
    async with client() as http:
        response = await http.get(
            "/workspace/events",
            cookies=organizer["cookies"],
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "http://test/workspace/events/"


@pytest.mark.anyio
async def test_organizer_navigation_points_to_workspace(organizer):
    async with client() as http:
        home = await http.get("/", cookies=organizer["cookies"])
        account = await http.get("/account", cookies=organizer["cookies"])

    assert home.status_code == 200
    assert 'href="/workspace/"' in home.text
    assert account.status_code == 200
    assert 'href="/workspace/">Organizer Workspace</a>' in account.text
    assert f'href="/workspace/events/{organizer["event_id"]}/"' in account.text


@pytest.mark.anyio
async def test_unrelated_user_cannot_access_workspace_event(organizer):
    from portal.database import create_user, get_session

    async with get_session() as session:
        user = await create_user(session, email="outsider@example.com", display_name="Outsider")
        outsider_cookie = {"user_token": create_user_token(user_id=user.id, email=user.email)}

    async with client() as http:
        response = await http.get(
            f"/workspace/events/{organizer['event_id']}/",
            cookies=outsider_cookie,
        )

    assert response.status_code == 403
