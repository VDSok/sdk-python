"""Idempotency-Key на денежных ручках: генерация, проброс, валидация."""

import uuid

import pytest

from vdsok._client import validate_idempotency_key

from conftest import json_response
from fixtures import DOMAIN, SERVER

MONEY_OPS = [
    ("post", "/balance/topup", lambda c: c.balance.topup("25.00", "cryptobot"), {"invoice_id": 1, "payment_url": "https://p", "amount": "25.00", "currency": "USD", "gateway": "cryptobot"}),
    ("post", "/invoices/10231/pay", lambda c: c.invoices.pay(10231), {"invoice_id": 10231, "status": "paid", "balance_after": "1.00", "currency": "USD"}),
    ("post", "/servers", lambda c: c.servers.create(12, "ubuntu-24.04"), {"server": SERVER, "root_password": "p", "invoice_id": 1, "charged": "5.90", "currency": "USD", "balance_after": "1.00"}),
    ("delete", "/servers/2001", lambda c: c.servers.delete(2001), {"server_id": 2001, "status": "cancelled", "refund": None, "balance_after": "1.00", "currency": "USD"}),
    ("post", "/servers/2001/renew", lambda c: c.servers.renew(2001, hours=24), {"server": SERVER, "invoice_id": 1, "charged": "0.20", "currency": "USD", "balance_after": "1.00", "next_due_at": "2026-10-01T00:00:00Z"}),
    ("post", "/servers/2001/ips", lambda c: c.servers.ips.add(2001), {"ip": None, "invoice_id": 1, "charged": "0.50", "currency": "USD", "balance_after": "1.00", "recurring_amount": "7.90"}),
    ("post", "/domains", lambda c: c.domains.register("example.com"), {"domain": DOMAIN, "invoice_id": 1, "charged": "11.90", "currency": "USD", "balance_after": "1.00", "status": "registered"}),
    ("post", "/domains/77/renew", lambda c: c.domains.renew(77, 1), {"domain": DOMAIN, "invoice_id": 1, "charged": "12.50", "currency": "USD", "balance_after": "1.00", "status": "renewed"}),
    ("post", "/domains/transfers", lambda c: c.domains.transfer("example.org", "AbC"), {"domain": DOMAIN, "invoice_id": 1, "charged": "12.50", "currency": "USD", "balance_after": "1.00", "status": "transfer_pending"}),
]


@pytest.mark.parametrize("method,path,call,body", MONEY_OPS, ids=[m[1] for m in MONEY_OPS])
def test_money_ops_get_an_auto_key(api, client, method, path, call, body):
    route = getattr(api, method)(path).mock(return_value=json_response(200, body))
    result = call(client)
    key = route.calls.last.request.headers["Idempotency-Key"]
    uuid.UUID(key)
    assert result.idempotency_key == key
    assert result.meta.idempotency_key == key


def test_auto_key_differs_between_calls(api, client):
    route = api.post("/invoices/1/pay").mock(return_value=json_response(200, {"invoice_id": 1, "status": "paid", "balance_after": "1.00", "currency": "USD"}))
    client.invoices.pay(1)
    client.invoices.pay(1)
    keys = {c.request.headers["Idempotency-Key"] for c in route.calls}
    assert len(keys) == 2


def test_explicit_key_is_used(api, client):
    route = api.post("/invoices/1/pay").mock(return_value=json_response(200, {"invoice_id": 1, "status": "paid", "balance_after": "1.00", "currency": "USD"}))
    result = client.invoices.pay(1, idempotency_key="order-42-attempt-1")
    assert route.calls.last.request.headers["Idempotency-Key"] == "order-42-attempt-1"
    assert result.idempotency_key == "order-42-attempt-1"


@pytest.mark.parametrize("bad", ["short", "x" * 129, "has space here 1234", "", "тест-кириллица-1234"])
def test_invalid_key_rejected_before_sending(api, client, bad):
    route = api.post("/invoices/1/pay")
    with pytest.raises(ValueError):
        client.invoices.pay(1, idempotency_key=bad)
    assert route.call_count == 0


def test_validate_idempotency_key_accepts_uuid():
    key = str(uuid.uuid4())
    assert validate_idempotency_key(key) == key
    assert validate_idempotency_key("a" * 16) == "a" * 16
    assert validate_idempotency_key("a" * 128) == "a" * 128


def test_non_money_ops_send_no_key(api, client):
    route = api.post("/ssh-keys").mock(return_value=json_response(201, {"id": 1}))
    client.ssh_keys.create("n", "ssh-ed25519 AAAA")
    assert "Idempotency-Key" not in route.calls.last.request.headers
