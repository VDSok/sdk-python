"""Разбор ошибок API: статус -> класс, code/message/request_id/details."""

import httpx
import pytest

import vdsok
from vdsok import (
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
)

from conftest import error_response
from fixtures import BALANCE


@pytest.mark.parametrize(
    "status,code,cls",
    [
        (400, "validation_error", InvalidRequestError),
        (401, "invalid_token", AuthenticationError),
        (402, "insufficient_funds", InsufficientFundsError),
        (403, "insufficient_scope", PermissionDeniedError),
        (404, "not_found", NotFoundError),
        (409, "service_state", ConflictError),
        (413, "payload_too_large", InvalidRequestError),
        (415, "unsupported_media_type", InvalidRequestError),
        (429, "rate_limited", RateLimitError),
        (500, "server_error", ServerError),
        (502, "upstream_error", ServerError),
        (503, "api_disabled", ServerError),
        (504, "upstream_timeout", ServerError),
    ],
)
def test_status_maps_to_class(api, client, status, code, cls):
    # POST без Idempotency-Key не повторяется, поэтому и 429/5xx долетают сразу
    api.post("/ssh-keys").mock(return_value=error_response(status, code, "boom"))
    with pytest.raises(cls) as info:
        client.ssh_keys.create("x", "ssh-ed25519 AAAA")
    err = info.value
    assert isinstance(err, ApiError)
    assert err.status == status
    assert err.code == code
    assert err.message == "boom"
    assert err.request_id == "req_err0001"
    assert f"[{status} {code}] boom" in str(err)
    assert "req_err0001" in str(err)
    assert code in repr(err)


def test_error_details_and_helpers(api, client):
    api.post("/servers/2001/renew").mock(
        return_value=error_response(
            402,
            "insufficient_funds",
            "Balance 4.10 USD is below the required 5.90 USD",
            details={"required": "5.90", "balance": "4.10", "shortfall": "1.80", "currency": "USD"},
        )
    )
    with pytest.raises(InsufficientFundsError) as info:
        client.servers.renew(2001, months=1)
    err = info.value
    assert err.details["shortfall"] == "1.80"
    assert err.required == "5.90"
    assert err.balance == "4.10"
    assert err.shortfall == "1.80"
    assert err.currency == "USD"
    # денежная ручка: ключ идемпотентности доступен для безопасного повтора
    assert err.idempotency_key and len(err.idempotency_key) >= 16


def test_validation_fields(api, client):
    api.post("/ssh-keys").mock(
        return_value=error_response(400, "validation_error", "bad", details={"fields": {"public_key": "invalid"}})
    )
    with pytest.raises(InvalidRequestError) as info:
        client.ssh_keys.create("x", "nope")
    assert info.value.fields == {"public_key": "invalid"}


def test_required_scopes(api, client):
    api.post("/ssh-keys").mock(
        return_value=error_response(403, "insufficient_scope", "no", details={"required": ["servers:manage"]})
    )
    with pytest.raises(PermissionDeniedError) as info:
        client.ssh_keys.create("x", "ssh-ed25519 AAAA")
    assert info.value.required_scopes == ["servers:manage"]


def test_rate_limit_error_carries_headers(api, client):
    api.post("/ssh-keys").mock(
        return_value=error_response(
            429,
            "rate_limited",
            "Too many requests",
            details={"bucket": "expensive", "limit": 20},
            **{"Retry-After": "7", "X-RateLimit-Limit": "20", "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1789000000", "X-Sandbox": "true"},
        )
    )
    with pytest.raises(RateLimitError) as info:
        client.ssh_keys.create("x", "ssh-ed25519 AAAA")
    err = info.value
    assert err.retry_after == 7.0
    assert err.rate_limit.limit == 20
    assert err.rate_limit.remaining == 0
    assert err.sandbox is True
    assert err.is_retryable


def test_non_json_error_body(api, client):
    api.post("/ssh-keys").mock(return_value=httpx.Response(502, content=b"<html>Bad Gateway</html>", headers={"X-Request-ID": "req_proxy"}))
    with pytest.raises(ServerError) as info:
        client.ssh_keys.create("x", "ssh-ed25519 AAAA")
    err = info.value
    assert err.status == 502
    assert err.code == "http_502"
    assert "Bad Gateway" in err.message
    assert err.request_id == "req_proxy"


def test_unknown_4xx_status_is_generic_api_error(api, client):
    api.post("/ssh-keys").mock(return_value=error_response(418, "teapot"))
    with pytest.raises(ApiError) as info:
        client.ssh_keys.create("x", "ssh-ed25519 AAAA")
    assert type(info.value) is ApiError
    assert not info.value.is_retryable


def test_transport_error_on_post_is_not_retried(api, client, sleeps):
    api.post("/ssh-keys").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(TransportError) as info:
        client.ssh_keys.create("x", "ssh-ed25519 AAAA")
    assert "network error" in info.value.message
    assert info.value.request_id  # наш X-Request-ID, чтобы искать в логах
    assert isinstance(info.value.cause, httpx.ConnectError)
    assert sleeps == []


def test_timeout_message(api, client, sleeps):
    api.post("/ssh-keys").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(TransportError) as info:
        client.ssh_keys.create("x", "ssh-ed25519 AAAA")
    assert "timed out" in info.value.message


def test_error_hierarchy():
    assert issubclass(RateLimitError, ApiError)
    assert issubclass(ApiError, vdsok.VdsokError)
    assert issubclass(TransportError, vdsok.VdsokError)
    assert issubclass(vdsok.WebhookSignatureError, vdsok.VdsokError)


def test_error_never_contains_the_key(api, client):
    api.get("/balance").mock(return_value=error_response(401, "invalid_token", "Unknown or revoked API key"))
    with pytest.raises(AuthenticationError) as info:
        client.balance.get()
    assert "vk_test" not in str(info.value)
    assert "vk_test" not in repr(info.value)
    assert BALANCE  # fixture import kept for symmetry with other modules
