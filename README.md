# vdsok — Python SDK for the VDSok Client API

[![PyPI](https://img.shields.io/pypi/v/vdsok.svg)](https://pypi.org/project/vdsok/)
[![Python](https://img.shields.io/pypi/pyversions/vdsok.svg)](https://pypi.org/project/vdsok/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-vdsok.guru%2Fdevelopers-0a7)](https://vdsok.guru/developers)

Official Python client for the [VDSok Client API v1](https://vdsok.guru/developers):
balance and invoices, the VDS catalog, servers (order, renew, power, reinstall,
IPs, PTR, SSH keys, delete with refund), domains, API keys and webhooks.

* Sync `Vdsok` and async `AsyncVdsok` on top of [httpx](https://www.python-httpx.org/)
* Typed dataclass models mirroring the OpenAPI schemas, `Decimal` money, tz-aware `datetime`
* Automatic `Idempotency-Key` on money endpoints, safe retries with `Retry-After`
* Cursor pagination helpers (`list_all()`), `X-Request-ID` and rate-limit info on every result
* Webhook signature verification (`verify`, `construct_event`)
* Python 3.9+, one dependency (`httpx`)

Source: <https://github.com/VDSok/sdk-python> · Docs: <https://vdsok.guru/developers> · Issues: <https://github.com/VDSok/sdk-python/issues>

## Install

```bash
pip install vdsok
```

## Quick start

```python
from vdsok import Vdsok

client = Vdsok("vk_live_...")           # create keys in the cabinet at /my/api

me = client.me()
print(me.account_id, me.scopes, me.livemode)   # livemode is False for vk_test_… keys

balance = client.balance.get()
print(balance.balance, balance.currency)   # Decimal('42.15') USD

for server in client.servers.list_all(status="active"):
    print(server.id, server.name, server.primary_ip, server.billing.next_due_at)
```

Async:

```python
import asyncio
from vdsok import AsyncVdsok

async def main():
    async with AsyncVdsok("vk_live_...") as client:
        tariffs = await client.catalog.tariffs()
        async for server in client.servers.list_all():
            print(server.name)

asyncio.run(main())
```

Use a `vk_test_...` key to try everything without spending money: reads return
real data, writes are simulated and every response is flagged
`result.sandbox == True`.

## Configuration

```python
Vdsok(
    api_key,
    base_url="https://vdsok.guru/api/v1",
    timeout=30.0,          # seconds, per request
    max_retries=2,         # on 429/502/503/504 and network errors
    max_retry_after=60.0,  # longer Retry-After is not waited for
    http_client=None,      # bring your own httpx.Client (proxies, certificates, ...)
    user_agent=None,       # replaces "vdsok-sdk-python/<version> ..."
    default_headers=None,  # extra headers on every request
)
```

Every request carries `Authorization: Bearer <key>`, `Accept: application/json`,
`User-Agent: vdsok-sdk-python/<version>` and a fresh `X-Request-ID` (UUID v4).
The key is never logged; `repr(client)` shows only its last characters.
`default_headers` is merged *under* those four, so it can add headers but never
replace the credential — change the agent string with `user_agent=` instead.

## Resources

| Group | Methods |
| --- | --- |
| `client.me()` / `health()` / `openapi()` | calling key, liveness, the spec |
| `client.account` | `get()` |
| `client.balance` | `get()`, `transactions()`, `transactions_all()`, `topup_info()`, `topup(amount, gateway)` |
| `client.invoices` | `list()`, `list_all()`, `get(id)`, `pdf(id)`, `pay(id)`, `payment_link(id)` |
| `client.catalog` | `tariffs()`, `tariff(id)`, `os_images()`, `locations()`, `zones()`, `quote(tariff_id, months=…)` |
| `client.servers` | `list()`, `list_all()`, `create(tariff_id, os, …)`, `get(id, include_live=…)`, `update(id, …)`, `delete(id)`, `status(id)`, `refund_quote(id)`, `renew(id, months=…)` |
| `client.servers.actions` | `power(id, action)`, `start(id)`, `stop(id)`, `restart(id)`, `reinstall(id, os, …)`, `reset_password(id)` |
| `client.servers.ips` | `list(id)`, `quote(id)`, `add(id)`, `delete(id, ip_id)`, `set_ptr(id, ip_id, ptr)` |
| `client.servers.orders` | `list()`, `list_all()`, `get(invoice_id)`, `wait(invoice_id)` |
| `client.domains` | `check_availability(name)`, `list()`, `list_all()`, `register(name, …)`, `get(id)`, `update(id, …)`, `renew(id, years)`, `set_nameservers(id, [...])`, `transfer(name, auth_code)` |
| `client.ssh_keys` | `list()`, `create(name, public_key)`, `delete(id)` |
| `client.keys` | `list()`, `get(id)`, `revoke(id)`, `revoke_current()` |
| `client.webhooks` | `list()`, `create(url, events)`, `events()`, `get(id)`, `update(id, …)`, `delete(id)`, `rotate_secret(id)`, `test(id)`, `verify(...)`, `construct_event(...)` |
| `client.webhooks.deliveries` | `list(webhook_id)`, `list_all(webhook_id)`, `get(delivery_id)`, `redeliver(delivery_id)` |

Anything the API adds later is reachable through the escape hatch:

```python
client.request("GET", "/servers", params={"limit": 5})   # -> dict
```

## Ordering a server

```python
from vdsok import InsufficientFundsError, ConflictError, Order

quote = client.catalog.quote(12, months=3)
if not quote.balance_sufficient:
    print("top up", quote.shortfall, quote.currency)

try:
    created = client.servers.create(12, "ubuntu-24.04", name="web-01", months=3, ssh_key_ids=[3])
except InsufficientFundsError as e:
    print("need", e.shortfall, e.currency, "more")      # nothing was charged
except ConflictError as e:
    print(e.code)                                       # no_capacity, tariff_unavailable, ...
else:
    if isinstance(created, Order):                      # 202: charged, still provisioning
        created = client.servers.orders.wait(created.invoice_id)
        print(created.status, created.server_id)        # active / cancelled (refunded)
    else:                                               # 201: up and running
        print(created.server.primary_ip, created.root_password)  # password is shown once
```

`servers.create()` returns a `ServerCreated` on `201` and an `Order` on
`202 provisioning` (the charge is kept, the panel was slow). `orders.wait()`
polls `GET /orders/{invoice_id}` until the order is `active` or `cancelled`
(a failed order is refunded and reported as `cancelled`).

An hourly order prepays exactly one hour: pass `hours=1` (anything else is a
`400`) and buy the rest with `servers.renew(id, hours=…)`, up to 2160 at a
time.

## Money, idempotency and retries

Money is always a `Decimal` (`"5.90"` on the wire, never a float). Amounts you
pass in may be `Decimal`, `int` or a numeric string; floats are converted
through their `repr` and anything beyond 4 fraction digits is rejected.

Endpoints that move money (`servers.create`, `servers.renew`, `servers.delete`,
`servers.ips.add`, `invoices.pay`, `balance.topup`, `domains.register`,
`domains.renew`, `domains.transfer`) require an `Idempotency-Key`. The SDK
generates a UUID for you and exposes it on the result and on any error:

```python
result = client.servers.renew(2001, months=1)
print(result.idempotency_key)

try:
    client.servers.renew(2001, months=1, idempotency_key="renew-2001-2026-09")
except vdsok.ServerError as e:
    # replaying with the same key returns the stored outcome instead of charging twice
    client.servers.renew(2001, months=1, idempotency_key=e.idempotency_key)
```

Retries (default 2) happen only where they are safe: `GET` requests and
mutations that carry an `Idempotency-Key`. They trigger on `429`, `502`, `503`,
`504`, `409 idempotency_in_progress` and network errors, honour `Retry-After`
(seconds or HTTP date) and fall back to exponential backoff. A plain `POST`
like `servers.actions.restart()` is never retried automatically.

## Errors

```python
import vdsok

try:
    client.servers.get(999)
except vdsok.NotFoundError as e:
    print(e.status, e.code, e.message, e.request_id)   # 404 not_found ... 9f1c2a9d-4b7e-...
except vdsok.RateLimitError as e:
    time.sleep(e.retry_after or 1)
except vdsok.ApiError as e:                            # any other 4xx/5xx
    print(e.details)
except vdsok.TransportError as e:                      # no HTTP response at all
    print(e.request_id)                                # the X-Request-ID the SDK sent
```

| Class | Status |
| --- | --- |
| `InvalidRequestError` | 400, 413, 415 (`.fields` for `validation_error`) |
| `AuthenticationError` | 401 |
| `InsufficientFundsError` | 402 (`.required`, `.balance`, `.shortfall`, `.currency`) |
| `PermissionDeniedError` | 403 (`.required_scopes`) |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |
| `RateLimitError` | 429 (`.retry_after`) |
| `ServerError` | 5xx |

Every result and error exposes `request_id`, `rate_limit`
(`RateLimitInfo(limit, remaining, reset)`), `sandbox` and, on money endpoints,
`idempotency_key`. Results also keep the original JSON in `.raw`.

## Pagination

```python
page = client.invoices.list(limit=50, status="not_paid")
page.data, page.next_cursor, page.has_more
nxt = client.invoices.list(cursor=page.next_cursor)

for invoice in client.invoices.list_all(status="not_paid"):   # lazy, all pages
    ...
```

## Webhooks

Both entry points take the same arguments in the same order —
`(secret, headers, raw_body, tolerance=300)`:

```python
from vdsok import construct_event, verify, WebhookSignatureError

# Flask
@app.post("/vdsok-webhook")
def hook():
    try:
        event = construct_event(WEBHOOK_SECRET, request.headers, request.get_data())
    except WebhookSignatureError:
        abort(400)
    if event.type == "server.suspended":
        server = vdsok.models.parse(vdsok.Server, event.data.object)
        ...
    return "", 204
```

```python
# same check, without exceptions
if not verify(WEBHOOK_SECRET, request.headers, request.get_data()):
    abort(400)
```

Always pass the raw request body: the signature covers the exact bytes VDSok
sent, so a re-serialized JSON will not match. Deliveries are retried, so
deduplicate by `event.id` (`X-Webhook-Id`).

## Development

```bash
pip install -e ".[dev]"
pytest
```

The test suite mocks HTTP with [respx](https://github.com/lundberg/respx) and
never touches the network.

## Versioning

SDK 1.x tracks API v1. The API only grows additively; breaking changes go to
`/v2` and a new SDK major. See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).
