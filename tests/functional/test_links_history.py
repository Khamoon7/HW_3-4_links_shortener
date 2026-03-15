import pytest


@pytest.mark.asyncio
async def test_history_is_public(anon_client):
    """GET /history/expired доступен без авторизации — 200."""
    resp = await anon_client.get("/links/history/expired")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_history_contains_deleted_link(anon_client, auth_client):
    """После удаления ссылка появляется в истории с reason='deleted'."""
    # Создаём и удаляем ссылку
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://history-test-deleted.com"},
    )
    short_code = resp.json()["short_code"]
    await auth_client.delete(f"/links/{short_code}")

    # Проверяем историю
    history = (await anon_client.get("/links/history/expired")).json()
    reasons = [entry["reason"] for entry in history]
    codes = [entry["short_code"] for entry in history]

    assert short_code in codes
    assert "deleted" in reasons


@pytest.mark.asyncio
async def test_history_record_has_required_fields(anon_client, auth_client):
    """Запись истории содержит все обязательные поля."""
    resp = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://history-fields-test.com"},
    )
    short_code = resp.json()["short_code"]
    await auth_client.delete(f"/links/{short_code}")

    history = (await anon_client.get("/links/history/expired")).json()
    # Находим нашу запись
    record = next((r for r in history if r["short_code"] == short_code), None)
    assert record is not None
    assert "short_code" in record
    assert "original_url" in record
    assert "created_at" in record
    assert "deactivated_at" in record
    assert "reason" in record
    assert "click_count" in record


@pytest.mark.asyncio
async def test_history_pagination(anon_client):
    """GET /history/expired с limit=1 возвращает не более 1 записи."""
    resp = await anon_client.get("/links/history/expired?skip=0&limit=1")
    assert resp.status_code == 200
    assert len(resp.json()) <= 1


@pytest.mark.asyncio
async def test_history_sorted_by_deactivated_at_desc(anon_client, auth_client):
    """История сортируется по deactivated_at убыванию (новые первые)."""
    # Создаём и удаляем две ссылки последовательно
    r1 = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://first-deleted.com"},
    )
    await auth_client.delete(f"/links/{r1.json()['short_code']}")

    r2 = await auth_client.post(
        "/links/shorten",
        json={"original_url": "https://second-deleted.com"},
    )
    await auth_client.delete(f"/links/{r2.json()['short_code']}")

    history = (await anon_client.get("/links/history/expired")).json()
    if len(history) >= 2:
        # Первый элемент должен быть удалён позже второго (убывающий порядок)
        dt1 = history[0]["deactivated_at"]
        dt2 = history[1]["deactivated_at"]
        assert dt1 >= dt2
