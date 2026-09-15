"""HTTP-ядро SDK: заголовки, ретраи, идемпотентность, разбор ответов и ошибок.

Синхронный ``Vdsok`` и асинхронный ``AsyncVdsok`` делят всю логику через
``_BaseClient``: подготовка запроса (``_prepare``), решение о повторе
(``_retry_delay``) и превращение ответа в объект (``_handle``) — чистые
функции без ввода-вывода, а сами циклы отправки отличаются только ``await``
и способом уснуть. Так поведение двух клиентов не может разойтись.
"""

from __future__ import annotations

import asyncio
import email.utils
import json
import platform
import random
import re
import time
import uuid
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Dict, Mapping, Optional

import httpx

from ._ops import KIND_BINARY, KIND_EMPTY, KIND_LIST, KIND_PAGE, KIND_RAW, Op
from ._parsing import build, compact_body, encode_params
from ._types import BinaryResult, EmptyResult, ItemList, Page, RateLimitInfo, ResponseMeta
from ._version import __version__
from .errors import ApiError, TransportError, error_class_for

DEFAULT_BASE_URL = "https://vdsok.guru/api/v1"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
# Retry-After больше этого порога не ждём: лучше отдать 429/503 вызывающему,
# чем молча висеть минуты внутри одного вызова SDK.
DEFAULT_MAX_RETRY_AFTER = 60.0

# Статусы, после которых тот же запрос имеет смысл повторить (спека: 429 и 503
# приходят с Retry-After, 502/504 — сбой upstream, который обычно короткий).
RETRY_STATUSES = frozenset({429, 502, 503, 504})
# 409 idempotency_in_progress — первый запрос с этим ключом ещё выполняется;
# повтор через Retry-After вернёт его сохранённый результат.
RETRY_CONFLICT_CODES = frozenset({"idempotency_in_progress"})

USER_AGENT = f"vdsok-sdk-python/{__version__} python/{platform.python_version()} httpx/{httpx.__version__}"

_IDEMPOTENCY_KEY_RE = re.compile(r"^[\x21-\x7e]{16,128}$")
_CONTENT_DISPOSITION_FILENAME = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)

# Точки для monkeypatch в тестах: ретраи и опрос заказа не должны реально спать
# и ждать. Именно отдельные имена модуля, а не time.sleep/time.monotonic по
# месту вызова: подмена атрибута у самого модуля time действовала бы на весь
# процесс, включая чужой код в том же прогоне тестов.
_sleep = time.sleep
_async_sleep = asyncio.sleep
_monotonic = time.monotonic

_ssl_context: Any = None


def _default_verify() -> Any:
    """Общий SSL-контекст для клиентов, которые SDK создаёт сам.

    httpx строит контекст (и читает корневые сертификаты) на каждый
    ``httpx.Client()``; на Windows это ~0.5 с. Код вроде «клиент на запрос»
    в serverless-функциях платил бы это на каждом вызове. Контекст
    неизменяемый после создания, делить его между клиентами безопасно.
    """
    global _ssl_context
    if _ssl_context is None:
        _ssl_context = httpx.create_ssl_context()
    return _ssl_context


@dataclass
class _Prepared:
    """Запрос, готовый к отправке; один и тот же для всех попыток."""

    method: str
    url: str
    headers: Dict[str, str]
    params: Dict[str, str]
    content: Optional[bytes]
    request_id: str
    idempotency_key: Optional[str]
    retryable: bool


def parse_retry_after(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """``Retry-After`` -> секунды. Принимает и число, и HTTP-дату."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    current = now if now is not None else time.time()
    return max(0.0, when.timestamp() - current)


def validate_idempotency_key(key: str) -> str:
    if not isinstance(key, str) or not _IDEMPOTENCY_KEY_RE.match(key):
        raise ValueError("idempotency_key must be 16..128 printable ASCII characters (a UUID is fine)")
    return key


def _backoff(attempt: int) -> float:
    """Экспоненциальная пауза с джиттером, когда сервер не сказал, сколько ждать."""
    base = min(8.0, 0.5 * (2 ** attempt))
    return base * (0.75 + random.random() * 0.5)


class _BaseClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
        user_agent: Optional[str] = None,
        default_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key is required (create one in the cabinet at /my/api)")
        if "\n" in api_key or "\r" in api_key:
            raise ValueError("api_key contains a line break")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self.max_retry_after = float(max_retry_after)
        self.user_agent = user_agent or USER_AGENT
        self._extra_headers = dict(default_headers or {})

    # ------------------------------------------------------------ свойства

    @property
    def key_hint(self) -> str:
        """Префикс и последние 4 символа ключа — для логов и repr; сам ключ
        SDK никогда не печатает."""
        key = self._api_key
        prefix = key.split("_")[0] + "_" if "_" in key else ""
        return f"{prefix}…{key[-4:]}" if len(key) > 8 else "…"

    @property
    def is_test_key(self) -> bool:
        return self._api_key.startswith("vk_test_")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(key={self.key_hint!r}, base_url={self.base_url!r})"

    # ------------------------------------------------------------ подготовка

    def _prepare(self, op: Op) -> _Prepared:
        # default_headers кладём ПЕРВЫМИ, а служебные заголовки — поверх: иначе
        # случайный `{"Authorization": …}` в default_headers молча подменял бы
        # ключ (запрос ушёл бы с чужим или сломанным токеном). Менять User-Agent
        # штатно можно параметром user_agent, а не этим словарём.
        headers: Dict[str, str] = dict(self._extra_headers)
        headers.update(
            {
                "Authorization": f"Bearer {self._api_key}",
                # PDF-ручка на ошибках (400/404/429/503) отвечает JSON-конвертом,
                # поэтому одного application/pdf мало: строгий origin или CDN
                # вернул бы на такой ответ 406.
                "Accept": "application/pdf, application/json" if op.kind == KIND_BINARY else "application/json",
                "User-Agent": self.user_agent,
            }
        )
        request_id = str(uuid.uuid4())
        headers["X-Request-ID"] = request_id

        idempotency_key: Optional[str] = None
        if op.money:
            # Пустая строка — не «не передан», а ошибка вызывающего: сервер
            # ответил бы 400 idempotency_key_required уже после сетевого вызова.
            supplied = op.idempotency_key if op.idempotency_key is not None else str(uuid.uuid4())
            idempotency_key = validate_idempotency_key(supplied)
            headers["Idempotency-Key"] = idempotency_key
        elif op.idempotency_key is not None:
            # Не денежная ручка, но вызывающий дал ключ — отправляем, сервер
            # его проигнорирует; повторы при этом всё равно не включаем.
            headers["Idempotency-Key"] = validate_idempotency_key(op.idempotency_key)

        content: Optional[bytes] = None
        if op.body is not None:
            headers["Content-Type"] = "application/json"
            content = json.dumps(compact_body(op.body), separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        # Повторять можно только то, что не создаст второй заказ/списание:
        # чтение и мутации под Idempotency-Key (сервер отдаст сохранённый ответ).
        retryable = op.method in ("GET", "HEAD") or idempotency_key is not None
        return _Prepared(
            method=op.method,
            url=self.base_url + op.path,
            headers=headers,
            params=encode_params(op.params),
            content=content,
            request_id=request_id,
            idempotency_key=idempotency_key,
            retryable=retryable,
        )

    # ------------------------------------------------------------ ретраи

    def _retry_delay(self, response: httpx.Response, prepared: _Prepared, attempt: int) -> Optional[float]:
        """Сколько спать перед повтором, или None — отдать ответ как есть."""
        if not prepared.retryable or attempt >= self.max_retries:
            return None
        status = response.status_code
        if status in RETRY_STATUSES:
            pass
        elif status == 409 and _error_code(response) in RETRY_CONFLICT_CODES:
            pass
        else:
            return None
        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is None:
            return _backoff(attempt)
        if retry_after > self.max_retry_after:
            return None
        return retry_after

    def _transport_retry_delay(self, prepared: _Prepared, attempt: int) -> Optional[float]:
        if not prepared.retryable or attempt >= self.max_retries:
            return None
        return _backoff(attempt)

    # ------------------------------------------------------------ ответ

    def _meta(self, response: httpx.Response, prepared: _Prepared) -> ResponseMeta:
        return ResponseMeta(
            status=response.status_code,
            request_id=response.headers.get("X-Request-ID") or prepared.request_id,
            rate_limit=RateLimitInfo.from_headers(response.headers),
            sandbox=response.headers.get("X-Sandbox", "").strip().lower() == "true",
            idempotency_key=prepared.idempotency_key,
        )

    def _handle(self, response: httpx.Response, op: Op, prepared: _Prepared) -> Any:
        meta = self._meta(response, prepared)
        if response.status_code >= 400:
            raise self._error(response, meta)

        if op.kind == KIND_EMPTY or response.status_code == 204 or not response.content:
            result: Any = EmptyResult()
            result._meta = meta
            return result

        if op.kind == KIND_BINARY:
            result = BinaryResult(
                response.content,
                response.headers.get("Content-Type"),
                _filename(response.headers.get("Content-Disposition")),
            )
            result._meta = meta
            return result

        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(
                response.status_code,
                "invalid_response",
                "API returned a non-JSON body",
                request_id=meta.request_id,
                rate_limit=meta.rate_limit,
                sandbox=meta.sandbox,
                idempotency_key=meta.idempotency_key,
            ) from exc

        if op.kind == KIND_RAW:
            return payload
        if not isinstance(payload, dict):
            raise ApiError(response.status_code, "invalid_response", "API returned a non-object body", request_id=meta.request_id)

        model = op.model
        if op.models_by_status:
            # Разные успешные статусы — разные схемы (POST /servers: 201/202).
            model = op.models_by_status.get(response.status_code, model)

        if op.kind in (KIND_PAGE, KIND_LIST):
            items = [build(model, item) for item in payload.get("data") or []]
            if op.kind == KIND_PAGE:
                result = Page(items, payload.get("next_cursor"))
            else:
                result = ItemList(items)
            result._meta = meta
            result._raw = payload
            return result

        result = build(model, payload)
        result._meta = meta
        return result

    def _error(self, response: httpx.Response, meta: ResponseMeta) -> ApiError:
        status = response.status_code
        code: Optional[str] = None
        message: Optional[str] = None
        details: Dict[str, Any] = {}
        request_id = meta.request_id
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            err = payload["error"]
            code = err.get("code")
            message = err.get("message")
            request_id = err.get("request_id") or request_id
            if isinstance(err.get("details"), dict):
                details = err["details"]
        if not code:
            # Ответ не от API (прокси, балансировщик, HTML-страница): статус
            # остаётся главным, код — синтетический.
            code = f"http_{status}"
        if not message:
            message = (response.text or "").strip()[:200] or response.reason_phrase or f"HTTP {status}"
        cls = error_class_for(status)
        return cls(
            status,
            code,
            message,
            request_id=request_id,
            details=details,
            retry_after=parse_retry_after(response.headers.get("Retry-After")),
            rate_limit=meta.rate_limit,
            sandbox=meta.sandbox,
            idempotency_key=meta.idempotency_key,
        )

    def _transport_error(self, exc: Exception, prepared: _Prepared) -> TransportError:
        if isinstance(exc, httpx.TimeoutException):
            text = f"request timed out after {self.timeout}s"
        else:
            text = f"network error: {exc.__class__.__name__}: {exc}"
        return TransportError(text, request_id=prepared.request_id, cause=exc)


def _error_code(response: httpx.Response) -> Optional[str]:
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        code = payload["error"].get("code")
        return code if isinstance(code, str) else None
    return None


def _filename(disposition: Optional[str]) -> Optional[str]:
    if not disposition:
        return None
    match = _CONTENT_DISPOSITION_FILENAME.search(disposition)
    return match.group(1).strip() if match else None


# ==================================================================== sync


class Vdsok(_BaseClient):
    """Синхронный клиент VDSok Client API v1.

    ::

        from vdsok import Vdsok

        client = Vdsok("vk_live_...")
        for server in client.servers.list_all():
            print(server.id, server.name, server.status)

    Ключ никогда не логируется; ``repr(client)`` показывает только его
    «хвост». Клиент держит пул соединений — закрывайте его через ``close()``
    или ``with``.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
        http_client: Optional[httpx.Client] = None,
        user_agent: Optional[str] = None,
        default_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            max_retry_after=max_retry_after,
            user_agent=user_agent,
            default_headers=default_headers,
        )
        self._owns_http = http_client is None
        # follow_redirects=False: редирект унёс бы Authorization на чужой хост.
        self._http = http_client or httpx.Client(
            timeout=httpx.Timeout(self.timeout), follow_redirects=False, verify=_default_verify()
        )

        from . import _resources as r

        self.account = r.Account(self)
        self.balance = r.Balance(self)
        self.invoices = r.Invoices(self)
        self.catalog = r.Catalog(self)
        self.servers = r.Servers(self)
        self.domains = r.Domains(self)
        self.ssh_keys = r.SshKeys(self)
        self.keys = r.Keys(self)
        self.webhooks = r.Webhooks(self)

    # ------------------------------------------------------------ жизненный цикл

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "Vdsok":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------ отправка

    def _run(self, op: Op) -> Any:
        prepared = self._prepare(op)
        attempt = 0
        while True:
            try:
                response = self._http.request(
                    prepared.method,
                    prepared.url,
                    params=prepared.params,
                    headers=prepared.headers,
                    content=prepared.content,
                )
            except httpx.HTTPError as exc:
                delay = self._transport_retry_delay(prepared, attempt)
                if delay is None:
                    raise self._transport_error(exc, prepared) from exc
                attempt += 1
                _sleep(delay)
                continue
            delay = self._retry_delay(response, prepared, attempt)
            if delay is not None:
                response.close()
                attempt += 1
                _sleep(delay)
                continue
            return self._handle(response, op, prepared)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Optional[Mapping[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Any:
        """Произвольный вызов API, ответ — словарь как есть.

        Запасной выход для ручек, появившихся в API позже этой версии SDK.
        ``idempotency_key`` включает и заголовок, и ретраи.
        """
        op = Op(
            method.upper(),
            path if path.startswith("/") else "/" + path,
            params=params,
            body=json,
            kind=KIND_RAW,
            money=idempotency_key is not None,
            idempotency_key=idempotency_key,
        )
        return self._run(op)

    # ------------------------------------------------------------ meta

    def health(self):
        """``GET /health`` — живость API и выключен ли он персоналом."""
        from . import _ops

        return self._run(_ops.get_health())

    def me(self):
        """``GET /me`` — кто я: ключ, скоупы, режим, лимиты. Дешёвая проверка ключа."""
        from . import _ops

        return self._run(_ops.get_me())

    def openapi(self) -> Dict[str, Any]:
        """``GET /openapi.json`` — спецификация как словарь."""
        from . import _ops

        return self._run(_ops.get_openapi())


# ==================================================================== async


class AsyncVdsok(_BaseClient):
    """Асинхронный клиент VDSok Client API v1 (``httpx.AsyncClient``).

    ::

        async with AsyncVdsok("vk_live_...") as client:
            balance = await client.balance.get()
            async for server in client.servers.list_all():
                ...
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
        http_client: Optional[httpx.AsyncClient] = None,
        user_agent: Optional[str] = None,
        default_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            max_retry_after=max_retry_after,
            user_agent=user_agent,
            default_headers=default_headers,
        )
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout), follow_redirects=False, verify=_default_verify()
        )

        from . import _async_resources as r

        self.account = r.Account(self)
        self.balance = r.Balance(self)
        self.invoices = r.Invoices(self)
        self.catalog = r.Catalog(self)
        self.servers = r.Servers(self)
        self.domains = r.Domains(self)
        self.ssh_keys = r.SshKeys(self)
        self.keys = r.Keys(self)
        self.webhooks = r.Webhooks(self)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> "AsyncVdsok":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def _run(self, op: Op) -> Any:
        prepared = self._prepare(op)
        attempt = 0
        while True:
            try:
                response = await self._http.request(
                    prepared.method,
                    prepared.url,
                    params=prepared.params,
                    headers=prepared.headers,
                    content=prepared.content,
                )
            except httpx.HTTPError as exc:
                delay = self._transport_retry_delay(prepared, attempt)
                if delay is None:
                    raise self._transport_error(exc, prepared) from exc
                attempt += 1
                await _async_sleep(delay)
                continue
            delay = self._retry_delay(response, prepared, attempt)
            if delay is not None:
                await response.aclose()
                attempt += 1
                await _async_sleep(delay)
                continue
            return self._handle(response, op, prepared)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Optional[Mapping[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Any:
        """Произвольный вызов API, ответ — словарь как есть (см. ``Vdsok.request``)."""
        op = Op(
            method.upper(),
            path if path.startswith("/") else "/" + path,
            params=params,
            body=json,
            kind=KIND_RAW,
            money=idempotency_key is not None,
            idempotency_key=idempotency_key,
        )
        return await self._run(op)

    async def health(self):
        from . import _ops

        return await self._run(_ops.get_health())

    async def me(self):
        from . import _ops

        return await self._run(_ops.get_me())

    async def openapi(self) -> Dict[str, Any]:
        from . import _ops

        return await self._run(_ops.get_openapi())


__all__ = [
    "Vdsok",
    "AsyncVdsok",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
    "USER_AGENT",
    "parse_retry_after",
    "validate_idempotency_key",
]
