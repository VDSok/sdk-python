"""Асинхронные группы ресурсов — зеркало ``_resources.py`` для ``AsyncVdsok``.

Отдельный файл, а не автогенерация из синхронного: у публичного SDK методы
должны иметь честные сигнатуры ``async def ... -> Model``, иначе IDE и mypy
не поймут, что результат нужно ``await``. Паритет с синхронной версией
проверяет тест ``tests/test_parity.py``.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Awaitable, Callable, Iterable, Optional, TYPE_CHECKING, Union

from . import _ops as ops
from ._ops import MoneyLike, TimestampLike
from ._types import NOT_GIVEN, BinaryResult, EmptyResult, ItemList, Page
from . import models as m
from . import webhooks as _webhooks

if TYPE_CHECKING:  # pragma: no cover
    from ._client import AsyncVdsok


async def _iterate(fetch: Callable[..., Awaitable[Page]], **filters: Any) -> AsyncIterator[Any]:
    cursor: Optional[str] = None
    while True:
        page = await fetch(cursor=cursor, **filters)
        for item in page.data:
            yield item
        if not page.next_cursor or page.next_cursor == cursor:
            return
        cursor = page.next_cursor


class _Resource:
    def __init__(self, client: "AsyncVdsok") -> None:
        self._c = client


# ---------------------------------------------------------------- Account / Balance


class Account(_Resource):
    async def get(self) -> m.Account:
        return await self._c._run(ops.get_account())


class Balance(_Resource):
    async def get(self) -> m.Balance:
        return await self._c._run(ops.get_balance())

    async def transactions(
        self,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        direction: Optional[str] = None,
        since: Optional[TimestampLike] = None,
        until: Optional[TimestampLike] = None,
    ) -> Page[m.Transaction]:
        return await self._c._run(ops.list_transactions(cursor, limit, direction, since, until))

    def transactions_all(
        self,
        *,
        limit: Optional[int] = None,
        direction: Optional[str] = None,
        since: Optional[TimestampLike] = None,
        until: Optional[TimestampLike] = None,
    ) -> AsyncIterator[m.Transaction]:
        return _iterate(self.transactions, limit=limit, direction=direction, since=since, until=until)

    async def topup_info(self) -> m.TopupInfo:
        return await self._c._run(ops.get_topup_info())

    async def topup(
        self,
        amount: MoneyLike,
        gateway: str,
        *,
        idempotency_key: Optional[str] = None,
    ) -> m.TopupResult:
        return await self._c._run(ops.create_topup(amount, gateway, idempotency_key))


# ---------------------------------------------------------------- Invoices


class Invoices(_Resource):
    async def list(
        self,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        type: Optional[str] = None,
    ) -> Page[m.Invoice]:
        return await self._c._run(ops.list_invoices(cursor, limit, status, type))

    def list_all(
        self, *, limit: Optional[int] = None, status: Optional[str] = None, type: Optional[str] = None
    ) -> AsyncIterator[m.Invoice]:
        return _iterate(self.list, limit=limit, status=status, type=type)

    async def get(self, invoice_id: int) -> m.Invoice:
        return await self._c._run(ops.get_invoice(invoice_id))

    async def pdf(self, invoice_id: int) -> BinaryResult:
        return await self._c._run(ops.get_invoice_pdf(invoice_id))

    async def pay(self, invoice_id: int, *, idempotency_key: Optional[str] = None) -> m.PayInvoiceResult:
        return await self._c._run(ops.pay_invoice(invoice_id, idempotency_key))

    async def payment_link(
        self, invoice_id: int, *, gateway: Any = NOT_GIVEN
    ) -> m.PaymentLink:
        return await self._c._run(ops.create_invoice_payment_link(invoice_id, gateway))


# ---------------------------------------------------------------- Catalog


class Catalog(_Resource):
    async def tariffs(self, *, location_id: Optional[int] = None) -> ItemList[m.Tariff]:
        return await self._c._run(ops.list_tariffs(location_id))

    async def tariff(self, tariff_id: int) -> m.Tariff:
        return await self._c._run(ops.get_tariff(tariff_id))

    async def os_images(self, *, tariff_id: Optional[int] = None) -> ItemList[m.OsImage]:
        return await self._c._run(ops.list_os_images(tariff_id))

    async def locations(self) -> ItemList[m.Location]:
        return await self._c._run(ops.list_locations())

    async def zones(self) -> ItemList[m.Zone]:
        return await self._c._run(ops.list_zones())

    async def quote(
        self,
        tariff_id: int,
        *,
        months: Optional[int] = None,
        hours: Optional[int] = None,
        billing_cycle: Optional[str] = None,
        promo_code: Optional[str] = None,
    ) -> m.Quote:
        return await self._c._run(ops.get_quote(tariff_id, months, hours, billing_cycle, promo_code))


# ---------------------------------------------------------------- Servers


class ServerActions(_Resource):
    async def power(self, server_id: int, action: str) -> m.ActionResult:
        return await self._c._run(ops.power_server(server_id, action))

    async def start(self, server_id: int) -> m.ActionResult:
        return await self.power(server_id, "start")

    async def stop(self, server_id: int) -> m.ActionResult:
        return await self.power(server_id, "stop")

    async def restart(self, server_id: int) -> m.ActionResult:
        return await self.power(server_id, "restart")

    async def reinstall(
        self, server_id: int, os: str, *, password: Any = NOT_GIVEN, ssh_key_ids: Any = NOT_GIVEN
    ) -> m.ReinstallResult:
        return await self._c._run(ops.reinstall_server(server_id, os, password, ssh_key_ids))

    async def reset_password(self, server_id: int) -> m.ResetPasswordResult:
        return await self._c._run(ops.reset_server_password(server_id))


class ServerIps(_Resource):
    async def list(self, server_id: int) -> ItemList[m.Ip]:
        return await self._c._run(ops.list_server_ips(server_id))

    async def quote(self, server_id: int) -> m.IpQuote:
        return await self._c._run(ops.get_server_ip_quote(server_id))

    async def add(self, server_id: int, *, idempotency_key: Optional[str] = None) -> m.IpAdded:
        return await self._c._run(ops.add_server_ip(server_id, idempotency_key))

    async def delete(self, server_id: int, ip_id: int) -> m.IpDeleted:
        return await self._c._run(ops.delete_server_ip(server_id, ip_id))

    async def set_ptr(self, server_id: int, ip_id: int, ptr: Optional[str]) -> m.PtrRecord:
        """Пустая строка или ``None`` снимают запись. Возвращает ``{id, ptr}``."""
        return await self._c._run(ops.set_server_ip_ptr(server_id, ip_id, ptr))


class Orders(_Resource):
    async def list(
        self, *, cursor: Optional[str] = None, limit: Optional[int] = None, status: Optional[str] = None
    ) -> Page[m.Order]:
        return await self._c._run(ops.list_orders(cursor, limit, status))

    def list_all(self, *, limit: Optional[int] = None, status: Optional[str] = None) -> AsyncIterator[m.Order]:
        return _iterate(self.list, limit=limit, status=status)

    async def get(self, invoice_id: int) -> m.Order:
        return await self._c._run(ops.get_order(invoice_id))

    async def wait(self, invoice_id: int, *, timeout: float = 600.0, interval: float = 5.0) -> m.Order:
        from . import _client

        deadline = _client._monotonic() + timeout
        while True:
            order = await self.get(invoice_id)
            if order.is_terminal:
                return order
            if _client._monotonic() >= deadline:
                raise TimeoutError(f"order {invoice_id} is still {order.status} after {timeout}s")
            await _client._async_sleep(interval)


class Servers(_Resource):
    def __init__(self, client: "AsyncVdsok") -> None:
        super().__init__(client)
        self.actions = ServerActions(client)
        self.ips = ServerIps(client)
        self.orders = Orders(client)

    async def list(
        self,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> Page[m.Server]:
        return await self._c._run(ops.list_servers(cursor, limit, status, ip))

    def list_all(
        self, *, limit: Optional[int] = None, status: Optional[str] = None, ip: Optional[str] = None
    ) -> AsyncIterator[m.Server]:
        return _iterate(self.list, limit=limit, status=status, ip=ip)

    async def create(
        self,
        tariff_id: int,
        os: str,
        *,
        name: Any = NOT_GIVEN,
        password: Any = NOT_GIVEN,
        months: Any = NOT_GIVEN,
        hours: Any = NOT_GIVEN,
        billing_cycle: Any = NOT_GIVEN,
        promo_code: Any = NOT_GIVEN,
        ssh_key_ids: Any = NOT_GIVEN,
        custom_fields: Any = NOT_GIVEN,
        idempotency_key: Optional[str] = None,
    ) -> Union[m.ServerCreated, m.Order]:
        # 202 -> Order (см. docstring синхронного Servers.create).
        return await self._c._run(
            ops.create_server(
                tariff_id, os, name, password, months, hours, billing_cycle, promo_code, ssh_key_ids, custom_fields, idempotency_key
            )
        )

    async def get(self, server_id: int, *, include_live: bool = False) -> m.ServerDetail:
        return await self._c._run(ops.get_server(server_id, include_live))

    async def update(
        self, server_id: int, *, auto_renew: Any = NOT_GIVEN, name: Any = NOT_GIVEN, notes: Any = NOT_GIVEN
    ) -> m.Server:
        return await self._c._run(ops.update_server(server_id, auto_renew, name, notes))

    async def delete(self, server_id: int, *, idempotency_key: Optional[str] = None) -> m.DeleteResult:
        return await self._c._run(ops.delete_server(server_id, idempotency_key))

    async def status(self, server_id: int) -> m.ServerLiveStatus:
        return await self._c._run(ops.get_server_status(server_id))

    async def refund_quote(self, server_id: int) -> m.RefundQuote:
        return await self._c._run(ops.get_server_refund_quote(server_id))

    async def renew(
        self,
        server_id: int,
        *,
        months: Optional[int] = None,
        hours: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> m.RenewResult:
        return await self._c._run(ops.renew_server(server_id, months, hours, idempotency_key))


# ---------------------------------------------------------------- Domains


class Domains(_Resource):
    async def check_availability(self, name: str) -> m.AvailabilityResult:
        return await self._c._run(ops.check_domain_availability(name))

    async def list(
        self, *, cursor: Optional[str] = None, limit: Optional[int] = None, status: Optional[str] = None
    ) -> Page[m.Domain]:
        return await self._c._run(ops.list_domains(cursor, limit, status))

    def list_all(self, *, limit: Optional[int] = None, status: Optional[str] = None) -> AsyncIterator[m.Domain]:
        return _iterate(self.list, limit=limit, status=status)

    async def register(
        self,
        name: str,
        *,
        years: Any = NOT_GIVEN,
        nameservers: Any = NOT_GIVEN,
        privacy: Any = NOT_GIVEN,
        promo_code: Any = NOT_GIVEN,
        idempotency_key: Optional[str] = None,
    ) -> m.DomainOrderResult:
        return await self._c._run(
            ops.register_domain(name, years, nameservers, privacy, promo_code, idempotency_key)
        )

    async def get(self, domain_id: int) -> m.Domain:
        return await self._c._run(ops.get_domain(domain_id))

    async def update(self, domain_id: int, *, auto_renew: Any = NOT_GIVEN, privacy: Any = NOT_GIVEN) -> m.Domain:
        return await self._c._run(ops.update_domain(domain_id, auto_renew, privacy))

    async def renew(self, domain_id: int, years: int, *, idempotency_key: Optional[str] = None) -> m.DomainRenewResult:
        return await self._c._run(ops.renew_domain(domain_id, years, idempotency_key))

    async def set_nameservers(self, domain_id: int, nameservers: Iterable[str]) -> m.Domain:
        return await self._c._run(ops.set_domain_nameservers(domain_id, nameservers))

    async def transfer(
        self,
        name: str,
        auth_code: str,
        *,
        nameservers: Any = NOT_GIVEN,
        idempotency_key: Optional[str] = None,
    ) -> m.DomainTransferResult:
        return await self._c._run(ops.transfer_domain(name, auth_code, nameservers, idempotency_key))


# ---------------------------------------------------------------- SSH keys


class SshKeys(_Resource):
    async def list(self) -> ItemList[m.SshKey]:
        return await self._c._run(ops.list_ssh_keys())

    async def create(self, name: str, public_key: str) -> m.SshKey:
        return await self._c._run(ops.create_ssh_key(name, public_key))

    async def delete(self, key_id: int) -> EmptyResult:
        return await self._c._run(ops.delete_ssh_key(key_id))


# ---------------------------------------------------------------- Keys


class Keys(_Resource):
    async def list(self) -> Page[m.ApiKey]:
        return await self._c._run(ops.list_api_keys())

    async def get(self, key_id: int) -> m.ApiKey:
        return await self._c._run(ops.get_api_key(key_id))

    async def revoke(self, key_id: int) -> m.ApiKeyRevoked:
        return await self._c._run(ops.revoke_api_key(key_id))

    async def revoke_current(self) -> m.ApiKeyRevoked:
        me = await self._c.me()
        if me.key is None or me.key.id is None:
            raise RuntimeError("GET /me did not return the current key id")
        return await self.revoke(me.key.id)


# ---------------------------------------------------------------- Webhooks


class WebhookDeliveries(_Resource):
    async def list(
        self,
        webhook_id: int,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> Page[m.WebhookDelivery]:
        return await self._c._run(ops.list_webhook_deliveries(webhook_id, cursor, limit, status, event_type))

    def list_all(
        self,
        webhook_id: int,
        *,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> AsyncIterator[m.WebhookDelivery]:
        return _iterate(self.list, webhook_id=webhook_id, limit=limit, status=status, event_type=event_type)

    async def get(self, delivery_id: int) -> m.WebhookDeliveryWithPayload:
        return await self._c._run(ops.get_webhook_delivery(delivery_id))

    async def redeliver(self, delivery_id: int) -> m.WebhookRedelivery:
        return await self._c._run(ops.redeliver_webhook(delivery_id))


class Webhooks(_Resource):
    verify = staticmethod(_webhooks.verify)
    construct_event = staticmethod(_webhooks.construct_event)
    sign = staticmethod(_webhooks.sign)

    def __init__(self, client: "AsyncVdsok") -> None:
        super().__init__(client)
        self.deliveries = WebhookDeliveries(client)

    async def list(self) -> Page[m.WebhookSubscription]:
        return await self._c._run(ops.list_webhooks())

    async def create(
        self, url: str, events: Iterable[str], *, description: Any = NOT_GIVEN
    ) -> m.WebhookSubscriptionWithSecret:
        return await self._c._run(ops.create_webhook(url, events, description))

    async def events(self) -> ItemList[m.WebhookEventDescriptor]:
        return await self._c._run(ops.list_webhook_events())

    async def get(self, webhook_id: int) -> m.WebhookSubscription:
        return await self._c._run(ops.get_webhook(webhook_id))

    async def update(
        self,
        webhook_id: int,
        *,
        url: Any = NOT_GIVEN,
        events: Any = NOT_GIVEN,
        description: Any = NOT_GIVEN,
        active: Any = NOT_GIVEN,
    ) -> m.WebhookSubscription:
        return await self._c._run(ops.update_webhook(webhook_id, url, events, description, active))

    async def delete(self, webhook_id: int) -> m.WebhookDeleted:
        return await self._c._run(ops.delete_webhook(webhook_id))

    async def rotate_secret(self, webhook_id: int) -> m.WebhookSecret:
        return await self._c._run(ops.rotate_webhook_secret(webhook_id))

    async def test(self, webhook_id: int) -> m.WebhookTestResult:
        return await self._c._run(ops.test_webhook(webhook_id))
