"""Проверка подписи входящих вебхуков VDSok и разбор события.

Каждая доставка подписана так (см. ``components.securitySchemes.webhookSignature``):

* ``X-Webhook-Signature: v1=<hex HMAC-SHA256(secret, "{ts}.{body}")>``
* ``X-Webhook-Timestamp: <unix seconds>``
* ``X-Webhook-Id`` / ``X-Webhook-Event`` — id и тип события.

Подпись считается по **сырым байтам тела**, не по пересериализованному JSON:
любая перестановка ключей или пробел сломает HMAC. Поэтому обработчик должен
брать тело до разбора (``request.get_data()`` во Flask, ``await
request.body()`` в FastAPI и т. п.).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union

from ._parsing import build
from .errors import WebhookSignatureError
from .models import WebhookEvent

__all__ = ["DEFAULT_TOLERANCE", "sign", "verify", "construct_event", "Webhooks"]

# Спецификация: отвергать, если |now - timestamp| > 300 секунд.
DEFAULT_TOLERANCE = 300

SIGNATURE_HEADER = "x-webhook-signature"
TIMESTAMP_HEADER = "x-webhook-timestamp"

BodyLike = Union[bytes, bytearray, memoryview, str]
HeadersLike = Union[Mapping[str, Any], Iterable[Tuple[str, Any]]]


def _body_bytes(raw_body: BodyLike) -> bytes:
    if isinstance(raw_body, str):
        return raw_body.encode("utf-8")
    if isinstance(raw_body, (bytes, bytearray, memoryview)):
        return bytes(raw_body)
    raise TypeError("raw_body must be bytes or str (the request body exactly as received)")


def _secret_bytes(secret: Union[str, bytes]) -> bytes:
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    if not secret:
        raise ValueError("webhook secret is empty")
    return secret


def _normalize_headers(headers: HeadersLike) -> Dict[str, str]:
    """Заголовки в нижнем регистре: фреймворки отдают их в разном регистре и
    разными типами (dict, ``httpx.Headers``, список пар WSGI)."""
    items = headers.items() if hasattr(headers, "items") else headers
    out: Dict[str, str] = {}
    for key, value in items:  # type: ignore[union-attr]
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        out[str(key).lower()] = str(value)
    return out


def sign(secret: Union[str, bytes], timestamp: Union[int, str], raw_body: BodyLike) -> str:
    """Подпись в том виде, в котором её шлёт VDSok: ``v1=<hex>``.

    Пригодится, чтобы сгенерировать тестовую доставку для своего обработчика.
    """
    ts = str(int(timestamp))
    digest = hmac.new(_secret_bytes(secret), ts.encode("ascii") + b"." + _body_bytes(raw_body), hashlib.sha256)
    return "v1=" + digest.hexdigest()


def _parse_signature_header(value: str) -> Iterable[str]:
    """``v1=abc, v1=def`` -> ["abc", "def"]. Несколько подписей возможны в
    момент ротации секрета; версии кроме ``v1`` пропускаем."""
    for part in value.replace(" ", "").split(","):
        if not part:
            continue
        version, _, sig = part.partition("=")
        if version == "v1" and sig:
            yield sig.lower()


def _check(
    secret: Union[str, bytes],
    headers: HeadersLike,
    raw_body: BodyLike,
    tolerance: Optional[int],
    now: Optional[float],
) -> None:
    h = _normalize_headers(headers)
    signature_header = h.get(SIGNATURE_HEADER)
    timestamp_header = h.get(TIMESTAMP_HEADER)
    if not signature_header:
        raise WebhookSignatureError("missing X-Webhook-Signature header")
    if not timestamp_header:
        raise WebhookSignatureError("missing X-Webhook-Timestamp header")
    try:
        timestamp = int(timestamp_header.strip())
    except ValueError:
        raise WebhookSignatureError("X-Webhook-Timestamp is not an integer") from None

    candidates = list(_parse_signature_header(signature_header))
    if not candidates:
        raise WebhookSignatureError("no v1 signature found in X-Webhook-Signature")

    expected = sign(secret, timestamp, raw_body)[3:]
    # compare_digest по каждому кандидату: время сравнения не зависит от того,
    # на каком байте разошлись строки.
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise WebhookSignatureError("signature mismatch")

    if tolerance is not None:
        current = now if now is not None else time.time()
        if abs(current - timestamp) > tolerance:
            raise WebhookSignatureError(f"timestamp outside tolerance of {tolerance}s (replay?)")


def verify(
    secret: Union[str, bytes],
    headers: HeadersLike,
    raw_body: BodyLike,
    tolerance: Optional[int] = DEFAULT_TOLERANCE,
    now: Optional[float] = None,
) -> bool:
    """True, если подпись верна и метка времени свежая; иначе False.

    Не бросает исключений — удобно в ``if not verify(...): abort(400)``.
    ``tolerance=None`` отключает проверку времени (только для тестов).
    """
    try:
        _check(secret, headers, raw_body, tolerance, now)
    except WebhookSignatureError:
        return False
    return True


def construct_event(
    secret: Union[str, bytes],
    headers: HeadersLike,
    raw_body: BodyLike,
    tolerance: Optional[int] = DEFAULT_TOLERANCE,
    now: Optional[float] = None,
) -> WebhookEvent:
    """Проверить подпись и вернуть разобранный ``WebhookEvent``.

    Порядок аргументов тот же, что у ``verify`` — ``(secret, headers,
    raw_body)``. Раньше он был обратным, и перепутать две функции, которые
    интегратор копирует из README рядом друг с другом, было слишком легко.

    Бросает ``WebhookSignatureError`` при любой проблеме с подписью и
    ``ValueError``, если тело — не JSON-объект события.
    """
    _check(secret, headers, raw_body, tolerance, now)
    import json

    try:
        payload = json.loads(_body_bytes(raw_body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"webhook body is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("webhook body must be a JSON object")
    return build(WebhookEvent, payload)


class Webhooks:
    """Те же функции в виде класса — для тех, кому привычнее
    ``Webhooks.verify(...)`` в стиле других SDK."""

    DEFAULT_TOLERANCE = DEFAULT_TOLERANCE
    sign = staticmethod(sign)
    verify = staticmethod(verify)
    construct_event = staticmethod(construct_event)
