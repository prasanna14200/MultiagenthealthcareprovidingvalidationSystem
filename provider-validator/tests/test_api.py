# tests/test_api.py
import pytest
from types import SimpleNamespace
from httpx import AsyncClient, ASGITransport
from src.api.app import app
from src.auth import get_current_active_user  # THE dependency your routes use

# Fake active user returned by dependency override
async def fake_current_active_user():
    # return an object with at least .username and .role attributes
    return SimpleNamespace(username="testuser", role="admin")

# Override the dependency the app actually depends on
app.dependency_overrides[get_current_active_user] = fake_current_active_user


@pytest.mark.asyncio
async def test_get_pending_providers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/providers/pending")
        assert resp.status_code in (200, 204)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, (list, dict))


@pytest.mark.asyncio
async def test_provider_review_patch():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        body = {"edited_fields": {"phone": "999999"}, "action": "save", "notes": "test"}
        resp = await client.patch("/providers/1/review", json=body)
        assert resp.status_code in (200, 201, 204)
