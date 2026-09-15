"""Служебные типы, общие для всех ответов SDK.

Каждый результат вызова (объект, список, страница, PDF, пустой ответ) несёт
метаданные ответа: request_id для обращения в поддержку, состояние
rate-limit, признак sandbox и Idempotency-Key, который SDK сгенерировал для
денежной операции. Их нельзя положить в поля dataclass-моделей, потому что
модели зеркалят схемы спецификации один в один; поэтому они живут в
``_meta`` и читаются через свойства базового класса ``ApiObject``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Generic, Iterator, List, Optional, TypeVar

T = TypeVar("T")


class _NotGiven:
    """Сентинел «параметр не передан».

    Нужен, потому что ``None`` в некоторых полях (``notes``, ``description``)
    — значимое значение «очистить», и его нельзя путать с «не менять».
    """

    _instance: Optional["_NotGiven"] = None

    def __new__(cls) -> "_NotGiven":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN = _NotGiven()


@dataclass(frozen=True)
class RateLimitInfo:
    """Состояние лимита запросов из заголовков ``X-RateLimit-*``.

    ``limit`` и ``remaining`` относятся к той корзине, в которую попал вызов
    (обычная 120/мин или «дорогая» 20/мин); ``reset`` — момент сброса окна.
    """

    limit: Optional[int]
    remaining: Optional[int]
    reset: Optional[datetime]

    @classmethod
    def from_headers(cls, headers: Any) -> Optional["RateLimitInfo"]:
        limit = _int_header(headers, "X-RateLimit-Limit")
        remaining = _int_header(headers, "X-RateLimit-Remaining")
        reset_raw = _int_header(headers, "X-RateLimit-Reset")
        if limit is None and remaining is None and reset_raw is None:
            return None
        reset = (
            datetime.fromtimestamp(reset_raw, tz=timezone.utc)
            if reset_raw is not None
            else None
        )
        return cls(limit=limit, remaining=remaining, reset=reset)


def _int_header(headers: Any, name: str) -> Optional[int]:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ResponseMeta:
    """Метаданные одного HTTP-ответа API."""

    status: int
    request_id: Optional[str]
    rate_limit: Optional[RateLimitInfo]
    sandbox: bool
    idempotency_key: Optional[str] = None


class ApiObject:
    """Базовый класс всех моделей и обёрток результатов.

    Не dataclass намеренно: у dataclass-наследников поля с default должны
    идти после полей без default, и служебные атрибуты базового класса
    ломали бы порядок. Поэтому ``_meta``/``_raw`` — обычные атрибуты
    экземпляра, выставляемые парсером после конструирования.
    """

    _meta: Optional[ResponseMeta] = None
    _raw: Optional[Dict[str, Any]] = None

    @property
    def meta(self) -> Optional[ResponseMeta]:
        """Метаданные ответа, из которого пришёл объект (None для вложенных)."""
        return self._meta

    @property
    def request_id(self) -> Optional[str]:
        """``X-Request-ID`` ответа — его просят в поддержке."""
        return self._meta.request_id if self._meta else None

    @property
    def rate_limit(self) -> Optional[RateLimitInfo]:
        return self._meta.rate_limit if self._meta else None

    @property
    def sandbox(self) -> bool:
        """True, если ответ пришёл тестовому ключу (``X-Sandbox: true``)."""
        return bool(self._meta and self._meta.sandbox)

    @property
    def idempotency_key(self) -> Optional[str]:
        """Idempotency-Key, с которым был сделан запрос (только денежные ручки)."""
        return self._meta.idempotency_key if self._meta else None

    @property
    def raw(self) -> Optional[Dict[str, Any]]:
        """Исходный JSON объекта — на случай полей, добавленных в API позже SDK."""
        return self._raw


class ItemList(ApiObject, List[T]):
    """Список без пагинации (``{"data": [...]}``): каталог, IP, SSH-ключи."""

    def __init__(self, items: Optional[List[T]] = None) -> None:
        super().__init__(items or [])


class Page(ApiObject, Generic[T]):
    """Одна страница курсорного списка.

    ``next_cursor`` передаётся в следующий вызов как ``cursor=``; он подписан
    сервером, собирать его вручную нельзя. Для обхода всех страниц есть
    ``list_all()`` у соответствующего ресурса.
    """

    def __init__(self, data: List[T], next_cursor: Optional[str]) -> None:
        self.data = data
        self.next_cursor = next_cursor

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None

    def __iter__(self) -> Iterator[T]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, index: int) -> T:
        return self.data[index]

    def __repr__(self) -> str:
        return f"Page(items={len(self.data)}, has_more={self.has_more})"


class BinaryResult(ApiObject):
    """Бинарный ответ (PDF счёта)."""

    def __init__(self, content: bytes, content_type: Optional[str], filename: Optional[str]) -> None:
        self.content = content
        self.content_type = content_type
        self.filename = filename

    def save(self, path: str) -> None:
        with open(path, "wb") as fh:
            fh.write(self.content)

    def __repr__(self) -> str:
        return f"BinaryResult(bytes={len(self.content)}, filename={self.filename!r})"


class EmptyResult(ApiObject):
    """Ответ ``204 No Content`` — тела нет, но request_id и лимиты доступны."""

    def __repr__(self) -> str:
        return f"EmptyResult(request_id={self.request_id!r})"
