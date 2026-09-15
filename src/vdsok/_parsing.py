"""Преобразование JSON API <-> типизированные модели.

Деньги в API — строки с 2..4 знаками после точки, даты — RFC 3339 с ``Z``.
Здесь они превращаются в ``Decimal`` и tz-aware ``datetime`` и обратно.
Конвертация ведётся по аннотациям dataclass-полей, поэтому модели в
``models.py`` остаются декларативными и добавление поля в схему не требует
правки парсера.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional, Type, TypeVar, Union, get_type_hints

try:  # Python 3.8+ имеет get_origin/get_args; на 3.9 они уже в typing.
    from typing import get_args, get_origin
except ImportError:  # pragma: no cover
    from typing_extensions import get_args, get_origin  # type: ignore

from ._types import NOT_GIVEN, ApiObject

T = TypeVar("T")

_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")


def parse_timestamp(value: Any) -> Optional[datetime]:
    """RFC 3339 -> tz-aware datetime (UTC).

    ``datetime.fromisoformat`` до Python 3.11 не понимает суффикс ``Z`` и
    дробные секунды длиннее 6 знаков, поэтому строка нормализуется вручную.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        raise ValueError(f"timestamp must be a string, got {type(value).__name__}")
    m = _TS_RE.match(value.strip())
    if not m:
        raise ValueError(f"invalid RFC 3339 timestamp: {value!r}")
    base, frac, tz = m.groups()
    micro = 0
    if frac:
        digits = (frac[1:] + "000000")[:6]
        micro = int(digits)
    offset = "+00:00" if tz in (None, "Z") else tz
    dt = datetime.fromisoformat(base + offset)
    return dt.replace(microsecond=micro).astimezone(timezone.utc)


def format_timestamp(value: Union[datetime, date, str]) -> str:
    """datetime -> строка RFC 3339 в UTC с ``Z`` (формат, который принимает API)."""
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # Наивные даты считаем UTC: SDK не должен молча подмешивать
            # локальную зону машины, это самый частый источник сдвига на часы.
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        if value.microsecond:
            return value.strftime("%Y-%m-%dT%H:%M:%S.%f").rstrip("0") + "Z"
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%dT00:00:00Z")
    raise TypeError(f"unsupported timestamp type: {type(value).__name__}")


def parse_money(value: Any) -> Optional[Decimal]:
    """Строка ``"5.90"`` -> ``Decimal("5.90")``. Float не принимается."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        # API никогда не отдаёт float; если он тут появился — это ошибка
        # сериализации на сервере или подмена ответа, и лучше упасть громко.
        raise ValueError("money must be a decimal string, not float")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid money value: {value!r}") from exc


def format_money(value: Union[Decimal, int, str, float]) -> str:
    """Сумма для тела запроса: строка с 2..4 знаками после точки.

    Float допускается для удобства, но конвертируется через ``str``, чтобы
    ``0.1`` не превратился в ``0.1000000000000000055``. Больше четырёх
    знаков — ошибка вызывающего: округлять деньги молча SDK не должен.
    """
    if isinstance(value, bool):
        raise TypeError("money cannot be a bool")
    if isinstance(value, float):
        dec = Decimal(repr(value))
    elif isinstance(value, (Decimal, int, str)):
        try:
            dec = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValueError(f"invalid money value: {value!r}") from exc
    else:
        raise TypeError(f"unsupported money type: {type(value).__name__}")
    if not dec.is_finite():
        raise ValueError("money must be a finite number")
    exponent = dec.as_tuple().exponent
    places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    if places > 4:
        raise ValueError(f"money supports at most 4 fraction digits, got {value!r}")
    if places < 2:
        dec = dec.quantize(Decimal("0.01"))
    return format(dec, "f")


# ---------------------------------------------------------------- построение моделей

_HINTS_CACHE: Dict[type, Dict[str, Any]] = {}


def _hints(cls: type) -> Dict[str, Any]:
    hints = _HINTS_CACHE.get(cls)
    if hints is None:
        # Без явного globalns: get_type_hints сам берёт словарь модуля каждого
        # класса в MRO, поэтому строковые аннотации базового ApiObject из
        # ``_types`` резолвятся в его же пространстве имён, а не в models.
        hints = get_type_hints(cls)
        _HINTS_CACHE[cls] = hints
    return hints


def _convert(hint: Any, value: Any) -> Any:
    if value is None or hint is Any:
        return value
    origin = get_origin(hint)
    if origin is Union:
        args = [a for a in get_args(hint) if a is not type(None)]
        if len(args) == 1:
            return _convert(args[0], value)
        return value
    if origin in (list, List):
        (item_hint,) = get_args(hint) or (Any,)
        if isinstance(value, list):
            return [_convert(item_hint, v) for v in value]
        return value
    if origin in (dict, Dict, Mapping):
        return value
    if origin is not None:  # Literal и прочие обёртки — значение как есть
        return value
    if hint is Decimal:
        return parse_money(value)
    if hint is datetime:
        return parse_timestamp(value)
    if isinstance(hint, type) and dataclasses.is_dataclass(hint) and isinstance(value, dict):
        return build(hint, value)
    return value


def build(cls: Type[T], data: Mapping[str, Any]) -> T:
    """Собрать dataclass-модель из словаря JSON.

    Неизвестные ключи не ломают разбор (API растёт только аддитивно) и
    остаются доступными через ``.raw``; отсутствующие поля получают default.
    """
    if not isinstance(data, Mapping):
        raise TypeError(f"{cls.__name__} expects an object, got {type(data).__name__}")
    hints = _hints(cls)
    kwargs: Dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        try:
            kwargs[f.name] = _convert(hints.get(f.name, Any), data[f.name])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{cls.__name__}.{f.name}: {exc}") from exc
    obj = cls(**kwargs)
    if isinstance(obj, ApiObject):
        obj._raw = dict(data)
    return obj


# ---------------------------------------------------------------- параметры запросов


def encode_params(params: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """Query-параметры: None выбрасывается, bool -> ``true``/``false``,
    даты -> RFC 3339, Decimal -> строка. httpx сам бы сериализовал bool как
    ``True``, что сервер не примет."""
    out: Dict[str, str] = {}
    for key, value in (params or {}).items():
        if value is None or value is NOT_GIVEN:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (datetime, date)):
            out[key] = format_timestamp(value)
        elif isinstance(value, Decimal):
            out[key] = format(value, "f")
        else:
            out[key] = str(value)
    return out


def compact_body(body: Mapping[str, Any]) -> Dict[str, Any]:
    """Тело запроса: выбрасываются только NOT_GIVEN; явный None сохраняется
    (``notes: null`` очищает заметку)."""
    out: Dict[str, Any] = {}
    for key, value in body.items():
        if value is NOT_GIVEN:
            continue
        if isinstance(value, Decimal):
            value = format_money(value)
        elif isinstance(value, datetime):
            value = format_timestamp(value)
        out[key] = value
    return out
