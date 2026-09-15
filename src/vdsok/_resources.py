"""Синхронные группы ресурсов: ``client.servers``, ``client.domains`` и т. д.

Каждый метод — тонкая обёртка: собирает ``Op`` через ``_ops`` и отдаёт его
клиенту. Вся HTTP-логика (ретраи, Idempotency-Key, разбор) — в ``_client``.
Асинхронный близнец в ``_async_resources.py`` повторяет этот файл метод в
метод; тест паритета следит, чтобы они не разъехались.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator, Optional, TYPE_CHECKING, Union

from . import _ops as ops
from ._ops import MoneyLike, TimestampLike
from ._types import NOT_GIVEN, BinaryResult, EmptyResult, ItemList, Page
from . import models as m
from . import webhooks as _webhooks

if TYPE_CHECKING:  # pragma: no cover
    from ._client import Vdsok


def _iterate(fetch: Callable[..., Page], **filters: Any) -> Iterator[Any]:
    """Обход всех страниц курсорного списка.

    Останавливается на ``next_cursor = null``; повтор того же курсора
    считается ошибкой сервера и тоже прерывает цикл — иначе итератор стал бы
    бесконечным.
    """
    cursor: Optional[str] = None
    while True:
        page = fetch(cursor=cursor, **filters)
        for item in page.data:
            yield item
        if not page.next_cursor or page.next_cursor == cursor:
            return
        cursor = page.next_cursor


class _Resource:
    def __init__(self, client: "Vdsok") -> None:
        self._c = client


# ---------------------------------------------------------------- Account / Balance


class Account(_Resource):
    def get(self) -> m.Account:
        """``GET /account`` — профиль, группа клиента и скидка."""
        return self._c._run(ops.get_account())


class Balance(_Resource):
    def get(self) -> m.Balance:
        """``GET /balance`` — баланс и ближайшие списания."""
        return self._c._run(ops.get_balance())

    def transactions(
        self,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        direction: Optional[str] = None,
        since: Optional[TimestampLike] = None,
        until: Optional[TimestampLike] = None,
    ) -> Page[m.Transaction]:
        """``GET /transactions`` — страница операций по балансу, новые первыми."""
        return self._c._run(ops.list_transactions(cursor, limit, direction, since, until))

    def transactions_all(
        self,
        *,
        limit: Optional[int] = None,
        direction: Optional[str] = None,
        since: Optional[TimestampLike] = None,
        until: Optional[TimestampLike] = None,
    ) -> Iterator[m.Transaction]:
        """Все операции по балансу через все страницы."""
        return _iterate(self.transactions, limit=limit, direction=direction, since=since, until=until)

    def topup_info(self) -> m.TopupInfo:
        """``GET /balance/topup-info`` — лимиты пополнения и доступные шлюзы."""
        return self._c._run(ops.get_topup_info())

    def topup(
        self,
        amount: MoneyLike,
        gateway: str,
        *,
        idempotency_key: Optional[str] = None,
    ) -> m.TopupResult:
        """``POST /balance/topup`` — счёт на пополнение и ссылка на оплату.

        Денежная ручка: Idempotency-Key генерируется автоматически и доступен
        в ``result.idempotency_key``.
        """
        return self._c._run(ops.create_topup(amount, gateway, idempotency_key))


# ---------------------------------------------------------------- Invoices


class Invoices(_Resource):
    def list(
        self,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        type: Optional[str] = None,
    ) -> Page[m.Invoice]:
        """``GET /invoices`` — страница счетов, новые первыми."""
        return self._c._run(ops.list_invoices(cursor, limit, status, type))

    def list_all(
        self, *, limit: Optional[int] = None, status: Optional[str] = None, type: Optional[str] = None
    ) -> Iterator[m.Invoice]:
        return _iterate(self.list, limit=limit, status=status, type=type)

    def get(self, invoice_id: int) -> m.Invoice:
        """``GET /invoices/{id}`` — счёт с позициями."""
        return self._c._run(ops.get_invoice(invoice_id))

    def pdf(self, invoice_id: int) -> BinaryResult:
        """``GET /invoices/{id}/pdf`` — PDF счёта (``result.content``, ``result.save(path)``)."""
        return self._c._run(ops.get_invoice_pdf(invoice_id))

    def pay(self, invoice_id: int, *, idempotency_key: Optional[str] = None) -> m.PayInvoiceResult:
        """``POST /invoices/{id}/pay`` — оплатить с баланса. ``status = provisioning``
        означает, что заказ ещё создаётся — опрашивайте ``servers.orders.get``."""
        return self._c._run(ops.pay_invoice(invoice_id, idempotency_key))

    def payment_link(
        self, invoice_id: int, *, gateway: Any = NOT_GIVEN
    ) -> m.PaymentLink:
        """``POST /invoices/{id}/payment-link`` — ссылка на оплату через шлюз."""
        return self._c._run(ops.create_invoice_payment_link(invoice_id, gateway))


# ---------------------------------------------------------------- Catalog


class Catalog(_Resource):
    def tariffs(self, *, location_id: Optional[int] = None) -> ItemList[m.Tariff]:
        """``GET /catalog/tariffs`` — тарифы VDS с учётом скидки вызывающего."""
        return self._c._run(ops.list_tariffs(location_id))

    def tariff(self, tariff_id: int) -> m.Tariff:
        """``GET /catalog/tariffs/{id}``."""
        return self._c._run(ops.get_tariff(tariff_id))

    def os_images(self, *, tariff_id: Optional[int] = None) -> ItemList[m.OsImage]:
        """``GET /catalog/os`` — образы ОС; с ``tariff_id`` без запрещённых тарифом."""
        return self._c._run(ops.list_os_images(tariff_id))

    def locations(self) -> ItemList[m.Location]:
        """``GET /catalog/locations``."""
        return self._c._run(ops.list_locations())

    def zones(self) -> ItemList[m.Zone]:
        """``GET /catalog/zones`` — доменные зоны и цены."""
        return self._c._run(ops.list_zones())

    def quote(
        self,
        tariff_id: int,
        *,
        months: Optional[int] = None,
        hours: Optional[int] = None,
        billing_cycle: Optional[str] = None,
        promo_code: Optional[str] = None,
    ) -> m.Quote:
        """``GET /catalog/quote`` — цена заказа до его оформления (промокод не тратится)."""
        return self._c._run(ops.get_quote(tariff_id, months, hours, billing_cycle, promo_code))


# ---------------------------------------------------------------- Servers


class ServerActions(_Resource):
    def power(self, server_id: int, action: str) -> m.ActionResult:
        """``POST /servers/{id}/actions/power`` — ``start`` | ``stop`` | ``restart``."""
        return self._c._run(ops.power_server(server_id, action))

    def start(self, server_id: int) -> m.ActionResult:
        return self.power(server_id, "start")

    def stop(self, server_id: int) -> m.ActionResult:
        return self.power(server_id, "stop")

    def restart(self, server_id: int) -> m.ActionResult:
        return self.power(server_id, "restart")

    def reinstall(
        self, server_id: int, os: str, *, password: Any = NOT_GIVEN, ssh_key_ids: Any = NOT_GIVEN
    ) -> m.ReinstallResult:
        """``POST /servers/{id}/actions/reinstall`` — переустановка ОС, данные на диске уничтожаются."""
        return self._c._run(ops.reinstall_server(server_id, os, password, ssh_key_ids))

    def reset_password(self, server_id: int) -> m.ResetPasswordResult:
        """``POST /servers/{id}/actions/reset-password`` — новый root-пароль, показывается один раз."""
        return self._c._run(ops.reset_server_password(server_id))


class ServerIps(_Resource):
    def list(self, server_id: int) -> ItemList[m.Ip]:
        """``GET /servers/{id}/ips``."""
        return self._c._run(ops.list_server_ips(server_id))

    def quote(self, server_id: int) -> m.IpQuote:
        """``GET /servers/{id}/ips/quote`` — цена ещё одного IPv4."""
        return self._c._run(ops.get_server_ip_quote(server_id))

    def add(self, server_id: int, *, idempotency_key: Optional[str] = None) -> m.IpAdded:
        """``POST /servers/{id}/ips`` — купить дополнительный IPv4 (денежная ручка)."""
        return self._c._run(ops.add_server_ip(server_id, idempotency_key))

    def delete(self, server_id: int, ip_id: int) -> m.IpDeleted:
        """``DELETE /servers/{id}/ips/{ip_id}`` — освободить адрес, без возврата денег."""
        return self._c._run(ops.delete_server_ip(server_id, ip_id))

    def set_ptr(self, server_id: int, ip_id: int, ptr: Optional[str]) -> m.PtrRecord:
        """``PUT /servers/{id}/ips/{ip_id}/ptr`` — обратная запись DNS.

        Пустая строка или ``None`` снимают запись. Возвращает ``{id, ptr}``.
        """
        return self._c._run(ops.set_server_ip_ptr(server_id, ip_id, ptr))


class Orders(_Resource):
    def list(
        self, *, cursor: Optional[str] = None, limit: Optional[int] = None, status: Optional[str] = None
    ) -> Page[m.Order]:
        """``GET /orders`` — заказы серверов, новые первыми."""
        return self._c._run(ops.list_orders(cursor, limit, status))

    def list_all(self, *, limit: Optional[int] = None, status: Optional[str] = None) -> Iterator[m.Order]:
        return _iterate(self.list, limit=limit, status=status)

    def get(self, invoice_id: int) -> m.Order:
        """``GET /orders/{invoice_id}`` — состояние заказа после ``202 provisioning``."""
        return self._c._run(ops.get_order(invoice_id))

    def wait(self, invoice_id: int, *, timeout: float = 600.0, interval: float = 5.0) -> m.Order:
        """Опрашивать заказ, пока он не станет ``active`` или ``cancelled``
        (сорвавшийся заказ возвращает деньги и приходит как ``cancelled``).

        Бросает ``TimeoutError``, если за ``timeout`` секунд заказ не завершился;
        сам заказ при этом продолжает выполняться на стороне VDSok.
        """
        from . import _client

        deadline = _client._monotonic() + timeout
        while True:
            order = self.get(invoice_id)
            if order.is_terminal:
                return order
            if _client._monotonic() >= deadline:
                raise TimeoutError(f"order {invoice_id} is still {order.status} after {timeout}s")
            _client._sleep(interval)


class Servers(_Resource):
    def __init__(self, client: "Vdsok") -> None:
        super().__init__(client)
        self.actions = ServerActions(client)
        self.ips = ServerIps(client)
        self.orders = Orders(client)

    def list(
        self,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> Page[m.Server]:
        """``GET /servers`` — страница серверов; ``ip`` ищет по любому адресу."""
        return self._c._run(ops.list_servers(cursor, limit, status, ip))

    def list_all(
        self, *, limit: Optional[int] = None, status: Optional[str] = None, ip: Optional[str] = None
    ) -> Iterator[m.Server]:
        return _iterate(self.list, limit=limit, status=status, ip=ip)

    def create(
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
        """``POST /servers`` — заказать сервер (денежная ручка).

        ``201`` -> ``ServerCreated`` с сервером и одноразовым ``root_password``.
        ``202`` -> ``Order``: деньги списаны, но панель не ответила вовремя;
        дождаться результата можно через ``servers.orders.wait(order.invoice_id)``.
        Различать удобно по типу::

            created = client.servers.create(12, "ubuntu-24.04")
            if isinstance(created, Order):
                created = client.servers.orders.wait(created.invoice_id)
        """
        return self._c._run(
            ops.create_server(
                tariff_id, os, name, password, months, hours, billing_cycle, promo_code, ssh_key_ids, custom_fields, idempotency_key
            )
        )

    def get(self, server_id: int, *, include_live: bool = False) -> m.ServerDetail:
        """``GET /servers/{id}`` — детали с ``refund_quote``; ``include_live`` добавляет
        состояние из панели (дорогой вызов)."""
        return self._c._run(ops.get_server(server_id, include_live))

    def update(
        self, server_id: int, *, auto_renew: Any = NOT_GIVEN, name: Any = NOT_GIVEN, notes: Any = NOT_GIVEN
    ) -> m.Server:
        """``PATCH /servers/{id}`` — автопродление, имя, заметки (``notes=None`` очищает)."""
        return self._c._run(ops.update_server(server_id, auto_renew, name, notes))

    def delete(self, server_id: int, *, idempotency_key: Optional[str] = None) -> m.DeleteResult:
        """``DELETE /servers/{id}`` — удалить с возвратом за неиспользованные дни."""
        return self._c._run(ops.delete_server(server_id, idempotency_key))

    def status(self, server_id: int) -> m.ServerLiveStatus:
        """``GET /servers/{id}/status`` — живое состояние из панели."""
        return self._c._run(ops.get_server_status(server_id))

    def refund_quote(self, server_id: int) -> m.RefundQuote:
        """``GET /servers/{id}/refund-quote`` — сколько вернёт ``delete`` прямо сейчас."""
        return self._c._run(ops.get_server_refund_quote(server_id))

    def renew(
        self,
        server_id: int,
        *,
        months: Optional[int] = None,
        hours: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> m.RenewResult:
        """``POST /servers/{id}/renew`` — продлить с баланса (денежная ручка)."""
        return self._c._run(ops.renew_server(server_id, months, hours, idempotency_key))


# ---------------------------------------------------------------- Domains


class Domains(_Resource):
    def check_availability(self, name: str) -> m.AvailabilityResult:
        """``GET /domains/availability`` — свободно ли имя и почём."""
        return self._c._run(ops.check_domain_availability(name))

    def list(
        self, *, cursor: Optional[str] = None, limit: Optional[int] = None, status: Optional[str] = None
    ) -> Page[m.Domain]:
        """``GET /domains``."""
        return self._c._run(ops.list_domains(cursor, limit, status))

    def list_all(self, *, limit: Optional[int] = None, status: Optional[str] = None) -> Iterator[m.Domain]:
        return _iterate(self.list, limit=limit, status=status)

    def register(
        self,
        name: str,
        *,
        years: Any = NOT_GIVEN,
        nameservers: Any = NOT_GIVEN,
        privacy: Any = NOT_GIVEN,
        promo_code: Any = NOT_GIVEN,
        idempotency_key: Optional[str] = None,
    ) -> m.DomainOrderResult:
        """``POST /domains`` — зарегистрировать домен (денежная ручка)."""
        return self._c._run(
            ops.register_domain(name, years, nameservers, privacy, promo_code, idempotency_key)
        )

    def get(self, domain_id: int) -> m.Domain:
        """``GET /domains/{id}``."""
        return self._c._run(ops.get_domain(domain_id))

    def update(self, domain_id: int, *, auto_renew: Any = NOT_GIVEN, privacy: Any = NOT_GIVEN) -> m.Domain:
        """``PATCH /domains/{id}`` — автопродление и WHOIS-privacy."""
        return self._c._run(ops.update_domain(domain_id, auto_renew, privacy))

    def renew(self, domain_id: int, years: int, *, idempotency_key: Optional[str] = None) -> m.DomainRenewResult:
        """``POST /domains/{id}/renew`` — продлить на N лет (денежная ручка)."""
        return self._c._run(ops.renew_domain(domain_id, years, idempotency_key))

    def set_nameservers(self, domain_id: int, nameservers: Iterable[str]) -> m.Domain:
        """``PUT /domains/{id}/nameservers`` — заменить набор NS (2..4)."""
        return self._c._run(ops.set_domain_nameservers(domain_id, nameservers))

    def transfer(
        self,
        name: str,
        auth_code: str,
        *,
        nameservers: Any = NOT_GIVEN,
        idempotency_key: Optional[str] = None,
    ) -> m.DomainTransferResult:
        """``POST /domains/transfers`` — перенести домен от другого регистратора (денежная ручка)."""
        return self._c._run(ops.transfer_domain(name, auth_code, nameservers, idempotency_key))


# ---------------------------------------------------------------- SSH keys


class SshKeys(_Resource):
    def list(self) -> ItemList[m.SshKey]:
        """``GET /ssh-keys``."""
        return self._c._run(ops.list_ssh_keys())

    def create(self, name: str, public_key: str) -> m.SshKey:
        """``POST /ssh-keys`` — добавить публичный ключ в формате OpenSSH."""
        return self._c._run(ops.create_ssh_key(name, public_key))

    def delete(self, key_id: int) -> EmptyResult:
        """``DELETE /ssh-keys/{id}`` — уже установленные на серверы ключи не трогает."""
        return self._c._run(ops.delete_ssh_key(key_id))


# ---------------------------------------------------------------- Keys


class Keys(_Resource):
    def list(self) -> Page[m.ApiKey]:
        """``GET /keys`` — ключи аккаунта (секретов нет).

        Ответ — конверт страницы с ``next_cursor`` (сегодня всегда ``None``):
        когда у ручки появится настоящий курсор, SDK не начнёт молча терять
        ключи.
        """
        return self._c._run(ops.list_api_keys())

    def get(self, key_id: int) -> m.ApiKey:
        """``GET /keys/{id}``."""
        return self._c._run(ops.get_api_key(key_id))

    def revoke(self, key_id: int) -> m.ApiKeyRevoked:
        """``DELETE /keys/{id}`` — отозвать **вызывающий** ключ (kill switch).

        Чужие ключи отсюда отозвать нельзя, только в кабинете.
        """
        return self._c._run(ops.revoke_api_key(key_id))

    def revoke_current(self) -> m.ApiKeyRevoked:
        """Отозвать ключ, которым сделан запрос: ``GET /me`` за id, затем ``DELETE /keys/{id}``."""
        me = self._c.me()
        if me.key is None or me.key.id is None:
            raise RuntimeError("GET /me did not return the current key id")
        return self.revoke(me.key.id)


# ---------------------------------------------------------------- Webhooks


class WebhookDeliveries(_Resource):
    def list(
        self,
        webhook_id: int,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> Page[m.WebhookDelivery]:
        """``GET /webhooks/{id}/deliveries`` — журнал доставок."""
        return self._c._run(ops.list_webhook_deliveries(webhook_id, cursor, limit, status, event_type))

    def list_all(
        self,
        webhook_id: int,
        *,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> Iterator[m.WebhookDelivery]:
        return _iterate(self.list, webhook_id=webhook_id, limit=limit, status=status, event_type=event_type)

    def get(self, delivery_id: int) -> m.WebhookDeliveryWithPayload:
        """``GET /webhooks/deliveries/{id}`` — одна доставка вместе с ``payload``
        (единственная ручка, которая его отдаёт)."""
        return self._c._run(ops.get_webhook_delivery(delivery_id))

    def redeliver(self, delivery_id: int) -> m.WebhookRedelivery:
        """``POST /webhooks/deliveries/{id}/redeliver`` — поставить в очередь те же байты."""
        return self._c._run(ops.redeliver_webhook(delivery_id))


class Webhooks(_Resource):
    """Подписки на события. Проверка подписи входящих доставок —
    ``client.webhooks.verify(...)`` / ``construct_event(...)`` (они же в
    ``vdsok.webhooks``)."""

    verify = staticmethod(_webhooks.verify)
    construct_event = staticmethod(_webhooks.construct_event)
    sign = staticmethod(_webhooks.sign)

    def __init__(self, client: "Vdsok") -> None:
        super().__init__(client)
        self.deliveries = WebhookDeliveries(client)

    def list(self) -> Page[m.WebhookSubscription]:
        """``GET /webhooks`` — как и ``/keys``, конверт страницы с ``next_cursor``."""
        return self._c._run(ops.list_webhooks())

    def create(self, url: str, events: Iterable[str], *, description: Any = NOT_GIVEN) -> m.WebhookSubscriptionWithSecret:
        """``POST /webhooks`` — подписать URL; ``secret`` возвращается один раз."""
        return self._c._run(ops.create_webhook(url, events, description))

    def events(self) -> ItemList[m.WebhookEventDescriptor]:
        """``GET /webhooks/events`` — каталог типов событий."""
        return self._c._run(ops.list_webhook_events())

    def get(self, webhook_id: int) -> m.WebhookSubscription:
        """``GET /webhooks/{id}``."""
        return self._c._run(ops.get_webhook(webhook_id))

    def update(
        self,
        webhook_id: int,
        *,
        url: Any = NOT_GIVEN,
        events: Any = NOT_GIVEN,
        description: Any = NOT_GIVEN,
        active: Any = NOT_GIVEN,
    ) -> m.WebhookSubscription:
        """``PATCH /webhooks/{id}`` — URL, события, описание; ``active=True`` включает после авто-отключения."""
        return self._c._run(ops.update_webhook(webhook_id, url, events, description, active))

    def delete(self, webhook_id: int) -> m.WebhookDeleted:
        """``DELETE /webhooks/{id}`` — удалить подписку и журнал доставок."""
        return self._c._run(ops.delete_webhook(webhook_id))

    def rotate_secret(self, webhook_id: int) -> m.WebhookSecret:
        """``POST /webhooks/{id}/rotate-secret`` — новый секрет; старый перестаёт
        работать сразу. Возвращается только ``{id, secret}``."""
        return self._c._run(ops.rotate_webhook_secret(webhook_id))

    def test(self, webhook_id: int) -> m.WebhookTestResult:
        """``POST /webhooks/{id}/test`` — отправить ``ping`` и показать ответ приёмника."""
        return self._c._run(ops.test_webhook(webhook_id))
