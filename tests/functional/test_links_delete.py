from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_delete_link_returns_204(auth_client):
    """Успешное удаление ссылки возвращает 204."""
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://to-delete.com"},
    )
    short_code = resp.json()["short_code"]

    del_resp = await auth_client.delete(f"/links/{short_code}")
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_link_then_redirect_returns_410(anon_client, auth_client):
    """После удаления ссылка недоступна для редиректа — 410."""
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://to-delete-410.com"},
    )
    short_code = resp.json()["short_code"]

    await auth_client.delete(f"/links/{short_code}")

    # Переход по удалённой ссылке должен вернуть 410
    resp = await anon_client.get(f"/links/{short_code}", follow_redirects=False)
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_delete_link_requires_auth(auth_client):
    """DELETE без токена возвращает 401."""
    # Создаём ссылку с auth_client, затем убираем токен для проверки 401
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://needs-auth-del.com"},
    )
    short_code = resp.json()["short_code"]

    # Временно убираем токен — клиент становится анонимным
    token = auth_client.headers.pop("Authorization")
    resp = await auth_client.delete(f"/links/{short_code}")
    auth_client.headers["Authorization"] = token
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_link_wrong_owner_returns_403(anon_client, created_link):
    """Другой пользователь не может удалить чужую ссылку — 403."""
    other_email = "other_delete@example.com"
    await anon_client.post(
        "/auth/register",
        json={"email": other_email, "password": "Str0ngPass!"},
    )
    resp = await anon_client.post(
        "/auth/jwt/login",
        data={"username": other_email, "password": "Str0ngPass!"},
    )
    other_token = resp.json()["access_token"]

    resp = await anon_client.delete(
        f"/links/{created_link['short_code']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_link_not_found_returns_404(auth_client):
    """DELETE несуществующего кода возвращает 404."""
    resp = await auth_client.delete("/links/nonexistent-del")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cleanup_requires_auth(anon_client):
    """DELETE /cleanup без токена возвращает 401."""
    resp = await anon_client.delete("/links/cleanup")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_cleanup_returns_count_and_days(auth_client):
    """DELETE /cleanup возвращает структуру CleanupResponse."""
    resp = await auth_client.delete("/links/cleanup?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert "deleted_count" in body
    assert "days" in body
    assert body["days"] == 30


@pytest.mark.asyncio
async def test_cleanup_archives_old_unused_links(auth_client):
    """Cleanup архивирует ссылки, не использованные дольше порога."""
    # Создаём ссылку
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://old-unused.com"},
    )
    short_code = resp.json()["short_code"]

    # Сдвигаем "сейчас" на 60 дней вперёд — ссылка станет "устаревшей"
    future = datetime.now(timezone.utc) + timedelta(days=60)
    with patch("links.service._now_utc", return_value=future):
        resp = await auth_client.delete("/links/cleanup?days=30")

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] >= 1
