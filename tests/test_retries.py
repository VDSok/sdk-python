"""Политика повторов: только GET и мутации под Idempotency-Key, Retry-After
уважается, лимит попыток соблюдается."""

import email.utils
import time

import httpx
import pytest

import vdsok
from vdsok import ConflictError, RateLimitError, ServerError, TransportError, Vdsok
from vdsok._client import parse_retry_after

from conftest import TEST_KEY, error_response, json_response
from fixtures import BALANCE, SERVER, SERVER_DETAIL


def test_get_retries_on_503_with_retry_after(api, client, sleeps):
    route = api.get("/balance").mock(
        side_effect=[error_response(503, "upstream_unavailable", **{"Retry-After": "2"}), json_response(200, BALANCE)]
    )
    balance = client.balance.get()
    assert balance.currency == "USD"
    assert route.call_count == 2
    assert sleeps == [2.0]


def test_get_retries_on_429_without_retry_after_uses_backoff(api, client, sleeps):
    api.get("/balance").mock(side_effect=[error_response(429, "rate_limited"), json_response(200, BALANCE)])
    client.balance.get()
    assert len(sleeps) == 1
    assert 0.3 <= sleeps[0] <= 0.7  # 0.5 * 2**0 с джиттером


@pytest.mark.parametrize("status,code", [(502, "upstream_error"), (504, "upstream_timeout")])
def test_get_retries_on_gateway_errors(api, client, sleeps, status, code):
    route = api.get("/balance").mock(side_effect=[error_response(status, code), json_response(200, BALANCE)])
    client.balance.get()
    assert route.call_count == 2


def test_retries_exhausted_raises_last_error(api, client, sleeps):
    route = api.get("/balance").mock(return_value=error_response(429, "rate_limited", **{"Retry-After": "1"}))
    with pytest.raises(RateLimitError) as info:
        client.balance.get()
    assert route.call_count == 3  # 1 + max_retries(2)
    assert sleeps == [1.0, 1.0]
    assert info.value.retry_after == 1.0


def test_max_retries_zero_means_no_retry(api, sleeps):
    route = api.get("/balance").mock(return_value=error_response(503, "api_disabled"))
    with Vdsok(TEST_KEY, max_retries=0) as c:
        with pytest.raises(ServerError):
            c.balance.get()
    assert route.call_count == 1
    assert sleeps == []


def test_500_is_not_retried(api, client, sleeps):
    route = api.get("/balance").mock(return_value=error_response(500, "server_error"))
    with pytest.raises(ServerError):
        client.balance.get()
    assert route.call_count == 1


def test_non_idempotent_post_is_never_retried(api, client, sleeps):
    route = api.post("/servers/2001/actions/power").mock(return_value=error_response(503, "upstream_unavailable", **{"Retry-After": "1"}))
    with pytest.raises(ServerError):
        client.servers.actions.restart(2001)
    assert route.call_count == 1
    assert sleeps == []


def test_patch_and_delete_without_key_are_not_retried(api, client, sleeps):
    api.patch("/servers/2001").mock(return_value=error_response(502, "upstream_error"))
    api.delete("/ssh-keys/3").mock(return_value=error_response(503, "upstream_unavailable"))
    with pytest.raises(ServerError):
        client.servers.update(2001, auto_renew=True)
    with pytest.raises(ServerError):
        client.ssh_keys.delete(3)
    assert sleeps == []


def test_money_mutation_is_retried_with_same_key_and_request_id(api, client, sleeps):
    route = api.post("/servers/2001/renew").mock(
        side_effect=[
            error_response(503, "temporarily_unavailable", **{"Retry-After": "3"}),
            json_response(200, {"server": SERVER, "invoice_id": 1, "charged": "5.90", "currency": "USD", "balance_after": "1.00", "next_due_at": "2026-11-01T00:00:00Z"}),
        ]
    )
    result = client.servers.renew(2001, months=1, idempotency_key="renew-2001-2026-09-15")
    assert route.call_count == 2
    assert sleeps == [3.0]
    first, second = route.calls[0].request, route.calls[1].request
    # Тот же ключ — сервер отдаст сохранённый результат вместо второго списания
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"] == "renew-2001-2026-09-15"
    assert first.headers["X-Request-ID"] == second.headers["X-Request-ID"]
    assert first.content == second.content
    assert result.idempotency_key == "renew-2001-2026-09-15"


def test_money_delete_is_retried(api, client, sleeps):
    route = api.delete("/servers/2001").mock(
        side_effect=[
            error_response(504, "upstream_timeout"),
            json_response(200, {"server_id": 2001, "status": "cancelled", "refund": None, "balance_after": "3.15", "currency": "USD"}),
        ]
    )
    result = client.servers.delete(2001)
    assert route.call_count == 2
    assert result.status == "cancelled"


def test_idempotency_in_progress_is_retried(api, client, sleeps):
    route = api.post("/balance/topup").mock(
        side_effect=[
            error_response(409, "idempotency_in_progress", **{"Retry-After": "1"}),
            json_response(201, {"invoice_id": 10240, "payment_url": "https://pay.example/x", "amount": "25.00", "currency": "USD", "gateway": "cryptobot", "expires_at": None}),
        ]
    )
    result = client.balance.topup("25", "cryptobot")
    assert route.call_count == 2
    assert sleeps == [1.0]
    assert result.invoice_id == 10240


def test_other_409_is_not_retried(api, client, sleeps):
    route = api.post("/balance/topup").mock(return_value=error_response(409, "idempotency_conflict"))
    with pytest.raises(ConflictError):
        client.balance.topup("25", "cryptobot")
    assert route.call_count == 1


def test_retry_after_above_cap_is_not_waited(api, sleeps):
    route = api.get("/balance").mock(return_value=error_response(429, "rate_limited", **{"Retry-After": "120"}))
    with Vdsok(TEST_KEY, max_retry_after=60) as c:
        with pytest.raises(RateLimitError) as info:
            c.balance.get()
    assert route.call_count == 1
    assert sleeps == []
    assert info.value.retry_after == 120.0


def test_retry_after_http_date(api, client, sleeps):
    when = email.utils.formatdate(time.time() + 5, usegmt=True)
    api.get("/balance").mock(side_effect=[error_response(503, "api_disabled", **{"Retry-After": when}), json_response(200, BALANCE)])
    client.balance.get()
    assert len(sleeps) == 1
    assert 3.0 <= sleeps[0] <= 5.5


def test_parse_retry_after_edge_cases():
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("garbage") is None
    assert parse_retry_after("15") == 15.0
    past = email.utils.formatdate(time.time() - 100, usegmt=True)
    assert parse_retry_after(past) == 0.0


def test_transport_error_on_get_is_retried(api, client, sleeps):
    route = api.get("/servers/2001").mock(side_effect=[httpx.ConnectError("boom"), json_response(200, SERVER_DETAIL)])
    server = client.servers.get(2001)
    assert server.id == 2001
    assert route.call_count == 2
    assert len(sleeps) == 1


def test_transport_error_exhausted(api, client, sleeps):
    route = api.get("/balance").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(TransportError):
        client.balance.get()
    assert route.call_count == 3


def test_transport_error_on_money_post_is_retried(api, client, sleeps):
    route = api.post("/servers/2001/ips").mock(
        side_effect=[
            httpx.ConnectError("boom"),
            json_response(201, {"ip": None, "invoice_id": 1, "charged": "0.50", "currency": "USD", "balance_after": "1.00", "recurring_amount": "7.90"}),
        ]
    )
    result = client.servers.ips.add(2001)
    assert route.call_count == 2
    assert result.charged.as_tuple().exponent == -2


def test_backoff_grows(monkeypatch):
    monkeypatch.setattr(vdsok._client.random, "random", lambda: 0.5)
    b = vdsok._client._backoff
    assert b(0) == 0.5
    assert b(1) == 1.0
    assert b(2) == 2.0
    assert b(10) == 8.0
