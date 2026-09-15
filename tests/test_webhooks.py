"""Подпись вебхуков: verify / construct_event / sign."""

import hashlib
import hmac
import json
import time

import pytest

import vdsok
from vdsok import WebhookSignatureError, Webhooks, construct_event, verify
from vdsok.webhooks import sign

from fixtures import WEBHOOK_EVENT

SECRET = "whsec_" + "k" * 44
BODY = json.dumps(WEBHOOK_EVENT, separators=(",", ":")).encode()


def headers_for(body=BODY, secret=SECRET, ts=None, **extra):
    ts = int(time.time()) if ts is None else ts
    h = {
        "X-Webhook-Signature": sign(secret, ts, body),
        "X-Webhook-Timestamp": str(ts),
        "X-Webhook-Id": WEBHOOK_EVENT["id"],
        "X-Webhook-Event": WEBHOOK_EVENT["type"],
        "User-Agent": "VDSok-Webhooks/1.0",
    }
    h.update(extra)
    return h


def test_sign_matches_spec_formula():
    ts = 1789000000
    expected = hmac.new(SECRET.encode(), f"{ts}.".encode() + BODY, hashlib.sha256).hexdigest()
    assert sign(SECRET, ts, BODY) == "v1=" + expected


def test_verify_ok():
    assert verify(SECRET, headers_for(), BODY) is True


def test_verify_accepts_str_body_and_bytes_secret():
    assert verify(SECRET.encode(), headers_for(), BODY.decode()) is True


def test_verify_headers_case_insensitive():
    h = {k.lower(): v for k, v in headers_for().items()}
    assert verify(SECRET, h, BODY) is True
    h = {k.upper(): v for k, v in headers_for().items()}
    assert verify(SECRET, h, BODY) is True


def test_verify_accepts_list_of_pairs():
    assert verify(SECRET, list(headers_for().items()), BODY) is True


def test_verify_wrong_secret():
    assert verify("whsec_" + "z" * 44, headers_for(), BODY) is False


def test_verify_tampered_body():
    tampered = BODY.replace(b"suspended", b"active")
    assert verify(SECRET, headers_for(), tampered) is False


def test_verify_reserialized_body_fails():
    # Пересериализованный JSON (другие пробелы) — это уже другие байты
    pretty = json.dumps(WEBHOOK_EVENT, indent=2).encode()
    assert verify(SECRET, headers_for(), pretty) is False


def test_verify_expired_timestamp():
    old = int(time.time()) - 301
    assert verify(SECRET, headers_for(ts=old), BODY) is False
    assert verify(SECRET, headers_for(ts=old), BODY, tolerance=600) is True
    assert verify(SECRET, headers_for(ts=old), BODY, tolerance=None) is True


def test_verify_future_timestamp():
    future = int(time.time()) + 400
    assert verify(SECRET, headers_for(ts=future), BODY) is False


def test_verify_now_parameter():
    ts = 1789000000
    assert verify(SECRET, headers_for(ts=ts), BODY, now=ts + 10) is True
    assert verify(SECRET, headers_for(ts=ts), BODY, now=ts + 1000) is False


def test_verify_missing_headers():
    h = headers_for()
    del h["X-Webhook-Signature"]
    assert verify(SECRET, h, BODY) is False
    h = headers_for()
    del h["X-Webhook-Timestamp"]
    assert verify(SECRET, h, BODY) is False
    assert verify(SECRET, {}, BODY) is False


def test_verify_bad_timestamp_value():
    assert verify(SECRET, headers_for(**{"X-Webhook-Timestamp": "soon"}), BODY) is False


def test_verify_multiple_signatures_during_rotation():
    ts = int(time.time())
    old_secret = "whsec_" + "o" * 44
    combined = sign(old_secret, ts, BODY) + "," + sign(SECRET, ts, BODY)
    h = headers_for(ts=ts, **{"X-Webhook-Signature": combined})
    assert verify(SECRET, h, BODY) is True
    assert verify(old_secret, h, BODY) is True


def test_verify_ignores_unknown_versions():
    ts = int(time.time())
    h = headers_for(ts=ts, **{"X-Webhook-Signature": "v0=deadbeef"})
    assert verify(SECRET, h, BODY) is False
    h = headers_for(ts=ts, **{"X-Webhook-Signature": "v0=deadbeef, " + sign(SECRET, ts, BODY)})
    assert verify(SECRET, h, BODY) is True


def test_construct_event():
    event = construct_event(SECRET, headers_for(), BODY)
    assert isinstance(event, vdsok.WebhookEvent)
    assert event.id == "evt_01J7ZK3Q9X4R"
    assert event.type == "server.suspended"
    assert event.account_id == 57
    assert event.created_at.year == 2026
    assert event.data.object["status"] == "suspended"
    assert event.data.previous == {"status": "active"}
    assert event.resource == "/api/v1/servers/2001"
    server = vdsok.models.parse(vdsok.Server, event.data.object)
    assert server.id == 2001


def test_construct_event_raises_on_bad_signature():
    with pytest.raises(WebhookSignatureError, match="mismatch"):
        construct_event(SECRET, headers_for(secret="whsec_" + "w" * 44), BODY)


def test_construct_event_raises_on_replay():
    with pytest.raises(WebhookSignatureError, match="tolerance"):
        construct_event(SECRET, headers_for(ts=int(time.time()) - 1000), BODY)


def test_construct_event_raises_on_missing_header():
    with pytest.raises(WebhookSignatureError, match="missing"):
        construct_event(SECRET, {}, BODY)


def test_construct_event_rejects_non_json():
    body = b"not json"
    with pytest.raises(ValueError):
        construct_event(SECRET, headers_for(body=body), body)
    body = b"[1,2]"
    with pytest.raises(ValueError):
        construct_event(SECRET, headers_for(body=body), body)


def test_empty_secret_rejected():
    with pytest.raises(ValueError):
        sign("", 1, BODY)


def test_verify_and_construct_event_share_argument_order():
    """Две функции, которые интегратор копирует рядом, не должны требовать
    аргументы в разном порядке."""
    import inspect

    from vdsok import webhooks as w

    assert list(inspect.signature(w.verify).parameters) == list(inspect.signature(w.construct_event).parameters)


def test_class_facade_and_client_attribute():
    assert Webhooks.verify(SECRET, headers_for(), BODY) is True
    assert Webhooks.DEFAULT_TOLERANCE == 300
    with vdsok.Vdsok("vk_test_example") as c:
        assert c.webhooks.verify(SECRET, headers_for(), BODY) is True
        assert isinstance(c.webhooks.construct_event(SECRET, headers_for(), BODY), vdsok.WebhookEvent)
