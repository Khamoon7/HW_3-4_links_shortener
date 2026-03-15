import pytest


@pytest.mark.asyncio
async def test_update_link_success(auth_client, created_link):
    """Успешное обновление URL возвращает 200 с новым original_url."""
    short_code = created_link["short_code"]
    # Используем URL с путём — Pydantic нормализует HttpUrl, добавляя /
    resp = await auth_client.put(
        f"/links/{short_code}",
        json={"original_url": "https://updated-url.com/page"},
    )
    assert resp.status_code == 200
    assert "updated-url.com" in resp.json()["original_url"]


@pytest.mark.asyncio
async def test_update_link_requires_auth(auth_client):
    """PUT без токена возвращает 401."""
    # Создаём ссылку с auth_client, затем убираем токен для проверки 401
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://needs-auth-upd.com"},
    )
    short_code = resp.json()["short_code"]

    # Временно убираем токен
    token = auth_client.headers.pop("Authorization")
    resp = await auth_client.put(
        f"/links/{short_code}",
        json={"original_url": "https://hacker.com"},
    )
    auth_client.headers["Authorization"] = token
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_link_wrong_owner_returns_403(anon_client, auth_client, created_link):
    """Другой пользователь не может редактировать чужую ссылку — 403."""
    # Регистрируем второго пользователя
    other_email = "other_update@example.com"
    await anon_client.post(
        "/auth/register",
        json={"email": other_email, "password": "Str0ngPass!"},
    )
    resp = await anon_client.post(
        "/auth/jwt/login",
        data={"username": other_email, "password": "Str0ngPass!"},
    )
    other_token = resp.json()["access_token"]

    resp = await anon_client.put(
        f"/links/{created_link['short_code']}",
        json={"original_url": "https://hack.com"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_link_not_found_returns_404(auth_client):
    """PUT несуществующего кода возвращает 404."""
    resp = await auth_client.put(
        "/links/nonexistent-code",
        json={"original_url": "https://new.com"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_link_past_expiry_returns_422(auth_client, created_link):
    """expires_at в прошлом при обновлении возвращает 422."""
    resp = await auth_client.put(
        f"/links/{created_link['short_code']}",
        json={"expires_at": "2020-01-01T00:00:00+00:00"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_link_project(auth_client, created_link):
    """Обновление поля project работает корректно."""
    short_code = created_link["short_code"]
    resp = await auth_client.put(
        f"/links/{short_code}",
        json={"project": "new-project"},
    )
    assert resp.status_code == 200
    assert resp.json()["project"] == "new-project"


@pytest.mark.asyncio
async def test_update_link_future_expiry_accepted(auth_client, created_link):
    """Обновление expires_at на будущее возвращает 200."""
    short_code = created_link["short_code"]
    resp = await auth_client.put(
        f"/links/{short_code}",
        json={"expires_at": "2099-06-01T12:00:00+00:00"},
    )
    assert resp.status_code == 200
    assert resp.json()["expires_at"] is not None
