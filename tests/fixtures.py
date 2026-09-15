"""Примеры ответов API — взяты из ``examples`` спецификации, чтобы тесты
проверяли разбор именно той формы, которую обещает документ."""

LOCATION = {"id": 1, "code": "nl-ams", "name": "Amsterdam", "country": "NL", "city": "Amsterdam"}
RESOURCES = {"cpu_cores": 1, "ram_mb": 1024, "disk_gb": 20, "bandwidth_tb": None, "port_mbps": 200}

# Карточка сервера отдаёт название локации и slug ОС строками, а ресурсы —
# срезом строки тарифа (диск в МЕГАБАЙТАХ), а не каталожными объектами.
SERVER = {
    "id": 2001,
    "name": "web-01",
    "hostname": "web-01",
    "status": "active",
    "tariff": {"id": 12, "name": "VDS-1"},
    "location": "Amsterdam",
    "os": "ubuntu-24.04",
    "primary_ip": "203.0.113.29",
    "ips": ["203.0.113.29", "2001:db8::29"],
    "resources": {"vcpu": 1, "ram_mb": 1024, "disk_mb": 20480},
    "flags": {
        "blocked": False,
        "suspended": False,
        "expired": False,
        "pending_cancel": False,
        "protected_until": None,
        "is_test": False,
        "synthetic": False,
    },
    "billing": {
        "cycle": "monthly",
        "months": 1,
        "price_monthly": "5.90",
        "recurring_amount": "6.90",
        "currency": "USD",
        "next_due_at": "2026-10-01T00:00:00Z",
        "auto_renew": True,
        "promo_code": None,
        "extra_ips": 1,
    },
    "notes": "",
    "created_at": "2026-03-01T12:00:00Z",
}

REFUND_QUOTE = {
    "server_id": 2001,
    "amount": "3.15",
    "currency": "USD",
    "refundable": True,
    "excluded_reason": None,
    "days_left": 16.0417,
    "gross_amount": "3.15",
    "referral_adjustment": "0.00",
    "note": "Возврат за 16.0 дн. по 1 счёт(ам)",
    "breakdown": [
        {
            "invoice_id": 10231,
            "amount": "5.90",
            "period_start": "2026-09-01T00:00:00Z",
            "period_end": "2026-10-01T00:00:00Z",
            "days_left": 16,
            "refund": "3.15",
            "paid_at": "2026-09-01T00:00:00Z",
        }
    ],
    "computed_at": "2026-09-15T10:00:00Z",
}

SERVER_DETAIL = dict(SERVER, refund_quote=REFUND_QUOTE, live=None)

LIVE_STATUS = {
    "server_id": 2001,
    "power": "running",
    "cpu_percent": 3.5,
    "memory": {"used_mb": 412, "total_mb": 1024},
    "disk": {"used_gb": 6.2, "total_gb": 20},
    "uptime_seconds": 864000,
    "checked_at": "2026-09-15T10:00:00Z",
}

BALANCE = {
    "balance": "42.15",
    "currency": "USD",
    "upcoming_7d": "5.90",
    "upcoming_30d": "23.60",
    "low_balance": False,
    "auto_renew_total_monthly": "23.60",
}

API_KEY = {
    "id": 3,
    "name": "ci-deploy",
    "hint": "vk_live_…7Qx2",
    "mode": "live",
    "scopes": ["servers:read", "servers:manage"],
    "ip_allowlist": [],
    "rate_per_minute": 120,
    "rate_expensive_per_minute": 20,
    "not_before": None,
    "expires_at": None,
    "active": True,
    "revoked_at": None,
    "revoked_reason": None,
    "last_used_at": "2026-09-15T09:59:00Z",
    "last_used_ip": "192.0.2.77",
    "created_at": "2026-09-01T12:00:00Z",
}

ME = {
    "key": API_KEY,
    "account_id": 57,
    "livemode": True,
    "scopes": ["servers:read", "servers:manage"],
    "available_scopes": ["account:read", "balance:read", "servers:read", "servers:manage"],
    "sandbox_enabled": True,
    "api_version": "1",
}

ACCOUNT = {
    "id": 57,
    "login": "kefisto",
    "email": "owner@example.com",
    "name": None,
    "company": None,
    "currency": "USD",
    "group": {"id": 2, "name": "Reseller", "discount_percent": 15},
    "loyalty_discount_percent": 0,
    "email_verified": True,
    "two_factor_enabled": True,
    "created_at": "2025-01-10T08:30:00Z",
}

TRANSACTION = {
    "id": 88012,
    "direction": "debit",
    "amount": "5.90",
    "currency": "USD",
    "type": "payment",
    "gateway": "balance",
    "description": "VDS #2001 renewal, 1 month",
    "invoice_id": 10231,
    "created_at": "2026-09-15T10:00:00Z",
}

INVOICE = {
    "id": 10231,
    "status": "paid",
    "type": "vds_renewal",
    "amount": "5.90",
    "currency": "USD",
    "description": "VDS #2001 renewal, 1 month",
    "gateway": "balance",
    "created_at": "2026-09-15T10:00:00Z",
    "due_at": "2026-09-20T00:00:00Z",
    "paid_at": "2026-09-15T10:00:01Z",
    "cancelled_at": None,
    "items": [{"description": "VDS #2001, 1 month", "amount": "5.90", "server_id": 2001, "domain_id": None}],
    "pdf_url": "/api/v1/invoices/10231/pdf",
}

TARIFF = {
    "id": 12,
    "name": "VDS-1",
    "description": None,
    "location": LOCATION,
    "resources": RESOURCES,
    "price_monthly": "5.02",
    "list_price_monthly": "5.90",
    "price_hourly": "0.0083",
    "currency": "USD",
    "periods": [{"months": 1, "discount_percent": 0, "total": "5.02"}, {"months": 12, "discount_percent": 10, "total": "54.22"}],
    "hourly_available": True,
    "in_stock": True,
    "non_refundable": False,
    "excluded_os": ["windows-2022"],
    "extra_ip_price_monthly": "1.00",
    "max_extra_ips": 5,
}

QUOTE = {
    "tariff_id": 12,
    "billing_cycle": "monthly",
    "months": 3,
    "hours": None,
    "base_amount": "17.70",
    "discounts": [{"type": "group", "percent": 15, "amount": "2.66"}, {"type": "period", "percent": 5, "amount": "0.75"}],
    "total": "14.29",
    "currency": "USD",
    "promo": None,
    "balance": "42.15",
    "balance_sufficient": True,
    "shortfall": "0.00",
}

ORDER = {
    "invoice_id": 10231,
    "status": "provisioning",
    "server_id": None,
    "tariff_id": 12,
    "amount": "5.90",
    "currency": "USD",
    "created_at": "2026-09-15T10:00:00Z",
    "updated_at": "2026-09-15T10:00:00Z",
    "order_url": "/api/v1/orders/10231",
    "failure_reason": None,
}

IP = {
    "id": 501,
    "address": "203.0.113.30",
    "version": 4,
    "primary": False,
    "ptr": "mail.example.com",
    "gateway": "203.0.113.1",
    "netmask": "255.255.255.0",
    "price_monthly": "1.00",
    "added_at": "2026-09-10T00:00:00Z",
}

SSH_KEY = {
    "id": 3,
    "name": "laptop",
    "fingerprint": "SHA256:Yk2Zt1HqzZ6cXyD9uQeL8XkFqf0F8Bq7oYy1o5G6Zso",
    "type": "ssh-ed25519",
    "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ9v... user@laptop",
    "created_at": "2026-02-01T09:00:00Z",
}

DOMAIN = {
    "id": 77,
    "name": "example.com",
    "tld": ".com",
    "status": "active",
    "registered_at": "2026-01-15T00:00:00Z",
    "expires_at": "2027-01-15T00:00:00Z",
    "auto_renew": True,
    "privacy": True,
    "nameservers": ["ns1.vdsok.guru", "ns2.vdsok.guru"],
    "locked": True,
    "blocked": False,
    "price_renew": "12.50",
    "currency": "USD",
    "created_at": "2026-01-15T10:00:00Z",
}

# Ответы денежных ручек доменов — плоские: объекта домена в них нет, потому
# что на ветке `pending` записи домена ещё не существует.
DOMAIN_REGISTERED = {
    "status": "registered",
    "domain": "example.com",
    "domain_id": 77,
    "zone": "com",
    "years": 2,
    "charged": "23.80",
    "discount": "0.00",
    "promo_code": None,
    "currency": "USD",
    "expires_at": "2028-01-15T00:00:00Z",
    "message": "Домен успешно зарегистрирован",
}

DOMAIN_RENEWED = {
    "status": "pending_sync",
    "domain": "example.com",
    "domain_id": 77,
    "years": 1,
    "total_years": 3,
    "charged": "12.50",
    "currency": "USD",
    "balance_after": "1.00",
    "expires_at": None,
    "message": None,
}

DOMAIN_TRANSFERRED = {
    "status": "pending_transfer",
    "domain": "example.org",
    "domain_id": 78,
    "charged": "12.50",
    "currency": "USD",
    "message": "Трансфер инициирован. Он может занять до 5–7 дней.",
}

WEBHOOK = {
    "id": 5,
    "url": "https://hooks.example.com/vdsok",
    "events": ["server.created", "invoice.paid"],
    "description": "billing sync",
    "active": True,
    "failures_in_row": 0,
    "disabled_at": None,
    "disabled_reason": None,
    "last_delivery_at": "2026-09-15T09:00:00Z",
    "last_status": 200,
    "created_at": "2026-09-01T12:00:00Z",
}

WEBHOOK_WITH_SECRET = dict(WEBHOOK, secret="whsec_" + "x" * 44)
WEBHOOK_SECRET = {"id": 5, "secret": "whsec_" + "y" * 44}

WEBHOOK_EVENT = {
    "id": "evt_01J7ZK3Q9X4R",
    "type": "server.suspended",
    "created_at": "2026-09-15T10:00:00Z",
    "livemode": True,
    "account_id": 57,
    "api_version": "1",
    "data": {"object": {"id": 2001, "name": "web-01", "status": "suspended"}, "previous": {"status": "active"}},
    "resource": "/api/v1/servers/2001",
}

DELIVERY = {
    "id": 900,
    "subscription_id": 5,
    "event_id": "evt_01J7ZK3Q9X4R",
    "event_type": "server.suspended",
    "attempts": 1,
    "next_attempt_at": "2026-09-15T10:00:00Z",
    "delivered_at": "2026-09-15T10:00:02Z",
    "dead": False,
    "last_status": 200,
    "last_error": None,
    "last_response": "ok",
    "created_at": "2026-09-15T10:00:00Z",
}

# `payload` отдаёт только GET /webhooks/deliveries/{id}.
DELIVERY_WITH_PAYLOAD = dict(DELIVERY, payload=WEBHOOK_EVENT)


def page(items, next_cursor=None):
    return {"data": items, "next_cursor": next_cursor}


def listing(items):
    return {"data": items}
