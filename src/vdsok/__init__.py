"""Официальный Python SDK для VDSok Client API v1.

::

    from vdsok import Vdsok

    client = Vdsok("vk_live_...")
    print(client.balance.get().balance)

Документация: https://vdsok.guru/developers
Исходники:    https://github.com/VDSok/sdk-python
"""

from ._client import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    USER_AGENT,
    AsyncVdsok,
    Vdsok,
)
from ._types import NOT_GIVEN, BinaryResult, EmptyResult, ItemList, Page, RateLimitInfo, ResponseMeta
from ._version import __version__
from .errors import (
    ApiError,
    AuthenticationError,
    ConflictError,
    InsufficientFundsError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TransportError,
    VdsokError,
    WebhookSignatureError,
)
from . import models
from . import webhooks
from .webhooks import Webhooks, construct_event, verify

# Модели доступны и напрямую: ``from vdsok import Server``.
from .models import *  # noqa: F401,F403

__all__ = [
    "__version__",
    "Vdsok",
    "AsyncVdsok",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
    "USER_AGENT",
    "NOT_GIVEN",
    "Page",
    "ItemList",
    "BinaryResult",
    "EmptyResult",
    "RateLimitInfo",
    "ResponseMeta",
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
    "Webhooks",
    "verify",
    "construct_event",
    "models",
    "webhooks",
] + list(models.__all__)
