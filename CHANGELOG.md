# Changelog

All notable changes to the `vdsok` Python package are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
the project uses [Semantic Versioning](https://semver.org/). SDK 1.x tracks
VDSok Client API v1.

## 1.0.0

Initial release for VDSok Client API v1.

### Added

- `Vdsok` (sync) and `AsyncVdsok` (async) clients on `httpx`, Python 3.9+.
- Resource groups: `account`, `balance`, `invoices`, `catalog`, `servers`
  (with `actions`, `ips`, `orders`), `domains`, `ssh_keys`, `keys`, `webhooks`
  (with `deliveries`), plus `me()`, `health()`, `openapi()` and a raw
  `request()` escape hatch.
- Dataclass models for every schema in the OpenAPI document; money as
  `Decimal`, timestamps as tz-aware `datetime`, unknown fields kept in `.raw`.
- Automatic `Idempotency-Key` (UUID v4) on money endpoints, exposed as
  `result.idempotency_key` / `error.idempotency_key`; caller-supplied keys are
  validated (16..128 printable ASCII).
- Retries (default 2) for `GET` and idempotent mutations on `429`, `502`, `503`,
  `504`, `409 idempotency_in_progress` and network errors, honouring
  `Retry-After` (seconds or HTTP date) with exponential backoff fallback.
- `ApiError` hierarchy (`InvalidRequestError`, `AuthenticationError`,
  `InsufficientFundsError`, `PermissionDeniedError`, `NotFoundError`,
  `ConflictError`, `RateLimitError`, `ServerError`) with `status`, `code`,
  `message`, `request_id`, `details`, `retry_after`; `TransportError` for
  network failures.
- `RateLimitInfo`, `request_id` and `sandbox` on every result and error.
- Cursor pagination: `Page` objects and lazy `list_all()` iterators
  (async generators on `AsyncVdsok`).
- `servers.create()` returns `ServerCreated` on `201` and `Order` on
  `202 provisioning`, matching the two schemas in the spec; the
  `servers.orders.wait()` helper polls such an order to completion.
- Webhooks: `verify()`, `construct_event()`, `sign()` implementing
  `v1=HMAC-SHA256(secret, "{ts}.{body}")` with replay tolerance and
  multi-signature support during secret rotation. `verify` and
  `construct_event` share one argument order: `(secret, headers, raw_body)`.
- Typed package (`py.typed`).
