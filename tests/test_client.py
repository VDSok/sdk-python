"""Конструктор, заголовки, метаданные ответа, произвольный запрос."""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

import vdsok
from vdsok import RateLimitInfo, Vdsok

from conftest import BASE_URL, TEST_KEY, json_response
from fixtures import BALANCE, ME


def test_constructor_defaults():
    c = Vdsok(TEST_KEY)
    assert c.base_url == vdsok.DEFAULT_BASE_URL == "https://vdsok.guru/api/v1"
    assert c.timeout == 30.0
    assert c.max_retries == 2
    assert c.is_test_key is True
    c.close()


def test_constructor_rejects_empty_key():
    with pytest.raises(ValueError):
        Vdsok("")
    with pytest.raises(ValueError):
        Vdsok("   ")
    with pytest.raises(ValueError):
        Vdsok("vk_test_ex\nample")


def test_constructor_rejects_negative_retries():
    with pytest.raises(ValueError):
        Vdsok(TEST_KEY, max_retries=-1)


def test_repr_never_shows_the_key(client):
    text = repr(client)
    assert TEST_KEY not in text
    assert "mple" in text  # только хвост
    assert "vk_" in text


def test_base_url_trailing_slash_and_custom(api):
    api.get("/balance").mock(return_value=json_response(200, BALANCE))
    with Vdsok(TEST_KEY, base_url=BASE_URL + "/") as c:
        assert c.base_url == BASE_URL
        c.balance.get()
    assert api.calls.last.request.url == BASE_URL + "/balance"


def test_headers(api, client):
    route = api.get("/balance").mock(return_value=json_response(200, BALANCE))
    client.balance.get()
    headers = route.calls.last.request.headers
    assert headers["Authorization"] == f"Bearer {TEST_KEY}"
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"].startswith("vdsok-sdk-python/1.0.0")
    assert "Idempotency-Key" not in headers
    assert "Content-Type" not in headers or headers["Content-Type"] != "application/json"
    uuid.UUID(headers["X-Request-ID"])  # валидный uuid4


def test_request_id_is_unique_per_call(api, client):
    route = api.get("/balance").mock(return_value=json_response(200, BALANCE))
    client.balance.get()
    client.balance.get()
    ids = {call.request.headers["X-Request-ID"] for call in route.calls}
    assert len(ids) == 2


def test_custom_user_agent_and_default_headers(api):
    api.get("/balance").mock(return_value=json_response(200, BALANCE))
    with Vdsok(TEST_KEY, user_agent="my-app/2.0", default_headers={"X-Trace": "abc"}) as c:
        c.balance.get()
    headers = api.calls.last.request.headers
    assert headers["User-Agent"] == "my-app/2.0"
    assert headers["X-Trace"] == "abc"


def test_default_headers_cannot_replace_the_credential(api):
    """default_headers не должен подменять служебные заголовки — иначе опечатка
    в чужом словаре молча отправила бы запрос с другим ключом."""
    api.get("/balance").mock(return_value=json_response(200, BALANCE))
    with Vdsok(
        TEST_KEY,
        default_headers={
            "Authorization": "Bearer vk_live_someone_else",
            "Accept": "text/html",
            "User-Agent": "spoofed/0",
            "X-Request-ID": "not-a-uuid",
        },
    ) as c:
        c.balance.get()
    headers = api.calls.last.request.headers
    assert headers["Authorization"] == f"Bearer {TEST_KEY}"
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"].startswith("vdsok-sdk-python/")
    uuid.UUID(headers["X-Request-ID"])


def test_json_body_is_compact_and_typed(api, client):
    route = api.post("/servers/2001/actions/reinstall").mock(
        return_value=json_response(202, {"server_id": 2001, "status": "reinstalling", "os": "debian-12", "root_password": "x"})
    )
    client.servers.actions.reinstall(2001, "debian-12", ssh_key_ids=[3])
    request = route.calls.last.request
    assert request.headers["Content-Type"] == "application/json"
    assert json.loads(request.content) == {"os": "debian-12", "ssh_key_ids": [3]}


def test_response_meta_on_result(api, client):
    api.get("/balance").mock(
        return_value=json_response(
            200,
            BALANCE,
            **{"X-RateLimit-Limit": "120", "X-RateLimit-Remaining": "119", "X-RateLimit-Reset": "1789000000", "X-Sandbox": "true"},
        )
    )
    balance = client.balance.get()
    assert balance.balance == Decimal("42.15")
    assert balance.request_id == "req_test1234"
    assert balance.sandbox is True
    assert balance.rate_limit == RateLimitInfo(limit=120, remaining=119, reset=datetime.fromtimestamp(1789000000, tz=timezone.utc))
    assert balance.meta.status == 200
    assert balance.idempotency_key is None
    assert balance.raw["balance"] == "42.15"


def test_missing_rate_limit_headers(api, client):
    api.get("/balance").mock(return_value=httpx.Response(200, json=BALANCE))
    balance = client.balance.get()
    assert balance.rate_limit is None
    assert balance.sandbox is False
    # X-Request-ID сервера нет — остаётся тот, что послал SDK
    uuid.UUID(balance.request_id)


def test_me_health_openapi(api, client):
    api.get("/me").mock(return_value=json_response(200, ME))
    api.get("/health").mock(return_value=json_response(200, {"status": "ok", "time": "2026-09-15T10:00:00Z", "version": "1"}))
    api.get("/openapi.json").mock(return_value=json_response(200, {"openapi": "3.1.0"}))
    me = client.me()
    assert me.account_id == 57
    assert me.livemode is True
    assert me.sandbox_enabled is True
    assert me.api_version == "1"
    assert me.key.rate_per_minute == 120
    health = client.health()
    assert health.status == "ok"
    assert health.version == "1"
    assert health.time == datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
    assert client.openapi() == {"openapi": "3.1.0"}


def test_raw_request(api, client):
    api.get("/new-endpoint").mock(return_value=json_response(200, {"hello": "world"}))
    assert client.request("get", "new-endpoint", params={"a": 1, "b": None}) == {"hello": "world"}
    assert api.calls.last.request.url.params["a"] == "1"
    assert "b" not in api.calls.last.request.url.params


def test_raw_request_with_idempotency_key_sends_header(api, client):
    api.post("/future-money").mock(return_value=json_response(201, {"ok": True}))
    client.request("POST", "/future-money", json={"amount": Decimal("1.5")}, idempotency_key="a" * 20)
    request = api.calls.last.request
    assert request.headers["Idempotency-Key"] == "a" * 20
    assert json.loads(request.content) == {"amount": "1.50"}


def test_external_http_client_is_not_closed(api):
    http = httpx.Client()
    c = Vdsok(TEST_KEY, http_client=http)
    c.close()
    assert not http.is_closed
    http.close()


def test_own_http_client_is_closed_by_context_manager():
    with Vdsok(TEST_KEY) as c:
        http = c._http
    assert http.is_closed


def test_timeout_is_applied_to_httpx():
    with Vdsok(TEST_KEY, timeout=5) as c:
        assert c._http.timeout == httpx.Timeout(5.0)


def test_pdf_binary_result(api, client):
    api.get("/invoices/10231/pdf").mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.4 fake",
            headers={"Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="invoice-10231.pdf"', "X-Request-ID": "req_pdf"},
        )
    )
    pdf = client.invoices.pdf(10231)
    assert pdf.content.startswith(b"%PDF")
    assert pdf.filename == "invoice-10231.pdf"
    assert pdf.content_type == "application/pdf"
    assert pdf.request_id == "req_pdf"
    # ошибки этой ручки (400/404/429/503) приходят JSON-конвертом, поэтому
    # application/json в Accept обязателен: иначе строгий origin ответит 406
    assert api.calls.last.request.headers["Accept"] == "application/pdf, application/json"


def test_pdf_save(api, client, tmp_path):
    api.get("/invoices/1/pdf").mock(return_value=httpx.Response(200, content=b"%PDF", headers={"Content-Type": "application/pdf"}))
    target = tmp_path / "invoice.pdf"
    client.invoices.pdf(1).save(str(target))
    assert target.read_bytes() == b"%PDF"


def test_empty_result_for_204(api, client):
    api.delete("/ssh-keys/3").mock(return_value=httpx.Response(204, headers={"X-Request-ID": "req_del"}))
    result = client.ssh_keys.delete(3)
    assert isinstance(result, vdsok.EmptyResult)
    assert result.request_id == "req_del"


def test_non_json_success_body_raises(api, client):
    api.get("/balance").mock(return_value=httpx.Response(200, content=b"<html>", headers={"Content-Type": "text/html"}))
    with pytest.raises(vdsok.ApiError) as info:
        client.balance.get()
    assert info.value.code == "invalid_response"


def test_no_redirect_following():
    with Vdsok(TEST_KEY) as c:
        assert c._http.follow_redirects is False
