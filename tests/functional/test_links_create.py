import pytest


@pytest.mark.asyncio
async def test_create_link_anonymous_returns_201(anon_client):
    """Аноним может создать ссылку без токена, получает 201."""
    resp = await anon_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/anon-test"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "short_code" in body
    assert len(body["short_code"]) == 8
    assert body["is_active"] is True
    assert body["original_url"] == "https://example.com/anon-test"


@pytest.mark.asyncio
async def test_create_link_authenticated_returns_201(auth_client):
    """Аутентифицированный пользователь создаёт ссылку — 201."""
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/auth-test"},
    )
    assert resp.status_code == 201
    assert "short_code" in resp.json()


@pytest.mark.asyncio
async def test_create_link_with_custom_alias(auth_client):
    """custom_alias используется как short_code."""
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "custom_alias": "my-custom-1"},
    )
    assert resp.status_code == 201
    assert resp.json()["short_code"] == "my-custom-1"


@pytest.mark.asyncio
async def test_create_link_duplicate_alias_returns_409(auth_client):
    """Повторное использование занятого alias возвращает 409."""
    payload = {"original_url": "https://example.com", "custom_alias": "dup-alias-1"}
    await auth_client.post("/links/shorten", json=payload)
    resp = await auth_client.post("/links/shorten", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_link_reserved_alias_returns_422(anon_client):
    """Зарезервированный alias (search, top, ...) возвращает 422."""
    for reserved in ("search", "top", "shorten", "history", "cleanup", "projects"):
        resp = await anon_client.post(
            "/links/shorten",
            json={"original_url": "https://example.com", "custom_alias": reserved},
        )
        assert resp.status_code == 422, f"Expected 422 for alias '{reserved}'"


@pytest.mark.asyncio
async def test_create_link_past_expiry_returns_422(auth_client):
    """expires_at в прошлом возвращает 422."""
    resp = await auth_client.post(
        "/links/shorten",
        json={
            "original_url": "https://example.com",
            "expires_at": "2020-01-01T00:00:00+00:00",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_link_invalid_url_returns_422(anon_client):
    """Невалидный URL возвращает 422."""
    resp = await anon_client.post(
        "/links/shorten",
        json={"original_url": "not-a-valid-url"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_link_with_project(auth_client):
    """Ссылка с project сохраняется и возвращает project в ответе."""
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://proj-test.com", "project": "test-project"},
    )
    assert resp.status_code == 201
    assert resp.json()["project"] == "test-project"


@pytest.mark.asyncio
async def test_create_link_short_url_format(auth_client):
    """short_url содержит short_code в пути /links/{code}."""
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com/url-format"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["short_code"] in body["short_url"]
    assert "/links/" in body["short_url"]


@pytest.mark.asyncio
async def test_create_link_alias_too_short_returns_422(anon_client):
    """Alias короче 3 символов возвращает 422."""
    resp = await anon_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "custom_alias": "ab"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_link_with_future_expiry(auth_client):
    """Ссылка с корректной датой истечения в будущем создаётся успешно."""
    resp = await auth_client.post(
        "/links/shorten",
        json={
            "original_url": "https://example.com/expiring",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["expires_at"] is not None
