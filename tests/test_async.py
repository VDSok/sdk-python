"""AsyncVdsok: та же логика, что у синхронного клиента, через httpx.AsyncClient."""

import json
import uuid
from decimal import Decimal

import httpx
import pytest

import vdsok
from vdsok import AsyncVdsok, RateLimitError, ServerError, TransportError

from conftest import TEST_KEY, error_response, json_response
from fixtures import BALANCE, ORDER, SERVER, SERVER_DETAIL, TARIFF, listing, page


async def test_headers_and_meta(api, aclient):
    route = api.get("/balance").mock(return_value=json_response(200, BALANCE, **{"X-RateLimit-Remaining": "5", "X-Sandbox": "true"}))
    balance = await aclient.balance.get()
    headers = route.calls.last.request.headers
    assert headers["Authorization"] == f"Bearer {TEST_KEY}"
    assert headers["User-Agent"].startswith("vdsok-sdk-python/")
    uuid.UUID(headers["X-Request-ID"])
    assert balance.balance == Decimal("42.15")
    assert balance.rate_limit.remaining == 5
    assert balance.sandbox is True
    assert balance.request_id == "req_test1234"


async def test_get_retry_with_retry_after(api, aclient, sleeps):
    route = api.get("/balance").mock(side_effect=[error_response(503, "api_disabled", **{"Retry-After": "4"}), json_response(200, BALANCE)])
    await aclient.balance.get()
    assert route.call_count == 2
    assert sleeps == [4.0]


async def test_retries_exhausted(api, aclient, sleeps):
    api.get("/balance").mock(return_value=error_response(429, "rate_limited"))
    with pytest.raises(RateLimitError):
        await aclient.balance.get()
    assert len(sleeps) == 2


async def test_non_idempotent_post_not_retried(api, aclient, sleeps):
    route = api.post("/ssh-keys").mock(return_value=error_response(502, "upstream_error"))
    with pytest.raises(ServerError):
        await aclient.ssh_keys.create("x", "ssh-ed25519 AAAA")
    assert route.call_count == 1


async def test_money_op_auto_key_and_retry(api, aclient, sleeps):
    route = api.post("/servers").mock(
        side_effect=[
            error_response(409, "idempotency_in_progress", **{"Retry-After": "1"}),
            json_response(201, {"server": SERVER, "root_password": "p", "invoice_id": 1, "charged": "5.90", "currency": "USD", "balance_after": "1.00"}),
        ]
    )
    created = await aclient.servers.create(12, "ubuntu-24.04", months=1)
    assert route.call_count == 2
    keys = {c.request.headers["Idempotency-Key"] for c in route.calls}
    assert len(keys) == 1
    assert created.idempotency_key in keys
    assert created.root_password == "p"
    assert json.loads(route.calls.last.request.content) == {"tariff_id": 12, "os": "ubuntu-24.04", "months": 1}


async def test_transport_error(api, aclient, sleeps):
    api.post("/ssh-keys").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(TransportError):
        await aclient.ssh_keys.create("x", "ssh-ed25519 AAAA")
    assert sleeps == []


async def test_list_all(api, aclient):
    route = api.get("/servers").mock(
        side_effect=[json_response(200, page([SERVER], "c2")), json_response(200, page([dict(SERVER, id=2002)], None))]
    )
    ids = [s.id async for s in aclient.servers.list_all(status="active")]
    assert ids == [2001, 2002]
    assert route.calls[1].request.url.params["cursor"] == "c2"


async def test_item_list_and_detail(api, aclient):
    api.get("/catalog/tariffs").mock(return_value=json_response(200, listing([TARIFF])))
    api.get("/servers/2001").mock(return_value=json_response(200, SERVER_DETAIL))
    tariffs = await aclient.catalog.tariffs()
    assert tariffs[0].price_hourly == Decimal("0.0083")
    server = await aclient.servers.get(2001)
    assert server.refund_quote.refundable is True


async def test_pdf_and_empty(api, aclient):
    api.get("/invoices/1/pdf").mock(return_value=httpx.Response(200, content=b"%PDF", headers={"Content-Type": "application/pdf"}))
    api.delete("/ssh-keys/1").mock(return_value=httpx.Response(204))
    assert (await aclient.invoices.pdf(1)).content == b"%PDF"
    assert isinstance(await aclient.ssh_keys.delete(1), vdsok.EmptyResult)


async def test_orders_wait(api, aclient, sleeps):
    api.get("/orders/10231").mock(side_effect=[json_response(200, ORDER), json_response(200, dict(ORDER, status="failed"))])
    order = await aclient.servers.orders.wait(10231, interval=3)
    assert order.status == "failed"
    assert sleeps == [3]


async def test_raw_request_and_meta_endpoints(api, aclient):
    api.get("/me").mock(return_value=json_response(200, {"account_id": 1}))
    api.get("/health").mock(return_value=json_response(200, {"status": "ok"}))
    api.get("/openapi.json").mock(return_value=json_response(200, {"openapi": "3.1.0"}))
    api.get("/x").mock(return_value=json_response(200, {"y": 1}))
    assert (await aclient.me()).account_id == 1
    assert (await aclient.health()).status == "ok"
    assert (await aclient.openapi())["openapi"] == "3.1.0"
    assert await aclient.request("GET", "/x") == {"y": 1}


async def test_external_client_not_closed():
    http = httpx.AsyncClient()
    c = AsyncVdsok(TEST_KEY, http_client=http)
    await c.aclose()
    assert not http.is_closed
    await http.aclose()


async def test_context_manager_closes_own_client():
    async with AsyncVdsok(TEST_KEY) as c:
        http = c._http
    assert http.is_closed
