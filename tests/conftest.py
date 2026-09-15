"""Общие фикстуры: respx-роутер на базовом URL API, клиенты, «тихий» sleep.

Ключи в тестах — короткие заглушки вида ``vk_test_example``: экспорт SDK в
публичный репозиторий отказывается от файлов, где встречается
``vk_(live|test)_`` с 32+ символами, чтобы настоящий ключ не утёк в git.
"""

from __future__ import annotations

from typing import List

import httpx
import pytest
import respx

import vdsok
from vdsok import AsyncVdsok, Vdsok

BASE_URL = "https://vdsok.guru/api/v1"
TEST_KEY = "vk_test_example"


@pytest.fixture
def api():
    with respx.mock(base_url=BASE_URL, assert_all_called=False, assert_all_mocked=True) as router:
        yield router


@pytest.fixture
def client():
    with Vdsok(TEST_KEY) as c:
        yield c


@pytest.fixture
async def aclient():
    async with AsyncVdsok(TEST_KEY) as c:
        yield c


@pytest.fixture
def sleeps(monkeypatch) -> List[float]:
    """Записывает паузы между ретраями вместо реального сна."""
    calls: List[float] = []

    def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    async def fake_async_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(vdsok._client, "_sleep", fake_sleep)
    monkeypatch.setattr(vdsok._client, "_async_sleep", fake_async_sleep)
    return calls


def json_response(status: int, payload, **headers) -> httpx.Response:
    base = {"X-Request-ID": "req_test1234"}
    base.update(headers)
    return httpx.Response(status, json=payload, headers=base)


def error_response(status: int, code: str, message: str = "error", details=None, **headers) -> httpx.Response:
    body = {"error": {"code": code, "message": message, "request_id": "req_err0001"}}
    if details is not None:
        body["error"]["details"] = details
    return json_response(status, body, **headers)
