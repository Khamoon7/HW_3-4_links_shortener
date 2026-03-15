import pytest


@pytest.mark.asyncio
async def test_qr_returns_png_for_active_link(anon_client, created_link):
    """GET /{short_code}/qr возвращает 200 и PNG-изображение."""
    short_code = created_link["short_code"]
    resp = await anon_client.get(f"/links/{short_code}/qr")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    # PNG начинается с сигнатуры \x89PNG
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_qr_is_public(anon_client, created_link):
    """GET /qr доступен без авторизации."""
    short_code = created_link["short_code"]
    resp = await anon_client.get(f"/links/{short_code}/qr")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_qr_nonexistent_code_returns_404(anon_client):
    """GET /qr для несуществующего кода возвращает 404."""
    resp = await anon_client.get("/links/doesnotexist99/qr")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_qr_deleted_link_returns_410(anon_client, auth_client):
    """GET /qr для удалённой ссылки возвращает 410."""
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://qr-delete-test.com"},
    )
    short_code = resp.json()["short_code"]

    # Удаляем ссылку
    await auth_client.delete(f"/links/{short_code}")

    # QR на удалённую ссылку
    resp = await anon_client.get(f"/links/{short_code}/qr")
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_qr_content_disposition_header(anon_client, created_link):
    """Ответ содержит заголовок Content-Disposition с именем файла."""
    short_code = created_link["short_code"]
    resp = await anon_client.get(f"/links/{short_code}/qr")
    assert resp.status_code == 200
    assert "content-disposition" in resp.headers
    assert short_code in resp.headers["content-disposition"]
