import pytest


@pytest.mark.asyncio
async def test_project_stats_requires_auth(anon_client):
    """GET /projects/{project}/stats без токена возвращает 401."""
    resp = await anon_client.get("/links/projects/myproject/stats")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_project_stats_not_found_returns_404(auth_client):
    """GET /projects/{project}/stats для несуществующего проекта — 404."""
    resp = await auth_client.get("/links/projects/nonexistent-proj-xyz/stats")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_project_stats_returns_correct_aggregates(auth_client, anon_client):
    """GET /projects/{project}/stats возвращает правильные агрегаты."""
    proj = "stats-test-project"

    # Создаём 3 ссылки в проекте
    codes = []
    for i in range(3):
        resp = await auth_client.post(
            "/links/shorten",
            json={"original_url": f"https://stats-proj-{i}.com", "project": proj},
        )
        codes.append(resp.json()["short_code"])

    # Делаем переходы: 3 по первой, 1 по второй, 0 по третьей
    for _ in range(3):
        await anon_client.get(f"/links/{codes[0]}", follow_redirects=False)
    await anon_client.get(f"/links/{codes[1]}", follow_redirects=False)

    resp = await auth_client.get(f"/links/projects/{proj}/stats")
    assert resp.status_code == 200
    body = resp.json()

    assert body["project"] == proj
    assert body["total_links"] == 3
    assert body["total_clicks"] == 4  # 3 + 1 + 0
    assert body["top_link"] == codes[0]  # самая кликнутая
    assert body["top_link_clicks"] == 3


@pytest.mark.asyncio
async def test_project_stats_response_schema(auth_client):
    """Ответ содержит все обязательные поля схемы ProjectStats."""
    proj = "schema-check-project"
    await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://schema-proj.com", "project": proj},
    )

    resp = await auth_client.get(f"/links/projects/{proj}/stats")
    assert resp.status_code == 200
    body = resp.json()

    for field in ("project", "total_links", "total_clicks", "avg_clicks", "top_link", "top_link_clicks"):
        assert field in body, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_project_stats_isolation_between_users(anon_client, auth_client):
    """Пользователь видит только собственные проекты, не чужие."""
    # auth_client создаёт ссылку в проекте
    await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://my-project-url.com", "project": "my-private-proj"},
    )

    # Второй пользователь не видит этот проект
    other_email = "other_proj@example.com"
    await anon_client.post(
        "/auth/register",
        json={"email": other_email, "password": "Str0ngPass!"},
    )
    resp = await anon_client.post(
        "/auth/jwt/login",
        data={"username": other_email, "password": "Str0ngPass!"},
    )
    other_token = resp.json()["access_token"]

    resp = await anon_client.get(
        "/links/projects/my-private-proj/stats",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404
