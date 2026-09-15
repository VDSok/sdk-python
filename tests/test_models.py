"""Разбор моделей: Decimal для денег, tz-aware datetime, вложенность,
терпимость к неизвестным полям, форматирование параметров."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from vdsok import models
from vdsok._parsing import build, compact_body, encode_params, format_money, format_timestamp, parse_money, parse_timestamp
from vdsok._types import NOT_GIVEN

from fixtures import ACCOUNT, INVOICE, ORDER, QUOTE, SERVER, SERVER_DETAIL, TARIFF, WEBHOOK_EVENT


def test_server_parsing():
    s = build(models.Server, SERVER)
    assert s.id == 2001
    assert s.billing.price_monthly == Decimal("5.90")
    assert s.billing.recurring_amount == Decimal("6.90")
    assert s.billing.next_due_at == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert s.flags.protected_until is None
    assert s.flags.synthetic is False
    # Локация и ОС в карточке — строки, а не каталожные объекты.
    assert s.location == "Amsterdam"
    assert s.os == "ubuntu-24.04"
    assert s.primary_ip == "203.0.113.29"
    assert s.ips == ["203.0.113.29", "2001:db8::29"]
    assert s.resources.vcpu == 1 and s.resources.disk_mb == 20480
    assert s.raw is not None and s.raw["id"] == 2001
    assert s.meta is None  # вложенный/собранный вручную объект без ответа


def test_server_detail_inherits_server():
    d = build(models.ServerDetail, SERVER_DETAIL)
    assert isinstance(d, models.Server)
    assert d.refund_quote.amount == Decimal("3.15")
    assert d.refund_quote.breakdown[0].days_left == 16
    assert d.refund_quote.breakdown[0].period_end.year == 2026
    assert d.live is None


def test_money_keeps_scale():
    t = build(models.Tariff, TARIFF)
    assert t.price_hourly == Decimal("0.0083")
    assert str(t.price_hourly) == "0.0083"
    assert t.periods[1].total == Decimal("54.22")
    assert t.periods[1].discount_percent == 10


def test_money_rejects_float():
    with pytest.raises(ValueError):
        parse_money(5.9)
    with pytest.raises(ValueError):
        build(models.Balance, {"balance": 5.9})


def test_unknown_fields_are_tolerated_and_kept_in_raw():
    payload = dict(ACCOUNT, brand_new_field={"x": 1})
    a = build(models.Account, payload)
    assert a.login == "kefisto"
    assert a.group.discount_percent == 15
    assert a.raw["brand_new_field"] == {"x": 1}


def test_unknown_enum_values_do_not_break():
    s = build(models.Server, dict(SERVER, status="hibernated"))
    assert s.status == "hibernated"


def test_partial_object_gets_defaults():
    inv = build(models.Invoice, {"id": 1})
    assert inv.id == 1
    assert inv.items == []
    assert inv.paid_at is None


def test_invoice_items():
    inv = build(models.Invoice, INVOICE)
    assert inv.items[0].server_id == 2001
    assert inv.items[0].amount == Decimal("5.90")
    assert inv.paid_at.second == 1


def test_quote_discounts():
    q = build(models.Quote, QUOTE)
    assert [d.type for d in q.discounts] == ["group", "period"]
    assert q.total == Decimal("14.29")
    assert q.promo is None
    assert q.shortfall == Decimal("0.00")


def test_order_terminal():
    o = build(models.Order, ORDER)
    assert o.status == "provisioning" and not o.is_terminal
    assert build(models.Order, dict(ORDER, status="active")).is_terminal
    assert build(models.Order, dict(ORDER, status="failed")).is_terminal


def test_webhook_event_model_and_parse_helper():
    e = build(models.WebhookEvent, WEBHOOK_EVENT)
    assert e.type == "server.suspended"
    assert e.created_at.tzinfo is timezone.utc
    assert e.data.previous == {"status": "active"}
    server = models.parse(models.Server, e.data.object)
    assert server.id == 2001 and server.status == "suspended"


def test_bad_timestamp_names_the_field():
    with pytest.raises(ValueError) as info:
        build(models.Invoice, {"created_at": "yesterday"})
    assert "Invoice.created_at" in str(info.value)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-09-15T10:00:00Z", datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)),
        ("2026-09-15T10:00:00.5Z", datetime(2026, 9, 15, 10, 0, 0, 500000, tzinfo=timezone.utc)),
        ("2026-09-15T10:00:00.1234567Z", datetime(2026, 9, 15, 10, 0, 0, 123456, tzinfo=timezone.utc)),
        ("2026-09-15T12:00:00+02:00", datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)),
        (None, None),
    ],
)
def test_parse_timestamp(raw, expected):
    assert parse_timestamp(raw) == expected


def test_format_timestamp():
    assert format_timestamp(datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)) == "2026-09-15T10:00:00Z"
    assert format_timestamp(datetime(2026, 9, 15, 10, 0)) == "2026-09-15T10:00:00Z"  # наивная = UTC
    assert format_timestamp(date(2026, 9, 15)) == "2026-09-15T00:00:00Z"
    assert format_timestamp("2026-09-15T10:00:00Z") == "2026-09-15T10:00:00Z"
    assert format_timestamp(datetime(2026, 9, 15, 10, 0, 0, 250000, tzinfo=timezone.utc)) == "2026-09-15T10:00:00.25Z"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("25", "25.00"),
        ("25.5", "25.50"),
        (25, "25.00"),
        (Decimal("0.0083"), "0.0083"),
        (0.1, "0.10"),
        ("12.3456", "12.3456"),
    ],
)
def test_format_money(value, expected):
    assert format_money(value) == expected


def test_format_money_rejects_bad_values():
    with pytest.raises(ValueError):
        format_money("1.23456")
    with pytest.raises(ValueError):
        format_money("abc")
    with pytest.raises(TypeError):
        format_money(True)
    with pytest.raises(ValueError):
        format_money("NaN")


def test_encode_params():
    out = encode_params(
        {
            "a": None,
            "b": NOT_GIVEN,
            "flag": True,
            "since": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "amount": Decimal("1.50"),
            "n": 5,
        }
    )
    assert out == {"flag": "true", "since": "2026-01-01T00:00:00Z", "amount": "1.50", "n": "5"}


def test_compact_body_keeps_explicit_none():
    out = compact_body({"notes": None, "name": NOT_GIVEN, "amount": Decimal("2"), "when": datetime(2026, 1, 1, tzinfo=timezone.utc)})
    assert out == {"notes": None, "amount": "2.00", "when": "2026-01-01T00:00:00Z"}
