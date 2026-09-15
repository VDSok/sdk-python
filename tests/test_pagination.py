"""Курсорная пагинация: Page и обход всех страниц через list_all."""

import pytest

from vdsok import Page

from conftest import json_response
from fixtures import SERVER, TRANSACTION, page


def test_page_object(api, client):
    api.get("/servers").mock(return_value=json_response(200, page([SERVER, dict(SERVER, id=2002)], "c2")))
    p = client.servers.list(limit=2, status="active")
    assert isinstance(p, Page)
    assert len(p) == 2
    assert p.has_more and p.next_cursor == "c2"
    assert [s.id for s in p] == [2001, 2002]
    assert p[1].id == 2002
    assert p.request_id == "req_test1234"
    assert "items=2" in repr(p)
    params = api.calls.last.request.url.params
    assert params["limit"] == "2" and params["status"] == "active"
    assert "cursor" not in params


def test_list_all_follows_cursor(api, client):
    route = api.get("/servers").mock(
        side_effect=[
            json_response(200, page([SERVER], "cursor-2")),
            json_response(200, page([dict(SERVER, id=2002)], "cursor-3")),
            json_response(200, page([dict(SERVER, id=2003)], None)),
        ]
    )
    ids = [s.id for s in client.servers.list_all(status="active", limit=1)]
    assert ids == [2001, 2002, 2003]
    assert route.call_count == 3
    cursors = [c.request.url.params.get("cursor") for c in route.calls]
    assert cursors == [None, "cursor-2", "cursor-3"]
    assert all(c.request.url.params["status"] == "active" for c in route.calls)


def test_list_all_is_lazy(api, client):
    route = api.get("/servers").mock(return_value=json_response(200, page([SERVER], "more")))
    it = client.servers.list_all()
    assert route.call_count == 0
    next(it)
    assert route.call_count == 1


def test_list_all_stops_on_repeated_cursor(api, client):
    route = api.get("/servers").mock(return_value=json_response(200, page([SERVER], "same")))
    ids = [s.id for s in client.servers.list_all()]
    # первая страница без курсора, вторая с "same" и снова "same" -> стоп
    assert route.call_count == 2
    assert ids == [2001, 2001]


def test_list_all_empty(api, client):
    api.get("/transactions").mock(return_value=json_response(200, page([], None)))
    assert list(client.balance.transactions_all()) == []


def test_limit_validation(api, client):
    with pytest.raises(ValueError):
        client.servers.list(limit=0)
    with pytest.raises(ValueError):
        client.servers.list(limit=101)


def test_transactions_filters(api, client):
    api.get("/transactions").mock(return_value=json_response(200, page([TRANSACTION], None)))
    from datetime import datetime, timezone

    p = client.balance.transactions(direction="debit", since=datetime(2026, 9, 1, tzinfo=timezone.utc), until="2026-09-30T00:00:00Z")
    params = api.calls.last.request.url.params
    assert params["direction"] == "debit"
    assert params["since"] == "2026-09-01T00:00:00Z"
    assert params["until"] == "2026-09-30T00:00:00Z"
    assert p[0].description.startswith("VDS #2001")


def test_deliveries_list_all_passes_webhook_id(api, client):
    route = api.get("/webhooks/5/deliveries").mock(
        side_effect=[json_response(200, page([{"id": 1}], "n")), json_response(200, page([{"id": 2}], None))]
    )
    ids = [d.id for d in client.webhooks.deliveries.list_all(5, status="dead")]
    assert ids == [1, 2]
    assert route.call_count == 2
    assert route.calls.last.request.url.params["status"] == "dead"
