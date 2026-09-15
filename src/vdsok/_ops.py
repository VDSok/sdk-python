"""Таблица операций API v1 — единственное место, где записаны метод, путь,
параметры, тело и модель ответа каждой ручки.

Синхронные и асинхронные ресурсы (``_resources.py`` / ``_async_resources.py``)
не знают про HTTP: они лишь собирают ``Op`` через функции отсюда и отдают его
клиенту. Так у двух клиентов физически не может разойтись ни путь, ни имя
поля в теле — и тест паритета сверяет оба набора методов с этой таблицей.

Имена функций совпадают с ``operationId`` спецификации
(``docs/openapi/vdsok-client-api-v1.yaml``), чтобы grep по спеке находил код.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, Mapping, Optional, Union

from ._parsing import format_money
from ._types import NOT_GIVEN
from . import models as m

# Виды результата: как клиент превращает тело ответа в объект.
KIND_OBJECT = "object"  # одна модель
KIND_LIST = "list"  # {"data": [...]} без пагинации -> ItemList
KIND_PAGE = "page"  # {"data": [...], "next_cursor": ...} -> Page
KIND_BINARY = "binary"  # PDF -> BinaryResult
KIND_EMPTY = "empty"  # 204 -> EmptyResult
KIND_RAW = "raw"  # словарь как есть (openapi.json)


@dataclass
class Op:
    """Описание одного HTTP-вызова к API."""

    method: str
    path: str
    params: Optional[Mapping[str, Any]] = None
    body: Optional[Mapping[str, Any]] = None
    model: Optional[type] = None
    # Ручки, у которых разные успешные статусы описаны РАЗНЫМИ схемами
    # (сегодня только POST /servers: 201 -> ServerCreated, 202 -> Order).
    # Без этой таблицы 202 разбирался бы как ServerCreated и отдавал объект,
    # которого API не присылает: server=None, charged=None, а настоящие поля
    # заказа были бы видны только через .raw.
    models_by_status: Optional[Mapping[int, type]] = None
    kind: str = KIND_OBJECT
    # ``x-idempotent: true`` в спецификации: ручка двигает деньги или трогает
    # внешние системы, заголовок Idempotency-Key обязателен. Клиент
    # генерирует его сам, если вызывающий не передал свой, и только такие
    # мутации разрешено повторять после 429/5xx.
    money: bool = False
    idempotency_key: Optional[str] = None
    # Ручки без авторизации (health, openapi.json) — ключ всё равно
    # отправляется, но его отсутствие не ошибка.
    auth: bool = True


MoneyLike = Union[Decimal, int, str, float]
TimestampLike = Union[datetime, str]


def _int_id(name: str, value: Any) -> int:
    """Идентификаторы в путях — только положительные целые: строка с пробелом
    или ``None`` дали бы 404 c невнятным сообщением вместо ошибки на клиенте."""
    if isinstance(value, bool) or not isinstance(value, int):
        try:
            value = int(str(value).strip())
        except (TypeError, ValueError):
            raise TypeError(f"{name} must be a positive integer, got {value!r}") from None
    if value < 1:
        raise ValueError(f"{name} must be >= 1, got {value}")
    return value


def _paging(cursor: Optional[str], limit: Optional[int], **extra: Any) -> Dict[str, Any]:
    if limit is not None and not 1 <= int(limit) <= 100:
        raise ValueError("limit must be between 1 and 100")
    params: Dict[str, Any] = {"cursor": cursor, "limit": limit}
    params.update(extra)
    return params


def _ids(values: Any) -> Any:
    if values is NOT_GIVEN or values is None:
        return values
    return [_int_id("ssh_key_id", v) for v in values]


# ---------------------------------------------------------------- Meta


def get_health() -> Op:
    return Op("GET", "/health", model=m.Health, auth=False)


def get_openapi() -> Op:
    return Op("GET", "/openapi.json", kind=KIND_RAW, auth=False)


def get_me() -> Op:
    return Op("GET", "/me", model=m.Me)


# ---------------------------------------------------------------- Account


def get_account() -> Op:
    return Op("GET", "/account", model=m.Account)


def get_balance() -> Op:
    return Op("GET", "/balance", model=m.Balance)


def list_transactions(
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
    direction: Optional[str] = None,
    since: Optional[TimestampLike] = None,
    until: Optional[TimestampLike] = None,
) -> Op:
    return Op(
        "GET",
        "/transactions",
        params=_paging(cursor, limit, direction=direction, since=since, until=until),
        model=m.Transaction,
        kind=KIND_PAGE,
    )


def get_topup_info() -> Op:
    return Op("GET", "/balance/topup-info", model=m.TopupInfo)


def create_topup(
    amount: MoneyLike,
    gateway: str,
    idempotency_key: Optional[str] = None,
) -> Op:
    # Только amount и gateway: api_v1/routes/balance.py:197 отвергает любое
    # другое поле 400-й ошибкой, так что «на всякий случай» отправить
    # return_url значило бы гарантированно провалить пополнение.
    return Op(
        "POST",
        "/balance/topup",
        body={"amount": format_money(amount), "gateway": gateway},
        model=m.TopupResult,
        money=True,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------- Invoices


def list_invoices(
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
    status: Optional[str] = None,
    type: Optional[str] = None,
) -> Op:
    return Op(
        "GET",
        "/invoices",
        params=_paging(cursor, limit, status=status, type=type),
        model=m.Invoice,
        kind=KIND_PAGE,
    )


def get_invoice(invoice_id: int) -> Op:
    return Op("GET", f"/invoices/{_int_id('invoice_id', invoice_id)}", model=m.Invoice)


def get_invoice_pdf(invoice_id: int) -> Op:
    return Op("GET", f"/invoices/{_int_id('invoice_id', invoice_id)}/pdf", kind=KIND_BINARY)


def pay_invoice(invoice_id: int, idempotency_key: Optional[str] = None) -> Op:
    return Op(
        "POST",
        f"/invoices/{_int_id('invoice_id', invoice_id)}/pay",
        model=m.PayInvoiceResult,
        money=True,
        idempotency_key=idempotency_key,
    )


def create_invoice_payment_link(invoice_id: int, gateway: Any = NOT_GIVEN) -> Op:
    # Единственное поле тела (api_v1/routes/invoices.py:281); без него берётся
    # шлюз, уже записанный в счёте.
    return Op(
        "POST",
        f"/invoices/{_int_id('invoice_id', invoice_id)}/payment-link",
        body={"gateway": gateway},
        model=m.PaymentLink,
    )


# ---------------------------------------------------------------- Catalog


def list_tariffs(location_id: Optional[int] = None) -> Op:
    return Op("GET", "/catalog/tariffs", params={"location_id": location_id}, model=m.Tariff, kind=KIND_LIST)


def get_tariff(tariff_id: int) -> Op:
    return Op("GET", f"/catalog/tariffs/{_int_id('tariff_id', tariff_id)}", model=m.Tariff)


def list_os_images(tariff_id: Optional[int] = None) -> Op:
    return Op("GET", "/catalog/os", params={"tariff_id": tariff_id}, model=m.OsImage, kind=KIND_LIST)


def list_locations() -> Op:
    return Op("GET", "/catalog/locations", model=m.Location, kind=KIND_LIST)


def list_zones() -> Op:
    return Op("GET", "/catalog/zones", model=m.Zone, kind=KIND_LIST)


def get_quote(
    tariff_id: int,
    months: Optional[int] = None,
    hours: Optional[int] = None,
    billing_cycle: Optional[str] = None,
    promo_code: Optional[str] = None,
) -> Op:
    if months is not None and hours is not None:
        raise ValueError("give either months or hours, not both")
    return Op(
        "GET",
        "/catalog/quote",
        params={
            "tariff_id": _int_id("tariff_id", tariff_id),
            "months": months,
            "hours": hours,
            "billing_cycle": billing_cycle,
            "promo_code": promo_code,
        },
        model=m.Quote,
    )


# ---------------------------------------------------------------- Servers


def list_servers(
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
    status: Optional[str] = None,
    ip: Optional[str] = None,
) -> Op:
    return Op(
        "GET",
        "/servers",
        params=_paging(cursor, limit, status=status, ip=ip),
        model=m.Server,
        kind=KIND_PAGE,
    )


def create_server(
    tariff_id: int,
    os: str,
    name: Any = NOT_GIVEN,
    password: Any = NOT_GIVEN,
    months: Any = NOT_GIVEN,
    hours: Any = NOT_GIVEN,
    billing_cycle: Any = NOT_GIVEN,
    promo_code: Any = NOT_GIVEN,
    ssh_key_ids: Any = NOT_GIVEN,
    custom_fields: Any = NOT_GIVEN,
    idempotency_key: Optional[str] = None,
) -> Op:
    if months is not NOT_GIVEN and hours is not NOT_GIVEN:
        raise ValueError("give either months or hours, not both")
    return Op(
        "POST",
        "/servers",
        body={
            "tariff_id": _int_id("tariff_id", tariff_id),
            "os": os,
            "name": name,
            "password": password,
            "months": months,
            "hours": hours,
            "billing_cycle": billing_cycle,
            "promo_code": promo_code,
            "ssh_key_ids": _ids(ssh_key_ids),
            "custom_fields": custom_fields,
        },
        model=m.ServerCreated,
        # 202 «panel timed out» описан в спеке схемой Order, а не ServerCreated:
        # деньги списаны, но сервера ещё нет — вызывающему нужны invoice_id,
        # status и order_url, чтобы дождаться заказа через orders.wait().
        models_by_status={202: m.Order},
        money=True,
        idempotency_key=idempotency_key,
    )


def get_server(server_id: int, include_live: bool = False) -> Op:
    return Op(
        "GET",
        f"/servers/{_int_id('server_id', server_id)}",
        params={"include": "live" if include_live else None},
        model=m.ServerDetail,
    )


def update_server(
    server_id: int,
    auto_renew: Any = NOT_GIVEN,
    name: Any = NOT_GIVEN,
    notes: Any = NOT_GIVEN,
) -> Op:
    body = {"auto_renew": auto_renew, "name": name, "notes": notes}
    if all(v is NOT_GIVEN for v in body.values()):
        raise ValueError("update_server needs at least one of auto_renew, name, notes")
    return Op("PATCH", f"/servers/{_int_id('server_id', server_id)}", body=body, model=m.Server)


def delete_server(server_id: int, idempotency_key: Optional[str] = None) -> Op:
    return Op(
        "DELETE",
        f"/servers/{_int_id('server_id', server_id)}",
        model=m.DeleteResult,
        money=True,
        idempotency_key=idempotency_key,
    )


def get_server_status(server_id: int) -> Op:
    return Op("GET", f"/servers/{_int_id('server_id', server_id)}/status", model=m.ServerLiveStatus)


def get_server_refund_quote(server_id: int) -> Op:
    return Op("GET", f"/servers/{_int_id('server_id', server_id)}/refund-quote", model=m.RefundQuote)


def renew_server(
    server_id: int,
    months: Optional[int] = None,
    hours: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> Op:
    if (months is None) == (hours is None):
        raise ValueError("give exactly one of months or hours")
    body: Dict[str, Any] = {"months": months} if months is not None else {"hours": hours}
    return Op(
        "POST",
        f"/servers/{_int_id('server_id', server_id)}/renew",
        body=body,
        model=m.RenewResult,
        money=True,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------- Server actions


def power_server(server_id: int, action: str) -> Op:
    if action not in ("start", "stop", "restart"):
        raise ValueError("action must be one of start, stop, restart")
    return Op(
        "POST",
        f"/servers/{_int_id('server_id', server_id)}/actions/power",
        body={"action": action},
        model=m.ActionResult,
    )


def reinstall_server(
    server_id: int, os: str, password: Any = NOT_GIVEN, ssh_key_ids: Any = NOT_GIVEN
) -> Op:
    return Op(
        "POST",
        f"/servers/{_int_id('server_id', server_id)}/actions/reinstall",
        body={"os": os, "password": password, "ssh_key_ids": _ids(ssh_key_ids)},
        model=m.ReinstallResult,
    )


def reset_server_password(server_id: int) -> Op:
    return Op(
        "POST",
        f"/servers/{_int_id('server_id', server_id)}/actions/reset-password",
        model=m.ResetPasswordResult,
    )


# ---------------------------------------------------------------- Orders


def list_orders(cursor: Optional[str] = None, limit: Optional[int] = None, status: Optional[str] = None) -> Op:
    return Op("GET", "/orders", params=_paging(cursor, limit, status=status), model=m.Order, kind=KIND_PAGE)


def get_order(invoice_id: int) -> Op:
    return Op("GET", f"/orders/{_int_id('invoice_id', invoice_id)}", model=m.Order)


# ---------------------------------------------------------------- IPs


def list_server_ips(server_id: int) -> Op:
    return Op("GET", f"/servers/{_int_id('server_id', server_id)}/ips", model=m.Ip, kind=KIND_LIST)


def add_server_ip(server_id: int, idempotency_key: Optional[str] = None) -> Op:
    return Op(
        "POST",
        f"/servers/{_int_id('server_id', server_id)}/ips",
        model=m.IpAdded,
        money=True,
        idempotency_key=idempotency_key,
    )


def get_server_ip_quote(server_id: int) -> Op:
    return Op("GET", f"/servers/{_int_id('server_id', server_id)}/ips/quote", model=m.IpQuote)


def delete_server_ip(server_id: int, ip_id: int) -> Op:
    return Op(
        "DELETE",
        f"/servers/{_int_id('server_id', server_id)}/ips/{_int_id('ip_id', ip_id)}",
        model=m.IpDeleted,
    )


def set_server_ip_ptr(server_id: int, ip_id: int, ptr: Optional[str]) -> Op:
    # Поле тела зовётся `domain`: API принимает только его и отвечает 400 на
    # `ptr`. Пустая строка и None снимают запись. Ответ — {id, ptr}, а не
    # карточка адреса.
    return Op(
        "PUT",
        f"/servers/{_int_id('server_id', server_id)}/ips/{_int_id('ip_id', ip_id)}/ptr",
        body={"domain": ptr if ptr else ""},
        model=m.PtrRecord,
    )


# ---------------------------------------------------------------- SSH keys


def list_ssh_keys() -> Op:
    return Op("GET", "/ssh-keys", model=m.SshKey, kind=KIND_LIST)


def create_ssh_key(name: str, public_key: str) -> Op:
    return Op("POST", "/ssh-keys", body={"name": name, "public_key": public_key}, model=m.SshKey)


def delete_ssh_key(key_id: int) -> Op:
    return Op("DELETE", f"/ssh-keys/{_int_id('key_id', key_id)}", kind=KIND_EMPTY)


# ---------------------------------------------------------------- Domains


def check_domain_availability(name: str) -> Op:
    return Op("GET", "/domains/availability", params={"name": name}, model=m.AvailabilityResult)


def list_domains(cursor: Optional[str] = None, limit: Optional[int] = None, status: Optional[str] = None) -> Op:
    return Op("GET", "/domains", params=_paging(cursor, limit, status=status), model=m.Domain, kind=KIND_PAGE)


def register_domain(
    name: str,
    years: Any = NOT_GIVEN,
    nameservers: Any = NOT_GIVEN,
    privacy: Any = NOT_GIVEN,
    promo_code: Any = NOT_GIVEN,
    idempotency_key: Optional[str] = None,
) -> Op:
    # `auto_renew` регистрация не принимает (api_v1/routes/domains.py:36) —
    # флаг ставится отдельным PATCH /domains/{id} уже после покупки.
    return Op(
        "POST",
        "/domains",
        body={
            "name": name,
            "years": years,
            "nameservers": list(nameservers) if isinstance(nameservers, Iterable) and not isinstance(nameservers, str) else nameservers,
            "privacy": privacy,
            "promo_code": promo_code,
        },
        model=m.DomainOrderResult,
        money=True,
        idempotency_key=idempotency_key,
    )


def get_domain(domain_id: int) -> Op:
    return Op("GET", f"/domains/{_int_id('domain_id', domain_id)}", model=m.Domain)


def update_domain(domain_id: int, auto_renew: Any = NOT_GIVEN, privacy: Any = NOT_GIVEN) -> Op:
    body = {"auto_renew": auto_renew, "privacy": privacy}
    if all(v is NOT_GIVEN for v in body.values()):
        raise ValueError("update_domain needs at least one of auto_renew, privacy")
    return Op("PATCH", f"/domains/{_int_id('domain_id', domain_id)}", body=body, model=m.Domain)


def renew_domain(domain_id: int, years: int, idempotency_key: Optional[str] = None) -> Op:
    return Op(
        "POST",
        f"/domains/{_int_id('domain_id', domain_id)}/renew",
        body={"years": _int_id("years", years)},
        model=m.DomainRenewResult,
        money=True,
        idempotency_key=idempotency_key,
    )


def set_domain_nameservers(domain_id: int, nameservers: Iterable[str]) -> Op:
    ns = list(nameservers)
    # Ровно два: схема хранит ns1/ns2, и третий NS молча пропал бы
    # (api_v1/routes/domains.py:169-184 отвечает на такой список 400).
    if len(ns) != 2:
        raise ValueError("nameservers must contain exactly 2 entries")
    return Op(
        "PUT",
        f"/domains/{_int_id('domain_id', domain_id)}/nameservers",
        body={"nameservers": ns},
        model=m.Domain,
    )


def transfer_domain(
    name: str,
    auth_code: str,
    nameservers: Any = NOT_GIVEN,
    idempotency_key: Optional[str] = None,
) -> Op:
    # Тело трансфера — name, auth_code и (необязательно) ровно два NS
    # (api_v1/routes/domains.py:37). Ответ отличается от регистрации: у
    # трансфера нет ни периода, ни срока — только состояние заявки.
    return Op(
        "POST",
        "/domains/transfers",
        body={
            "name": name,
            "auth_code": auth_code,
            "nameservers": list(nameservers) if isinstance(nameservers, Iterable) and not isinstance(nameservers, str) else nameservers,
        },
        model=m.DomainTransferResult,
        money=True,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------- Keys


# Ответ — конверт страницы {"data": [...], "next_cursor": null}: курсора
# сегодня нет, но поле есть, и читать его страницей безопаснее, чем списком.
def list_api_keys() -> Op:
    return Op("GET", "/keys", model=m.ApiKey, kind=KIND_PAGE)


def get_api_key(key_id: int) -> Op:
    return Op("GET", f"/keys/{_int_id('key_id', key_id)}", model=m.ApiKey)


def revoke_api_key(key_id: int) -> Op:
    return Op("DELETE", f"/keys/{_int_id('key_id', key_id)}", model=m.ApiKeyRevoked)


# ---------------------------------------------------------------- Webhooks


def list_webhooks() -> Op:
    return Op("GET", "/webhooks", model=m.WebhookSubscription, kind=KIND_PAGE)


def create_webhook(url: str, events: Iterable[str], description: Any = NOT_GIVEN) -> Op:
    return Op(
        "POST",
        "/webhooks",
        body={"url": url, "events": list(events), "description": description},
        model=m.WebhookSubscriptionWithSecret,
    )


def list_webhook_events() -> Op:
    return Op("GET", "/webhooks/events", model=m.WebhookEventDescriptor, kind=KIND_LIST)


def get_webhook(webhook_id: int) -> Op:
    return Op("GET", f"/webhooks/{_int_id('webhook_id', webhook_id)}", model=m.WebhookSubscription)


def update_webhook(
    webhook_id: int,
    url: Any = NOT_GIVEN,
    events: Any = NOT_GIVEN,
    description: Any = NOT_GIVEN,
    active: Any = NOT_GIVEN,
) -> Op:
    body = {
        "url": url,
        "events": list(events) if events is not NOT_GIVEN and events is not None else events,
        "description": description,
        "active": active,
    }
    if all(v is NOT_GIVEN for v in body.values()):
        raise ValueError("update_webhook needs at least one field")
    return Op("PATCH", f"/webhooks/{_int_id('webhook_id', webhook_id)}", body=body, model=m.WebhookSubscription)


# 200 с телом {"status": "deleted", "id": ...}, а не пустой 204.
def delete_webhook(webhook_id: int) -> Op:
    return Op("DELETE", f"/webhooks/{_int_id('webhook_id', webhook_id)}", model=m.WebhookDeleted)


# Ротация отдаёт только {"id", "secret"} — подписка не меняется.
def rotate_webhook_secret(webhook_id: int) -> Op:
    return Op(
        "POST",
        f"/webhooks/{_int_id('webhook_id', webhook_id)}/rotate-secret",
        model=m.WebhookSecret,
    )


def test_webhook(webhook_id: int) -> Op:
    return Op("POST", f"/webhooks/{_int_id('webhook_id', webhook_id)}/test", model=m.WebhookTestResult)


def list_webhook_deliveries(
    webhook_id: int,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
    status: Optional[str] = None,
    event_type: Optional[str] = None,
) -> Op:
    return Op(
        "GET",
        f"/webhooks/{_int_id('webhook_id', webhook_id)}/deliveries",
        params=_paging(cursor, limit, status=status, event_type=event_type),
        model=m.WebhookDelivery,
        kind=KIND_PAGE,
    )


# Единственная ручка, возвращающая payload доставки.
def get_webhook_delivery(delivery_id: int) -> Op:
    return Op(
        "GET",
        f"/webhooks/deliveries/{_int_id('delivery_id', delivery_id)}",
        model=m.WebhookDeliveryWithPayload,
    )


def redeliver_webhook(delivery_id: int) -> Op:
    return Op(
        "POST",
        f"/webhooks/deliveries/{_int_id('delivery_id', delivery_id)}/redeliver",
        model=m.WebhookRedelivery,
    )
