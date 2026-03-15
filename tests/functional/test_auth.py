import pytest


@pytest.mark.asyncio
async def test_register_success(anon_client):
    """Успешная регистрация возвращает 201 и содержит поле id."""
    resp = await anon_client.post(
        "/auth/register",
        json={"email": "newuser_reg@example.com", "password": "Str0ngPass!"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["email"] == "newuser_reg@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_400(anon_client):
    """Повторная регистрация с тем же email возвращает 400."""
    payload = {"email": "dup_auth@example.com", "password": "Str0ngPass!"}
    await anon_client.post("/auth/register", json=payload)
    resp = await anon_client.post("/auth/register", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_success(anon_client):
    """Успешный вход возвращает 200 и токен access_token."""
    await anon_client.post(
        "/auth/register",
        json={"email": "logintest@example.com", "password": "Str0ngPass!"},
    )
    # fastapi-users принимает form-data на /auth/jwt/login
    resp = await anon_client.post(
        "/auth/jwt/login",
        data={"username": "logintest@example.com", "password": "Str0ngPass!"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_400(anon_client):
    """Неверный пароль при входе возвращает 400."""
    await anon_client.post(
        "/auth/register",
        json={"email": "wrongpass@example.com", "password": "Str0ngPass!"},
    )
    resp = await anon_client.post(
        "/auth/jwt/login",
        data={"username": "wrongpass@example.com", "password": "WrongPassword"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_nonexistent_user_returns_400(anon_client):
    """Вход несуществующего пользователя возвращает 400."""
    resp = await anon_client.post(
        "/auth/jwt/login",
        data={"username": "ghost@example.com", "password": "Str0ngPass!"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_root_endpoint(anon_client):
    """Корневой endpoint возвращает 200 с информацией о сервисе."""
    resp = await anon_client.get("/")
    assert resp.status_code == 200
    assert "service" in resp.json()
