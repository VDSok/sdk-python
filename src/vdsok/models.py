"""Модели ответов — один в один схемы ``components.schemas`` спецификации
``vdsok-client-api-v1.yaml``.

Правила:

* деньги (``Money``) -> ``Decimal``; даты (``Timestamp``) -> tz-aware ``datetime``;
* enum-поля остаются строками (``Literal`` только для подсказок IDE): API
  просит терпеть неизвестные значения, и падать на новом статусе нельзя;
* у всех полей есть default, чтобы объект собирался даже из частичного
  ответа — например, из ``data.object`` вебхука, где часть полей может быть
  опущена. Обязательность по спецификации гарантирует сервер, не SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from ._parsing import build
from ._types import ApiObject

__all__ = [
    "parse",
    "Scope",
    "BillingCycle",
    "Health",
    "ApiKey",
    "ApiKeyRevoked",
    "Me",
    "ClientGroup",
    "Account",
    "Balance",
    "Transaction",
    "TopupInfo",
    "TopupResult",
    "InvoiceItem",
    "Invoice",
    "PayInvoiceResult",
    "PaymentLink",
    "Resources",
    "PeriodPrice",
    "Location",
    "Tariff",
    "OsImage",
    "Zone",
    "Discount",
    "QuotePromo",
    "Quote",
    "ServerFlags",
    "ServerBilling",
    "ServerRef",
    "ServerResources",
    "Server",
    "MemoryUsage",
    "DiskUsage",
    "ServerLiveStatus",
    "RefundBreakdownItem",
    "RefundQuote",
    "ServerDetail",
    "ServerCreated",
    "DeleteResult",
    "RenewResult",
    "ActionResult",
    "ReinstallResult",
    "ResetPasswordResult",
    "Order",
    "Ip",
    "IpQuote",
    "IpAdded",
    "IpDeleted",
    "PtrRecord",
    "SshKey",
    "Domain",
    "AvailabilityResult",
    "DomainOrderResult",
    "DomainRenewResult",
    "DomainTransferResult",
    "WebhookEventDescriptor",
    "WebhookSubscription",
    "WebhookSubscriptionWithSecret",
    "WebhookSecret",
    "WebhookDeleted",
    "WebhookEventData",
    "WebhookEvent",
    "WebhookDelivery",
    "WebhookDeliveryWithPayload",
    "WebhookRedelivery",
    "WebhookTestResult",
]

Scope = Literal[
    "account:read",
    "balance:read",
    "balance:topup",
    "invoices:read",
    "invoices:pay",
    "servers:read",
    "servers:manage",
    "servers:order",
    "servers:delete",
    "domains:read",
    "domains:manage",
    "domains:order",
    "keys:read",
    "webhooks:manage",
]
BillingCycle = Literal["monthly", "hourly"]
InvoiceStatus = Literal["not_paid", "paid", "cancelled", "refunded"]
InvoiceType = Literal[
    "topup",
    "vds_purchase",
    "vds_renewal",
    "ip_purchase",
    "domain_registration",
    "domain_renewal",
    "domain_transfer",
    "other",
]
ServerStatus = Literal["active", "stopped", "suspended", "pending_cancel", "cancelled", "terminated"]
OrderStatus = Literal[
    "provisioning",
    "invoice_created",
    "processing",
    "active",
    "cancelled",
]
DomainStatus = Literal["pending", "active", "expired", "transfer_pending", "cancelled"]
PowerAction = Literal["start", "stop", "restart"]
WebhookEventType = Literal[
    "server.created",
    "server.suspended",
    "server.unsuspended",
    "server.terminated",
    "server.reinstalled",
    "invoice.created",
    "invoice.paid",
    "invoice.overdue",
    "balance.low",
    "domain.registered",
    "domain.expiring",
    "domain.renewed",
    "key.created",
    "key.revoked",
    "ping",
]
DeliveryStatus = Literal["pending", "delivered", "dead"]


def parse(model: type, data: Dict[str, Any]):
    """Собрать модель из словаря, например ``parse(Server, event.data.object)``."""
    return build(model, data)


# ---------------------------------------------------------------- meta


@dataclass
class Health(ApiObject):
    """``GET /health``: поле версии называется ``version`` (а в ``/me`` — ``api_version``)."""

    status: str = "ok"  # ok | disabled
    time: Optional[datetime] = None
    version: str = "1"


@dataclass
class ApiKey(ApiObject):
    """Ключ API. Секрет никогда не возвращается; ``hint`` — префикс + 4 последних символа.

    ``rate_per_minute`` / ``rate_expensive_per_minute`` равны ``None``, когда
    персонального потолка нет и ключ живёт на дефолте аккаунта; действующий
    лимит виден в ``result.meta.rate_limit``.
    """

    id: Optional[int] = None
    name: Optional[str] = None
    hint: Optional[str] = None
    mode: Optional[str] = None  # live | test
    scopes: List[str] = field(default_factory=list)
    ip_allowlist: List[str] = field(default_factory=list)
    rate_per_minute: Optional[int] = None
    rate_expensive_per_minute: Optional[int] = None
    not_before: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    active: Optional[bool] = None
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None
    last_used_at: Optional[datetime] = None
    last_used_ip: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class ApiKeyRevoked(ApiObject):
    """Ответ ``DELETE /keys/{id}``: статус плюс сам ключ после отзыва."""

    status: Optional[str] = None  # revoked
    key: Optional[ApiKey] = None


@dataclass
class Me(ApiObject):
    key: Optional[ApiKey] = None
    account_id: Optional[int] = None
    livemode: Optional[bool] = None
    scopes: List[str] = field(default_factory=list)
    available_scopes: List[str] = field(default_factory=list)
    sandbox_enabled: Optional[bool] = None
    api_version: Optional[str] = None


# ---------------------------------------------------------------- account


@dataclass
class ClientGroup(ApiObject):
    id: Optional[int] = None
    name: Optional[str] = None
    discount_percent: Optional[float] = None


@dataclass
class Account(ApiObject):
    id: Optional[int] = None
    login: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    company: Optional[str] = None
    currency: Optional[str] = None
    group: Optional[ClientGroup] = None
    loyalty_discount_percent: Optional[float] = None
    email_verified: Optional[bool] = None
    two_factor_enabled: Optional[bool] = None
    created_at: Optional[datetime] = None


@dataclass
class Balance(ApiObject):
    balance: Optional[Decimal] = None
    currency: Optional[str] = None
    upcoming_7d: Optional[Decimal] = None
    upcoming_30d: Optional[Decimal] = None
    low_balance: Optional[bool] = None
    auto_renew_total_monthly: Optional[Decimal] = None


@dataclass
class Transaction(ApiObject):
    id: Optional[int] = None
    direction: Optional[str] = None  # credit | debit
    amount: Optional[Decimal] = None  # абсолютное значение, знак — в direction
    currency: Optional[str] = None
    type: Optional[str] = None  # topup | payment | refund | bonus | referral | adjustment | other
    gateway: Optional[str] = None
    description: Optional[str] = None
    invoice_id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class TopupInfo(ApiObject):
    """Лимиты пополнения и коды включённых шлюзов.

    `gateways` — плоский список строк, а не объектов: ручка отдаёт
    `["cryptobot", …]`. Раньше здесь были `min_amount`/`max_amount` и
    `TopupGateway`, и `info.gateways[0].code` падал на строке, а лимиты
    молча приезжали None.
    """

    currency: Optional[str] = None
    min: Optional[Decimal] = None
    max: Optional[Decimal] = None
    first_topup_bonus_percent: Optional[float] = None
    first_topup_eligible: Optional[bool] = None
    gateways: List[str] = field(default_factory=list)


@dataclass
class TopupResult(ApiObject):
    invoice_id: Optional[int] = None
    payment_url: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    gateway: Optional[str] = None


# ---------------------------------------------------------------- invoices


@dataclass
class InvoiceItem(ApiObject):
    description: Optional[str] = None
    amount: Optional[Decimal] = None
    server_id: Optional[int] = None
    domain_id: Optional[int] = None


@dataclass
class Invoice(ApiObject):
    id: Optional[int] = None
    status: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    gateway: Optional[str] = None
    created_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    items: List[InvoiceItem] = field(default_factory=list)
    pdf_url: Optional[str] = None


@dataclass
class PayInvoiceResult(ApiObject):
    invoice_id: Optional[int] = None
    # Единственный успешный исход — "paid" (200): провижининг заказанной
    # услуги идёт фоном и на ответ не влияет.
    status: Optional[str] = None  # paid
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    balance_after: Optional[Decimal] = None


@dataclass
class PaymentLink(ApiObject):
    invoice_id: Optional[int] = None
    payment_url: Optional[str] = None
    gateway: Optional[str] = None


# ---------------------------------------------------------------- catalog


@dataclass
class Resources(ApiObject):
    cpu_cores: Optional[int] = None
    ram_mb: Optional[int] = None
    disk_gb: Optional[int] = None
    bandwidth_tb: Optional[float] = None  # None = безлимит
    port_mbps: Optional[int] = None


@dataclass
class PeriodPrice(ApiObject):
    months: Optional[int] = None
    discount_percent: Optional[float] = None
    total: Optional[Decimal] = None


@dataclass
class Location(ApiObject):
    id: Optional[int] = None
    code: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    in_stock: Optional[bool] = None


@dataclass
class Tariff(ApiObject):
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[Location] = None
    resources: Optional[Resources] = None
    price_monthly: Optional[Decimal] = None  # уже с групповой скидкой вызывающего
    list_price_monthly: Optional[Decimal] = None
    price_hourly: Optional[Decimal] = None
    currency: Optional[str] = None
    periods: List[PeriodPrice] = field(default_factory=list)
    hourly_available: Optional[bool] = None
    in_stock: Optional[bool] = None
    non_refundable: Optional[bool] = None
    excluded_os: List[str] = field(default_factory=list)
    extra_ip_price_monthly: Optional[Decimal] = None
    max_extra_ips: Optional[int] = None


@dataclass
class OsImage(ApiObject):
    slug: Optional[str] = None
    name: Optional[str] = None
    family: Optional[str] = None  # linux | windows | other
    version: Optional[str] = None
    supports_ssh_keys: Optional[bool] = None
    min_disk_gb: Optional[int] = None


@dataclass
class Zone(ApiObject):
    tld: Optional[str] = None
    price_register: Optional[Decimal] = None
    price_renew: Optional[Decimal] = None
    price_transfer: Optional[Decimal] = None
    currency: Optional[str] = None
    min_years: Optional[int] = None
    max_years: Optional[int] = None
    privacy_supported: Optional[bool] = None
    transfer_supported: Optional[bool] = None


@dataclass
class Discount(ApiObject):
    type: Optional[str] = None  # group | loyalty | volume | period | promo
    percent: Optional[float] = None
    amount: Optional[Decimal] = None


@dataclass
class QuotePromo(ApiObject):
    code: Optional[str] = None
    valid: Optional[bool] = None
    message: Optional[str] = None


@dataclass
class Quote(ApiObject):
    tariff_id: Optional[int] = None
    billing_cycle: Optional[str] = None
    months: Optional[int] = None
    hours: Optional[int] = None
    base_amount: Optional[Decimal] = None
    discounts: List[Discount] = field(default_factory=list)
    total: Optional[Decimal] = None
    currency: Optional[str] = None
    promo: Optional[QuotePromo] = None
    balance: Optional[Decimal] = None
    balance_sufficient: Optional[bool] = None
    shortfall: Optional[Decimal] = None


# ---------------------------------------------------------------- servers


@dataclass
class ServerFlags(ApiObject):
    blocked: Optional[bool] = None
    suspended: Optional[bool] = None
    expired: Optional[bool] = None
    pending_cancel: Optional[bool] = None
    protected_until: Optional[datetime] = None
    is_test: Optional[bool] = None
    # Услуга-история с WHMCS: VM в панели нет, живой статус для неё — 409.
    synthetic: Optional[bool] = None


@dataclass
class ServerBilling(ApiObject):
    cycle: Optional[str] = None  # monthly | hourly
    months: Optional[int] = None
    price_monthly: Optional[Decimal] = None
    recurring_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    next_due_at: Optional[datetime] = None
    auto_renew: Optional[bool] = None
    promo_code: Optional[str] = None
    extra_ips: Optional[int] = None


@dataclass
class ServerRef(ApiObject):
    id: Optional[int] = None
    name: Optional[str] = None


@dataclass
class ServerResources(ApiObject):
    """Ресурсы тарифа этого сервера. Это НЕ каталожный ``Resources``: имена и
    единицы другие — диск здесь в мегабайтах."""

    vcpu: Optional[int] = None
    ram_mb: Optional[int] = None
    disk_mb: Optional[int] = None


@dataclass
class Server(ApiObject):
    """Сервер. Паролей здесь не бывает — ``root_password`` только в ``ServerCreated``."""

    id: Optional[int] = None  # id панели (solusvm_id); sandbox-серверы >= 9000000000
    name: Optional[str] = None
    hostname: Optional[str] = None
    status: Optional[str] = None
    tariff: Optional[ServerRef] = None
    location: Optional[str] = None  # название локации, например "Amsterdam"
    os: Optional[str] = None  # slug ОС, каким его заказали
    primary_ip: Optional[str] = None
    ips: List[str] = field(default_factory=list)
    resources: Optional[ServerResources] = None
    flags: Optional[ServerFlags] = None
    billing: Optional[ServerBilling] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class MemoryUsage(ApiObject):
    used_mb: Optional[int] = None
    total_mb: Optional[int] = None


@dataclass
class DiskUsage(ApiObject):
    used_gb: Optional[float] = None
    total_gb: Optional[float] = None


@dataclass
class ServerLiveStatus(ApiObject):
    server_id: Optional[int] = None
    power: Optional[str] = None  # running | stopped | unknown
    cpu_percent: Optional[float] = None
    memory: Optional[MemoryUsage] = None
    disk: Optional[DiskUsage] = None
    uptime_seconds: Optional[int] = None
    checked_at: Optional[datetime] = None


@dataclass
class RefundBreakdownItem(ApiObject):
    invoice_id: Optional[int] = None
    amount: Optional[Decimal] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    days_left: Optional[int] = None  # целые сутки до конца окна, показание
    refund: Optional[Decimal] = None
    paid_at: Optional[datetime] = None


@dataclass
class RefundQuote(ApiObject):
    """``Σ breakdown[].refund == gross_amount``, а
    ``amount == gross_amount - referral_adjustment``."""

    server_id: Optional[int] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    refundable: Optional[bool] = None
    # promo_tariff | blocked | service_state | unpaid | no_payment_record |
    # hourly | consumed | currency_mismatch | unavailable
    excluded_reason: Optional[str] = None
    days_left: Optional[float] = None
    gross_amount: Optional[Decimal] = None
    referral_adjustment: Optional[Decimal] = None
    note: Optional[str] = None
    breakdown: List[RefundBreakdownItem] = field(default_factory=list)
    computed_at: Optional[datetime] = None


@dataclass
class ServerDetail(Server):
    refund_quote: Optional[RefundQuote] = None
    live: Optional[ServerLiveStatus] = None  # только с include=live


@dataclass
class ServerCreated(ApiObject):
    server: Optional[Server] = None
    root_password: Optional[str] = None  # показывается один раз; в replay пустой
    invoice_id: Optional[int] = None  # в песочнице None: счёта не существует
    charged: Optional[Decimal] = None
    currency: Optional[str] = None
    balance_after: Optional[Decimal] = None
    order_url: Optional[str] = None


@dataclass
class DeleteResult(ApiObject):
    """``refund`` — сумма зачисления, ``refund_quote`` — её расшифровка."""

    server_id: Optional[int] = None
    status: Optional[str] = None  # cancelled
    refund: Optional[Decimal] = None
    currency: Optional[str] = None
    balance_after: Optional[Decimal] = None
    refund_quote: Optional[RefundQuote] = None


@dataclass
class RenewResult(ApiObject):
    server: Optional[Server] = None
    # None в песочнице и когда счёт не удалось найти — продление при этом
    # состоялось (сервис продления номер счёта не возвращает).
    invoice_id: Optional[int] = None
    charged: Optional[Decimal] = None
    currency: Optional[str] = None
    balance_after: Optional[Decimal] = None
    next_due_at: Optional[datetime] = None
    months: Optional[int] = None  # то из двух, чем продлевали
    hours: Optional[int] = None


@dataclass
class ActionResult(ApiObject):
    server_id: Optional[int] = None
    action: Optional[str] = None
    status: Optional[str] = None  # accepted | done
    message: Optional[str] = None


@dataclass
class ReinstallResult(ApiObject):
    server_id: Optional[int] = None
    status: Optional[str] = None  # reinstalling
    os: Optional[str] = None
    root_password: Optional[str] = None  # только если пароль сгенерировал VDSok


@dataclass
class ResetPasswordResult(ApiObject):
    server_id: Optional[int] = None
    password: Optional[str] = None


# ---------------------------------------------------------------- orders


@dataclass
class Order(ApiObject):
    invoice_id: Optional[int] = None
    # provisioning | invoice_created | processing | active | cancelled
    status: Optional[str] = None
    server_id: Optional[int] = None
    server_name: Optional[str] = None  # только в ответах /orders
    tariff_name: Optional[str] = None
    tariff_id: Optional[int] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    order_url: Optional[str] = None
    failure_reason: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        # `failed` API сегодня не отдаёт (сорвавшийся заказ возвращает деньги
        # и становится `cancelled`), но терпеть неизвестный статус дешевле,
        # чем вечно опрашивать заказ, который уже никуда не двинется.
        return self.status in ("active", "cancelled", "failed")


# ---------------------------------------------------------------- ips


@dataclass
class Ip(ApiObject):
    id: Optional[int] = None
    address: Optional[str] = None
    version: Optional[int] = None  # 4 | 6
    primary: Optional[bool] = None
    ptr: Optional[str] = None
    gateway: Optional[str] = None
    netmask: Optional[str] = None
    price_monthly: Optional[Decimal] = None  # 0.00 у основного адреса
    added_at: Optional[datetime] = None


@dataclass
class IpQuote(ApiObject):
    server_id: Optional[int] = None
    price_monthly: Optional[Decimal] = None
    prorated_now: Optional[Decimal] = None
    currency: Optional[str] = None
    next_due_at: Optional[datetime] = None
    extra_ips: Optional[int] = None
    max_extra_ips: Optional[int] = None
    balance_sufficient: Optional[bool] = None


@dataclass
class IpAdded(ApiObject):
    """Самого адреса здесь нет: панель выдаёт его асинхронно, читайте
    ``client.server_ips.list(server_id)``."""

    success: Optional[bool] = None
    server_id: Optional[int] = None
    charged: Optional[Decimal] = None
    currency: Optional[str] = None
    days: Optional[int] = None


@dataclass
class IpDeleted(ApiObject):
    status: Optional[str] = None  # deleted
    server_id: Optional[int] = None
    ip_id: Optional[int] = None


@dataclass
class PtrRecord(ApiObject):
    """Ответ ``PUT /servers/{id}/ips/{ip_id}/ptr`` — два поля, а не карточка
    адреса: остального панель в этот момент ещё не знает."""

    id: Optional[int] = None
    ptr: Optional[str] = None  # None, если запись снята


# ---------------------------------------------------------------- ssh keys


@dataclass
class SshKey(ApiObject):
    id: Optional[int] = None
    name: Optional[str] = None
    fingerprint: Optional[str] = None
    type: Optional[str] = None  # ssh-ed25519 | ssh-rsa | ecdsa-sha2-nistp256/384/521
    public_key: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------- domains


@dataclass
class Domain(ApiObject):
    id: Optional[int] = None
    name: Optional[str] = None
    tld: Optional[str] = None
    status: Optional[str] = None
    registered_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    auto_renew: Optional[bool] = None
    privacy: Optional[bool] = None
    nameservers: List[str] = field(default_factory=list)
    locked: Optional[bool] = None
    blocked: Optional[bool] = None
    price_renew: Optional[Decimal] = None
    currency: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class AvailabilityResult(ApiObject):
    name: Optional[str] = None
    available: Optional[bool] = None
    reason: Optional[str] = None  # taken | premium | reserved | invalid | unsupported_tld
    premium: Optional[bool] = None
    price_register: Optional[Decimal] = None
    price_renew: Optional[Decimal] = None
    currency: Optional[str] = None
    min_years: Optional[int] = None


@dataclass
class DomainOrderResult(ApiObject):
    """``POST /domains``. ``domain`` — ИМЯ домена строкой, а не объект:
    записи домена на ветке ``pending`` ещё не существует."""

    status: Optional[str] = None  # registered | pending
    domain: Optional[str] = None
    domain_id: Optional[int] = None
    zone: Optional[str] = None
    years: Optional[int] = None
    charged: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    promo_code: Optional[str] = None
    currency: Optional[str] = None
    expires_at: Optional[datetime] = None
    message: Optional[str] = None


@dataclass
class DomainRenewResult(ApiObject):
    status: Optional[str] = None  # renewed | pending_sync | pending
    domain: Optional[str] = None
    domain_id: Optional[int] = None
    years: Optional[int] = None  # добавлено этим вызовом
    total_years: Optional[int] = None  # оплаченный период после продления
    charged: Optional[Decimal] = None
    currency: Optional[str] = None
    balance_after: Optional[Decimal] = None
    expires_at: Optional[datetime] = None
    message: Optional[str] = None


@dataclass
class DomainTransferResult(ApiObject):
    status: Optional[str] = None  # pending_transfer | pending
    domain: Optional[str] = None
    domain_id: Optional[int] = None
    charged: Optional[Decimal] = None
    currency: Optional[str] = None
    message: Optional[str] = None


# ---------------------------------------------------------------- webhooks


@dataclass
class WebhookEventDescriptor(ApiObject):
    """``GET /webhooks/events``: только тип и короткое описание."""

    type: Optional[str] = None
    description: Optional[str] = None


@dataclass
class WebhookSubscription(ApiObject):
    id: Optional[int] = None
    url: Optional[str] = None
    events: List[str] = field(default_factory=list)  # типы событий или "*"
    description: Optional[str] = None
    active: Optional[bool] = None
    failures_in_row: Optional[int] = None
    disabled_at: Optional[datetime] = None
    # Свободный текст воркера, например "20 failures in a row: ...".
    disabled_reason: Optional[str] = None
    last_delivery_at: Optional[datetime] = None
    last_status: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class WebhookSubscriptionWithSecret(WebhookSubscription):
    secret: Optional[str] = None  # whsec_..., показывается один раз


@dataclass
class WebhookSecret(ApiObject):
    """Ответ ``POST /webhooks/{id}/rotate-secret``: только id и новый секрет."""

    id: Optional[int] = None
    secret: Optional[str] = None  # whsec_..., показывается один раз


@dataclass
class WebhookDeleted(ApiObject):
    """Ответ ``DELETE /webhooks/{id}``."""

    status: Optional[str] = None  # deleted
    id: Optional[int] = None


@dataclass
class WebhookEventData(ApiObject):
    """``object`` — полный снимок объекта в форме REST-ответа (словарь; при
    необходимости ``parse(Server, event.data.object)``), ``previous`` —
    изменившиеся поля или None."""

    object: Dict[str, Any] = field(default_factory=dict)
    previous: Optional[Dict[str, Any]] = None


@dataclass
class WebhookEvent(ApiObject):
    id: Optional[str] = None
    type: Optional[str] = None
    created_at: Optional[datetime] = None
    livemode: Optional[bool] = None
    account_id: Optional[int] = None
    api_version: Optional[str] = None
    data: Optional[WebhookEventData] = None
    resource: Optional[str] = None


@dataclass
class WebhookDelivery(ApiObject):
    """Строка журнала доставок.

    Отдельного ``status`` API не отдаёт: ``dead`` — попыток больше не будет,
    ``delivered_at`` — доставлено, иначе доставка ждёт ``next_attempt_at``.
    Фильтр ``?status=delivered|pending|dead`` у списка при этом есть.
    """

    id: Optional[int] = None
    subscription_id: Optional[int] = None
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    attempts: Optional[int] = None
    next_attempt_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    dead: Optional[bool] = None
    last_status: Optional[int] = None
    last_error: Optional[str] = None
    last_response: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class WebhookDeliveryWithPayload(WebhookDelivery):
    """``GET /webhooks/deliveries/{id}`` — единственное место, где есть ``payload``."""

    payload: Optional[WebhookEvent] = None


@dataclass
class WebhookRedelivery(ApiObject):
    """Ответ ``POST /webhooks/deliveries/{id}/redeliver`` (202)."""

    status: Optional[str] = None  # queued
    delivery: Optional[WebhookDelivery] = None


@dataclass
class WebhookTestResult(ApiObject):
    """Ответ ``POST /webhooks/{id}/test``: строка журнала плюс исход попытки."""

    delivery: Optional[WebhookDelivery] = None
    ok: Optional[bool] = None
    status: Optional[int] = None
    latency_ms: Optional[int] = None
    detail: Optional[str] = None
