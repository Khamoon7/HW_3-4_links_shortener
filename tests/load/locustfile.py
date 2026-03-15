import random
import string

from locust import HttpUser, between, task


def _random_suffix(n: int = 8) -> str:
    """Генерирует случайный суффикс из строчных букв."""
    return "".join(random.choices(string.ascii_lowercase, k=n))


class AnonymousUser(HttpUser):
    """Анонимный пользователь: создаёт ссылки и переходит по ним.

    Симулирует основную публичную нагрузку:
    - создание ссылок (task weight 3)
    - переходы по ссылкам (task weight 5) - самая частая операция
    - просмотр статистики (task weight 2) - тест кэширования
    - поиск и топ (task weight 1 каждый)
    """

    wait_time = between(0.5, 2)
    host = "http://localhost:8000"

    # Список созданных кодов для переходов и статистики
    created_codes: list[str] = []

    @task(3)
    def shorten_link(self):
        """Создание короткой ссылки - массовая нагрузка на запись."""
        url = f"https://example.com/load-test/{_random_suffix()}"
        with self.client.post(
            "/links/shorten",
            json={"original_url": url},
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                code = resp.json().get("short_code")
                if code:
                    self.created_codes.append(code)
                resp.success()
            else:
                resp.failure(f"Shorten failed: {resp.status_code}")

    @task(5)
    def follow_redirect(self):
        """Переходы по ссылкам - самая частая операция в production."""
        if not self.created_codes:
            return
        code = random.choice(self.created_codes)
        # allow_redirects=False: не следуем за редиректом, только замеряем API
        self.client.get(
            f"/links/{code}",
            allow_redirects=False,
            name="/links/[code]",
        )

    @task(2)
    def view_stats(self):
        """Просмотр статистики - тест влияния кэширования (30 сек TTL).

        Первый запрос - cache miss (обращение к БД).
        Последующие в течение 30 секунд - cache hit (Redis/InMemory).
        Сравните response time в Locust UI для оценки выигрыша от кэша.
        """
        if not self.created_codes:
            return
        code = random.choice(self.created_codes)
        self.client.get(f"/links/{code}/stats", name="/links/[code]/stats")

    @task(1)
    def search_links(self):
        """Поиск ссылок - кэшируемый endpoint (30 сек TTL)."""
        self.client.get(
            "/links/search?original_url=load-test",
            name="/links/search",
        )

    @task(1)
    def top_links(self):
        """Топ ссылок - кэшируемый endpoint (60 сек TTL)."""
        self.client.get("/links/top", name="/links/top")


class AuthenticatedUser(HttpUser):
    """Аутентифицированный пользователь: CRUD и управление ссылками.

    Каждый экземпляр регистрируется и логинится отдельно.
    Симулирует активных пользователей, управляющих своими ссылками.
    """

    wait_time = between(1, 3)
    host = "http://localhost:8000"

    token: str | None = None
    my_codes: list[str]

    def on_start(self):
        """Регистрируется и логинится при старте виртуального пользователя."""
        self.my_codes = []
        email = f"loadtest_{_random_suffix(6)}@test.com"
        password = "LoadTest1!"

        # Регистрация
        self.client.post(
            "/auth/register",
            json={"email": email, "password": password},
            name="/auth/register",
        )

        # Вход
        resp = self.client.post(
            "/auth/jwt/login",
            data={"username": email, "password": password},
            name="/auth/jwt/login",
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    def _headers(self) -> dict:
        """Возвращает заголовок авторизации."""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(4)
    def create_link(self):
        """Создание ссылок - основная задача аутентифицированного пользователя."""
        url = f"https://auth-load.com/{_random_suffix()}"
        with self.client.post(
            "/links/shorten",
            json={"original_url": url},
            headers=self._headers(),
            catch_response=True,
            name="/links/shorten (auth)",
        ) as resp:
            if resp.status_code == 201:
                code = resp.json().get("short_code")
                if code:
                    self.my_codes.append(code)
                resp.success()
            else:
                resp.failure(f"Create failed: {resp.status_code}")

    @task(2)
    def list_my_links(self):
        """Список своих ссылок - регулярный опрос."""
        self.client.get(
            "/links/",
            headers=self._headers(),
            name="/links/ (my)",
        )

    @task(1)
    def update_link(self):
        """Обновление ссылки - редкая операция."""
        if not self.my_codes:
            return
        code = random.choice(self.my_codes)
        new_url = f"https://updated-{_random_suffix()}.com"
        self.client.put(
            f"/links/{code}",
            json={"original_url": new_url},
            headers=self._headers(),
            name="/links/[code] PUT",
        )

    @task(1)
    def delete_link(self):
        """Удаление ссылки - редкая очистка."""
        if not self.my_codes:
            return
        # Удаляем последнюю созданную (pop)
        code = self.my_codes.pop()
        self.client.delete(
            f"/links/{code}",
            headers=self._headers(),
            name="/links/[code] DELETE",
        )
