from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_redirect_returns_307(anon_client, created_link):
    """Переход по короткой ссылке возвращает 307 с Location."""
    short_code = created_link["short_code"]
    resp = await anon_client.get(f"/links/{short_code}", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://example.com/fixture-link"


@pytest.mark.asyncio
async def test_redirect_nonexistent_returns_404(anon_client):
    """Переход по несуществующему коду возвращает 404."""
    resp = await anon_client.get("/links/definitely-missing", follow_redirects=False)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_redirect_increments_click_count(anon_client, auth_client):
    """Каждый переход увеличивает click_count."""
    # Создаём ссылку
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://clickcount.com"},
    )
    short_code = resp.json()["short_code"]

    # Делаем 3 перехода
    for _ in range(3):
        await anon_client.get(f"/links/{short_code}", follow_redirects=False)

    # Проверяем счётчик через stats
    stats = (await anon_client.get(f"/links/{short_code}/stats")).json()
    assert stats["click_count"] == 3


@pytest.mark.asyncio
async def test_redirect_expired_link_returns_410(anon_client, auth_client):
    """Истёкшая ссылка при переходе возвращает 410."""
    resp = await auth_client.post(
        "/links/shorten",
        json={
            "original_url": "https://will-expire.com",
            "expires_at": "2099-12-31T23:59:00+00:00",
        },
    )
    short_code = resp.json()["short_code"]

    # Патчим _now_utc чтобы симулировать, что время ушло вперёд
    future = datetime(2100, 1, 1, tzinfo=timezone.utc)
    with patch("links.service._now_utc", return_value=future):
        resp = await anon_client.get(f"/links/{short_code}", follow_redirects=False)
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_stats_returns_200(anon_client, created_link):
    """GET /{short_code}/stats возвращает 200 и поля статистики."""
    short_code = created_link["short_code"]
    resp = await anon_client.get(f"/links/{short_code}/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "click_count" in body
    assert "short_code" in body
    assert body["short_code"] == short_code


@pytest.mark.asyncio
async def test_stats_does_not_increment_click_count(anon_client, auth_client):
    """GET /stats не инкрементирует click_count (в отличие от redirect)."""
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://statsonly.com"},
    )
    short_code = resp.json()["short_code"]

    # Запрашиваем статистику 5 раз
    for _ in range(5):
        await anon_client.get(f"/links/{short_code}/stats")

    stats = (await anon_client.get(f"/links/{short_code}/stats")).json()
    assert stats["click_count"] == 0


@pytest.mark.asyncio
async def test_stats_nonexistent_returns_404(anon_client):
    """GET /stats несуществующего кода возвращает 404."""
    resp = await anon_client.get("/links/nonexistentcode/stats")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_finds_matching_links(anon_client, auth_client):
    """GET /search находит ссылки по подстроке URL."""
    await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://unique-search-target-xyz.com/page"},
    )
    resp = await anon_client.get("/links/search?original_url=unique-search-target-xyz")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert any("unique-search-target-xyz" in r["original_url"] for r in results)


@pytest.mark.asyncio
async def test_search_no_results_returns_empty_list(anon_client):
    """GET /search без совпадений возвращает пустой список."""
    resp = await anon_client.get("/links/search?original_url=absolutely-no-match-qwerty123")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_top_links_returns_list(anon_client):
    """GET /top возвращает список ссылок (может быть пустым)."""
    resp = await anon_client.get("/links/top")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_top_links_ordered_by_click_count(anon_client, auth_client):
    """GET /top возвращает ссылки в порядке убывания click_count."""
    # Создаём 2 ссылки
    r1 = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://top-high-clicks.com"},
    )
    r2 = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://top-low-clicks.com"},
    )
    code_high = r1.json()["short_code"]
    code_low = r2.json()["short_code"]

    # Делаем 5 переходов по первой и 1 по второй
    for _ in range(5):
        await anon_client.get(f"/links/{code_high}", follow_redirects=False)
    await anon_client.get(f"/links/{code_low}", follow_redirects=False)

    top = (await anon_client.get("/links/top")).json()
    codes = [link["short_code"] for link in top]

    # high должна быть выше low в рейтинге
    assert codes.index(code_high) < codes.index(code_low)


@pytest.mark.asyncio
async def test_my_links_requires_auth(anon_client):
    """GET /links/ без токена возвращает 401."""
    resp = await anon_client.get("/links/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_my_links_returns_own_links(auth_client, created_link):
    """GET /links/ возвращает ссылки текущего пользователя."""
    resp = await auth_client.get("/links/")
    assert resp.status_code == 200
    codes = [link["short_code"] for link in resp.json()]
    assert created_link["short_code"] in codes


@pytest.mark.asyncio
async def test_my_links_filter_by_project(auth_client):
    """GET /links/?project=... возвращает только ссылки нужного проекта."""
    project_name = "filter-proj-unique"
    await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://proj-filter.com", "project": project_name},
    )
    await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://other-proj.com", "project": "other-proj"},
    )

    resp = await auth_client.get(f"/links/?project={project_name}")
    assert resp.status_code == 200
    links = resp.json()
    assert len(links) >= 1
    assert all(link["project"] == project_name for link in links)


@pytest.mark.asyncio
async def test_my_links_pagination(auth_client):
    """GET /links/ с параметрами skip и limit работает корректно."""
    # Создаём несколько ссылок
    for i in range(3):
        await auth_client.post(
            "/links/shorten",
            json={"original_url": f"https://pagination-test-{i}.com"},
        )

    resp = await auth_client.get("/links/?skip=0&limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) <= 2
