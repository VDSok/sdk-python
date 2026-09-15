"""Матрица маршрутов: каждый метод ресурса бьёт в нужный метод+путь с нужным
телом/параметрами и возвращает модель нужного класса."""

import json

import pytest

from vdsok import ItemList, models

from conftest import json_response
from fixtures import (
    ACCOUNT,
    API_KEY,
    BALANCE,
    DELIVERY,
    DELIVERY_WITH_PAYLOAD,
    DOMAIN,
    DOMAIN_REGISTERED,
    DOMAIN_RENEWED,
    DOMAIN_TRANSFERRED,
    INVOICE,
    IP,
    LIVE_STATUS,
    LOCATION,
    ORDER,
    QUOTE,
    REFUND_QUOTE,
    SERVER,
    SERVER_DETAIL,
    SSH_KEY,
    TARIFF,
    WEBHOOK,
    WEBHOOK_EVENT,
    WEBHOOK_SECRET,
    WEBHOOK_WITH_SECRET,
    listing,
    page,
)

# (method, path, call, response status, response body, expected query, expected json body, model)
MATRIX = [
    ("GET", "/account", lambda c: c.account.get(), 200, ACCOUNT, {}, None, models.Account),
    ("GET", "/balance", lambda c: c.balance.get(), 200, BALANCE, {}, None, models.Balance),
    # Тело — ровно то, что отдаёт ручка: min/max и плоский список кодов.
    ("GET", "/balance/topup-info", lambda c: c.balance.topup_info(), 200, {"currency": "USD", "min": "5.00", "max": "1000.00", "first_topup_bonus_percent": 0, "first_topup_eligible": False, "gateways": ["cryptobot", "heleket"]}, {}, None, models.TopupInfo),
    ("POST", "/balance/topup", lambda c: c.balance.topup(25, "cryptobot"), 201, {"invoice_id": 10240, "payment_url": "https://pay.example/inv/abc", "amount": "25.00", "currency": "USD", "gateway": "cryptobot"}, {}, {"amount": "25.00", "gateway": "cryptobot"}, models.TopupResult),
    ("GET", "/invoices", lambda c: c.invoices.list(status="not_paid", type="topup"), 200, page([INVOICE]), {"status": "not_paid", "type": "topup"}, None, None),
    ("GET", "/invoices/10231", lambda c: c.invoices.get(10231), 200, INVOICE, {}, None, models.Invoice),
    # Успех у оплаты счёта ровно один — 200 paid: провижининг идёт фоном.
    ("POST", "/invoices/10231/pay", lambda c: c.invoices.pay(10231), 200, {"invoice_id": 10231, "status": "paid", "amount": "5.90", "currency": "USD", "balance_after": "4.10"}, {}, None, models.PayInvoiceResult),
    ("POST", "/invoices/10231/payment-link", lambda c: c.invoices.payment_link(10231, gateway="cryptobot"), 200, {"invoice_id": 10231, "payment_url": "https://p", "gateway": "cryptobot"}, {}, {"gateway": "cryptobot"}, models.PaymentLink),
    ("POST", "/invoices/10231/payment-link", lambda c: c.invoices.payment_link(10231), 200, {"invoice_id": 10231, "payment_url": "https://p", "gateway": "cryptobot"}, {}, {}, models.PaymentLink),
    ("GET", "/catalog/tariffs", lambda c: c.catalog.tariffs(location_id=1), 200, listing([TARIFF]), {"location_id": "1"}, None, None),
    ("GET", "/catalog/tariffs/12", lambda c: c.catalog.tariff(12), 200, TARIFF, {}, None, models.Tariff),
    ("GET", "/catalog/os", lambda c: c.catalog.os_images(tariff_id=12), 200, listing([{"slug": "ubuntu-24.04", "name": "Ubuntu 24.04", "family": "linux"}]), {"tariff_id": "12"}, None, None),
    ("GET", "/catalog/locations", lambda c: c.catalog.locations(), 200, listing([LOCATION]), {}, None, None),
    ("GET", "/catalog/zones", lambda c: c.catalog.zones(), 200, listing([{"tld": ".com", "price_register": "11.90", "price_renew": "12.50", "price_transfer": None, "currency": "USD", "min_years": 1, "max_years": 10, "privacy_supported": True}]), {}, None, None),
    ("GET", "/catalog/quote", lambda c: c.catalog.quote(12, months=3, promo_code="SALE"), 200, QUOTE, {"tariff_id": "12", "months": "3", "promo_code": "SALE"}, None, models.Quote),
    ("GET", "/catalog/quote", lambda c: c.catalog.quote(12, hours=48, billing_cycle="hourly"), 200, QUOTE, {"tariff_id": "12", "hours": "48", "billing_cycle": "hourly"}, None, models.Quote),
    ("GET", "/servers", lambda c: c.servers.list(ip="203.0.113.29"), 200, page([SERVER]), {"ip": "203.0.113.29"}, None, None),
    ("POST", "/servers", lambda c: c.servers.create(12, "ubuntu-24.04", name="web-01", months=1, ssh_key_ids=[3], custom_fields={"purpose": "web"}), 201, {"server": SERVER, "root_password": "s3cret", "invoice_id": 10231, "charged": "5.02", "currency": "USD", "balance_after": "37.13", "order_url": "/api/v1/orders/10231"}, {}, {"tariff_id": 12, "os": "ubuntu-24.04", "name": "web-01", "months": 1, "ssh_key_ids": [3], "custom_fields": {"purpose": "web"}}, models.ServerCreated),
    # 202 «panel timed out» описан в спеке схемой Order, а не ServerCreated.
    ("POST", "/servers", lambda c: c.servers.create(12, "ubuntu-24.04", hours=1, billing_cycle="hourly", password="Sup3rSecret!"), 202, ORDER, {}, {"tariff_id": 12, "os": "ubuntu-24.04", "hours": 1, "billing_cycle": "hourly", "password": "Sup3rSecret!"}, models.Order),
    ("GET", "/servers/2001", lambda c: c.servers.get(2001), 200, SERVER_DETAIL, {}, None, models.ServerDetail),
    ("GET", "/servers/2001", lambda c: c.servers.get(2001, include_live=True), 200, dict(SERVER_DETAIL, live=LIVE_STATUS), {"include": "live"}, None, models.ServerDetail),
    ("PATCH", "/servers/2001", lambda c: c.servers.update(2001, auto_renew=True, notes=None), 200, SERVER, {}, {"auto_renew": True, "notes": None}, models.Server),
    ("DELETE", "/servers/2001", lambda c: c.servers.delete(2001), 200, {"server_id": 2001, "status": "cancelled", "refund": "3.15", "currency": "USD", "balance_after": "45.30", "refund_quote": REFUND_QUOTE}, {}, None, models.DeleteResult),
    ("GET", "/servers/2001/status", lambda c: c.servers.status(2001), 200, LIVE_STATUS, {}, None, models.ServerLiveStatus),
    ("GET", "/servers/2001/refund-quote", lambda c: c.servers.refund_quote(2001), 200, REFUND_QUOTE, {}, None, models.RefundQuote),
    ("POST", "/servers/2001/renew", lambda c: c.servers.renew(2001, months=3), 200, {"server": SERVER, "invoice_id": 1, "charged": "14.29", "currency": "USD", "balance_after": "1.00", "next_due_at": "2027-01-01T00:00:00Z", "months": 3}, {}, {"months": 3}, models.RenewResult),
    ("POST", "/servers/2001/renew", lambda c: c.servers.renew(2001, hours=12), 200, {"server": SERVER, "invoice_id": None, "charged": "0.10", "currency": "USD", "balance_after": "1.00", "next_due_at": "2026-10-01T12:00:00Z", "hours": 12}, {}, {"hours": 12}, models.RenewResult),
    ("POST", "/servers/2001/actions/power", lambda c: c.servers.actions.power(2001, "restart"), 202, {"server_id": 2001, "action": "restart", "status": "accepted"}, {}, {"action": "restart"}, models.ActionResult),
    ("POST", "/servers/2001/actions/power", lambda c: c.servers.actions.start(2001), 202, {"server_id": 2001, "action": "start", "status": "accepted"}, {}, {"action": "start"}, models.ActionResult),
    ("POST", "/servers/2001/actions/power", lambda c: c.servers.actions.stop(2001), 202, {"server_id": 2001, "action": "stop", "status": "accepted"}, {}, {"action": "stop"}, models.ActionResult),
    ("POST", "/servers/2001/actions/reinstall", lambda c: c.servers.actions.reinstall(2001, "debian-12", ssh_key_ids=[3]), 202, {"server_id": 2001, "status": "reinstalling", "os": "debian-12", "root_password": None}, {}, {"os": "debian-12", "ssh_key_ids": [3]}, models.ReinstallResult),
    ("POST", "/servers/2001/actions/reset-password", lambda c: c.servers.actions.reset_password(2001), 200, {"server_id": 2001, "password": "n3w"}, {}, None, models.ResetPasswordResult),
    ("GET", "/orders", lambda c: c.servers.orders.list(status="provisioning"), 200, page([ORDER]), {"status": "provisioning"}, None, None),
    ("GET", "/orders/10231", lambda c: c.servers.orders.get(10231), 200, ORDER, {}, None, models.Order),
    ("GET", "/servers/2001/ips", lambda c: c.servers.ips.list(2001), 200, listing([IP]), {}, None, None),
    ("POST", "/servers/2001/ips", lambda c: c.servers.ips.add(2001), 201, {"success": True, "server_id": 2001, "charged": "0.53", "currency": "USD", "days": 16}, {}, None, models.IpAdded),
    ("GET", "/servers/2001/ips/quote", lambda c: c.servers.ips.quote(2001), 200, {"server_id": 2001, "price_monthly": "1.00", "prorated_now": "0.53", "currency": "USD", "next_due_at": None, "extra_ips": 1, "max_extra_ips": 5, "balance_sufficient": True}, {}, None, models.IpQuote),
    ("DELETE", "/servers/2001/ips/501", lambda c: c.servers.ips.delete(2001, 501), 200, {"status": "deleted", "server_id": 2001, "ip_id": 501}, {}, None, models.IpDeleted),
    # Поле тела — `domain` (роут принимает только его), ответ — {id, ptr}.
    ("PUT", "/servers/2001/ips/501/ptr", lambda c: c.servers.ips.set_ptr(2001, 501, "mail.example.com"), 200, {"id": 501, "ptr": "mail.example.com"}, {}, {"domain": "mail.example.com"}, models.PtrRecord),
    # Снятие записи: пустая строка уходит как есть, ptr возвращается null.
    ("PUT", "/servers/2001/ips/501/ptr", lambda c: c.servers.ips.set_ptr(2001, 501, ""), 200, {"id": 501, "ptr": None}, {}, {"domain": ""}, models.PtrRecord),
    ("GET", "/ssh-keys", lambda c: c.ssh_keys.list(), 200, listing([SSH_KEY]), {}, None, None),
    ("POST", "/ssh-keys", lambda c: c.ssh_keys.create("laptop", "ssh-ed25519 AAAA user@laptop"), 201, SSH_KEY, {}, {"name": "laptop", "public_key": "ssh-ed25519 AAAA user@laptop"}, models.SshKey),
    ("GET", "/domains/availability", lambda c: c.domains.check_availability("example.com"), 200, {"name": "example.com", "available": False, "reason": "taken", "premium": False, "price_register": "11.90", "price_renew": "12.50", "currency": "USD", "min_years": 1}, {"name": "example.com"}, None, models.AvailabilityResult),
    ("GET", "/domains", lambda c: c.domains.list(status="active"), 200, page([DOMAIN]), {"status": "active"}, None, None),
    ("POST", "/domains", lambda c: c.domains.register("example.com", years=2, privacy=True, nameservers=("ns1.example.net", "ns2.example.net")), 201, DOMAIN_REGISTERED, {}, {"name": "example.com", "years": 2, "privacy": True, "nameservers": ["ns1.example.net", "ns2.example.net"]}, models.DomainOrderResult),
    ("GET", "/domains/77", lambda c: c.domains.get(77), 200, DOMAIN, {}, None, models.Domain),
    ("PATCH", "/domains/77", lambda c: c.domains.update(77, privacy=False), 200, DOMAIN, {}, {"privacy": False}, models.Domain),
    ("POST", "/domains/77/renew", lambda c: c.domains.renew(77, 1), 200, DOMAIN_RENEWED, {}, {"years": 1}, models.DomainRenewResult),
    ("PUT", "/domains/77/nameservers", lambda c: c.domains.set_nameservers(77, ["ns1.example.net", "ns2.example.net"]), 200, DOMAIN, {}, {"nameservers": ["ns1.example.net", "ns2.example.net"]}, models.Domain),
    ("POST", "/domains/transfers", lambda c: c.domains.transfer("example.org", "AbC-123-xyz"), 202, DOMAIN_TRANSFERRED, {}, {"name": "example.org", "auth_code": "AbC-123-xyz"}, models.DomainTransferResult),
    ("GET", "/keys", lambda c: c.keys.list(), 200, page([API_KEY]), {}, None, None),
    ("GET", "/keys/3", lambda c: c.keys.get(3), 200, API_KEY, {}, None, models.ApiKey),
    ("DELETE", "/keys/3", lambda c: c.keys.revoke(3), 200, {"status": "revoked", "key": dict(API_KEY, active=False, revoked_at="2026-09-15T10:00:00Z")}, {}, None, models.ApiKeyRevoked),
    ("GET", "/webhooks", lambda c: c.webhooks.list(), 200, page([WEBHOOK]), {}, None, None),
    ("POST", "/webhooks", lambda c: c.webhooks.create("https://hooks.example.com/vdsok", ["server.created", "invoice.paid"], description="billing sync"), 201, WEBHOOK_WITH_SECRET, {}, {"url": "https://hooks.example.com/vdsok", "events": ["server.created", "invoice.paid"], "description": "billing sync"}, models.WebhookSubscriptionWithSecret),
    ("GET", "/webhooks/events", lambda c: c.webhooks.events(), 200, listing([{"type": "ping", "description": "Тестовая отправка"}]), {}, None, None),
    ("GET", "/webhooks/5", lambda c: c.webhooks.get(5), 200, WEBHOOK, {}, None, models.WebhookSubscription),
    ("PATCH", "/webhooks/5", lambda c: c.webhooks.update(5, active=True, events=["ping"]), 200, WEBHOOK, {}, {"active": True, "events": ["ping"]}, models.WebhookSubscription),
    ("POST", "/webhooks/5/rotate-secret", lambda c: c.webhooks.rotate_secret(5), 200, WEBHOOK_SECRET, {}, None, models.WebhookSecret),
    ("POST", "/webhooks/5/test", lambda c: c.webhooks.test(5), 200, {"delivery": DELIVERY, "ok": True, "status": 200, "latency_ms": 120, "detail": None}, {}, None, models.WebhookTestResult),
    ("GET", "/webhooks/5/deliveries", lambda c: c.webhooks.deliveries.list(5, status="dead", event_type="invoice.paid"), 200, page([DELIVERY]), {"status": "dead", "event_type": "invoice.paid"}, None, None),
    ("GET", "/webhooks/deliveries/900", lambda c: c.webhooks.deliveries.get(900), 200, DELIVERY_WITH_PAYLOAD, {}, None, models.WebhookDeliveryWithPayload),
    ("POST", "/webhooks/deliveries/900/redeliver", lambda c: c.webhooks.deliveries.redeliver(900), 202, {"status": "queued", "delivery": dict(DELIVERY, delivered_at=None, dead=False)}, {}, None, models.WebhookRedelivery),
]


def _ids():
    return [f"{m[0]} {m[1]} #{i}" for i, m in enumerate(MATRIX)]


@pytest.mark.parametrize("method,path,call,status,body,query,expected_json,model", MATRIX, ids=_ids())
def test_route(api, client, method, path, call, status, body, query, expected_json, model):
    route = api.route(method=method, path=path).mock(return_value=json_response(status, body))
    result = call(client)
    assert route.call_count == 1
    request = route.calls.last.request
    assert dict(request.url.params) == query
    if expected_json is None:
        assert request.content == b""
        assert "Content-Type" not in request.headers or "json" not in request.headers["Content-Type"]
    else:
        assert json.loads(request.content) == expected_json
    if model is not None:
        assert isinstance(result, model)
    else:
        assert isinstance(result, (list, ItemList)) or hasattr(result, "data")
    assert result.meta.status == status


def test_list_results_are_typed(api, client):
    api.get("/catalog/tariffs").mock(return_value=json_response(200, listing([TARIFF])))
    tariffs = client.catalog.tariffs()
    assert isinstance(tariffs, ItemList)
    assert isinstance(tariffs[0], models.Tariff)
    assert tariffs.request_id == "req_test1234"
    assert len(tariffs) == 1


def test_delete_webhook_returns_status_and_id(api, client):
    """webhooks.py:webhooks_delete отвечает 200 с телом, а не пустым 204."""
    api.delete("/webhooks/5").mock(return_value=json_response(200, {"status": "deleted", "id": 5}))
    result = client.webhooks.delete(5)
    assert result.status == "deleted" and result.id == 5


def test_revoke_current(api, client):
    api.get("/me").mock(return_value=json_response(200, {"account_id": 57, "key": API_KEY}))
    route = api.delete("/keys/3").mock(
        return_value=json_response(200, {"status": "revoked", "key": dict(API_KEY, active=False)})
    )
    revoked = client.keys.revoke_current()
    assert route.call_count == 1
    assert revoked.status == "revoked"
    assert revoked.key.active is False


def test_orders_wait(api, client, sleeps):
    api.get("/orders/10231").mock(
        side_effect=[json_response(200, ORDER), json_response(200, dict(ORDER, status="active", server_id=2001))]
    )
    order = client.servers.orders.wait(10231, interval=2)
    assert order.status == "active" and order.server_id == 2001
    assert sleeps == [2]


def test_orders_wait_timeout(api, client, sleeps, monkeypatch):
    api.get("/orders/10231").mock(return_value=json_response(200, ORDER))
    clock = iter([0.0, 0.0, 100.0, 100.0])
    # подменяем СВОЮ обёртку, а не time.monotonic у модуля time: последнее
    # действовало бы на весь процесс, включая посторонний код в этом прогоне.
    monkeypatch.setattr("vdsok._client._monotonic", lambda: next(clock))
    with pytest.raises(TimeoutError):
        client.servers.orders.wait(10231, timeout=50, interval=1)


def test_create_server_202_is_an_order(api, client):
    """202 отдаёт Order с полями заказа, а не пустой ServerCreated."""
    api.post("/servers").mock(return_value=json_response(202, ORDER))
    created = client.servers.create(12, "ubuntu-24.04", months=1)
    assert isinstance(created, models.Order)
    assert created.invoice_id == ORDER["invoice_id"]
    assert created.status == "provisioning"
    assert created.order_url == ORDER["order_url"]
    # дальше вызывающий идёт в orders.wait(created.invoice_id)
    api.get(f"/orders/{ORDER['invoice_id']}").mock(
        return_value=json_response(200, dict(ORDER, status="active", server_id=2001))
    )
    assert client.servers.orders.wait(created.invoice_id).server_id == 2001


def test_create_server_201_is_server_created(api, client):
    api.post("/servers").mock(
        return_value=json_response(201, {"server": SERVER, "root_password": "s3cret", "invoice_id": 10231})
    )
    created = client.servers.create(12, "ubuntu-24.04", months=1)
    assert isinstance(created, models.ServerCreated)
    assert created.server.id == 2001 and created.root_password == "s3cret"


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.servers.update(2001),
        lambda c: c.domains.update(77),
        lambda c: c.webhooks.update(5),
        lambda c: c.servers.renew(2001),
        lambda c: c.servers.renew(2001, months=1, hours=1),
        lambda c: c.servers.create(12, "ubuntu", months=1, hours=1),
        lambda c: c.catalog.quote(12, months=1, hours=1),
        lambda c: c.servers.actions.power(2001, "reboot"),
        lambda c: c.domains.set_nameservers(77, ["only-one"]),
        lambda c: c.servers.get(0),
        lambda c: c.servers.get(-5),
    ],
)
def test_client_side_validation(api, client, call):
    with pytest.raises(ValueError):
        call(client)
    assert len(api.calls) == 0


def test_id_type_validation(api, client):
    with pytest.raises(TypeError):
        client.servers.get("abc")
    with pytest.raises(TypeError):
        client.servers.get(None)
    assert len(api.calls) == 0


def test_numeric_string_id_is_accepted(api, client):
    api.get("/servers/2001").mock(return_value=json_response(200, SERVER_DETAIL))
    assert client.servers.get("2001").id == 2001


def test_webhook_event_fixture_is_valid():
    # держим пример в fixtures синхронным с моделью
    assert models.parse(models.WebhookEvent, WEBHOOK_EVENT).id == "evt_01J7ZK3Q9X4R"
