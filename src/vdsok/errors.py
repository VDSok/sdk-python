"""Исключения SDK.

Единственная форма ошибки API — ``{"error": {code, message, request_id,
details}}``; она разбирается в ``ApiError`` и его подклассы по HTTP-статусу.
Подклассы нужны, чтобы писать ``except InsufficientFundsError`` вместо
сравнения статусов; ``code`` при этом остаётся главным дискриминатором,
потому что у одного статуса бывает несколько кодов (``409 no_capacity`` и
``409 idempotency_conflict`` требуют разной реакции).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._types import RateLimitInfo

__all__ = [
    "VdsokError",
    "TransportError",
    "ApiError",
    "InvalidRequestError",
    "AuthenticationError",
    "InsufficientFundsError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ServerError",
    "WebhookSignatureError",
]


class VdsokError(Exception):
    """Базовый класс всех исключений SDK."""


class TransportError(VdsokError):
    """Сеть/таймаут: ответа от API не было.

    ``request_id`` здесь — тот ``X-Request-ID``, который SDK сам поставил в
    запрос: если запрос всё же дошёл до сервера, по нему его найдут в логах.
    """

    def __init__(self, message: str, *, request_id: Optional[str] = None, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.message = message
        self.request_id = request_id
        self.cause = cause


class ApiError(VdsokError):
    """Ответ API со статусом 4xx/5xx.

    В сообщении и repr нет ни заголовков, ни ключа: исключения часто попадают
    в логи и трекеры ошибок целиком.
    """

    status: int
    code: str
    message: str
    request_id: Optional[str]
    details: Dict[str, Any]

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[float] = None,
        rate_limit: Optional[RateLimitInfo] = None,
        sandbox: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.details = details or {}
        self.retry_after = retry_after
        self.rate_limit = rate_limit
        self.sandbox = sandbox
        # Ключ идемпотентности денежной операции: с ним же можно безопасно
        # повторить запрос и получить сохранённый результат вместо второго
        # списания.
        self.idempotency_key = idempotency_key

    def __str__(self) -> str:
        text = f"[{self.status} {self.code}] {self.message}"
        if self.request_id:
            text += f" (request_id={self.request_id})"
        return text

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status={self.status}, code={self.code!r}, message={self.message!r}, request_id={self.request_id!r})"

    @property
    def is_retryable(self) -> bool:
        """Можно ли повторить тот же запрос позже без изменения данных."""
        return self.status in (429, 502, 503, 504) or self.code == "idempotency_in_progress"


class InvalidRequestError(ApiError):
    """400 / 413 / 415: запрос сформирован неверно (``validation_error``,
    ``invalid_period``, ``idempotency_key_required`` и т. п.)."""

    @property
    def fields(self) -> Dict[str, Any]:
        """Ошибки по полям из ``details.fields`` при ``validation_error``."""
        fields = self.details.get("fields")
        return fields if isinstance(fields, dict) else {}


class AuthenticationError(ApiError):
    """401: ключ неизвестен, отозван, истёк или ещё не действует."""


class InsufficientFundsError(ApiError):
    """402 ``insufficient_funds``: денег не хватило, ничего не списано."""

    @property
    def required(self) -> Optional[str]:
        return self.details.get("required")

    @property
    def balance(self) -> Optional[str]:
        return self.details.get("balance")

    @property
    def shortfall(self) -> Optional[str]:
        return self.details.get("shortfall")

    @property
    def currency(self) -> Optional[str]:
        return self.details.get("currency")


class PermissionDeniedError(ApiError):
    """403: нет скоупа, IP вне allow-list, аккаунт/услуга заблокированы,
    операция недоступна тестовому ключу."""

    @property
    def required_scopes(self) -> list:
        req = self.details.get("required")
        return list(req) if isinstance(req, (list, tuple)) else []


class NotFoundError(ApiError):
    """404: объекта нет на этом аккаунте."""


class ConflictError(ApiError):
    """409: конфликт состояния (``service_state``, ``no_capacity``,
    ``idempotency_conflict``, ``operation_in_progress`` ...)."""


class RateLimitError(ApiError):
    """429: корзина лимита исчерпана; ``retry_after`` — сколько ждать."""


class ServerError(ApiError):
    """5xx: сбой API или его upstream (панель, регистратор, шлюз)."""


class WebhookSignatureError(VdsokError):
    """Подпись вебхука не сошлась, устарела или отсутствует."""


_BY_STATUS = {
    400: InvalidRequestError,
    401: AuthenticationError,
    402: InsufficientFundsError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    413: InvalidRequestError,
    415: InvalidRequestError,
    429: RateLimitError,
}


def error_class_for(status: int) -> type:
    if status in _BY_STATUS:
        return _BY_STATUS[status]
    if status >= 500:
        return ServerError
    return ApiError
