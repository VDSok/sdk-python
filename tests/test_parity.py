"""Синхронные и асинхронные ресурсы не должны разъезжаться, а таблица
операций — покрывать каждый operationId спецификации."""

import inspect
import re
from pathlib import Path

import pytest

from vdsok import _async_resources, _ops, _resources

GROUPS = [
    "Account",
    "Balance",
    "Invoices",
    "Catalog",
    "ServerActions",
    "ServerIps",
    "Orders",
    "Servers",
    "Domains",
    "SshKeys",
    "Keys",
    "WebhookDeliveries",
    "Webhooks",
]


def _public_methods(cls):
    return {
        name: inspect.signature(fn)
        for name, fn in inspect.getmembers(cls, callable)
        if not name.startswith("_") and inspect.isfunction(fn)
    }


@pytest.mark.parametrize("group", GROUPS)
def test_sync_and_async_groups_have_identical_methods(group):
    sync_methods = _public_methods(getattr(_resources, group))
    async_methods = _public_methods(getattr(_async_resources, group))
    assert set(sync_methods) == set(async_methods)
    for name, sig in sync_methods.items():
        assert list(sig.parameters) == list(async_methods[name].parameters), f"{group}.{name}"
        for p in sig.parameters.values():
            assert p.default == async_methods[name].parameters[p.name].default, f"{group}.{name}({p.name})"


SPEC = Path(__file__).resolve().parents[3] / "docs" / "openapi" / "vdsok-client-api-v1.yaml"

# Строители, которые вызывает сам клиент (client.health()/me()/openapi()),
# а не группа ресурсов.
CLIENT_LEVEL_OPS = {"get_health", "get_me", "get_openapi"}

# Обязательные аргументы строителей, которые нельзя заполнить единицей.
_STUBS = {
    "os": "x",
    "name": "x",
    "gateway": "x",
    "public_key": "x",
    "auth_code": "x",
    "ptr": "x",
    "url": "x",
    "action": "restart",
    "nameservers": ["a", "b"],
    "events": ["a", "b"],
    "amount": "1",
}
# У этих строителей есть клиентская валидация «передайте хотя бы одно поле».
_EXTRA_ARGS = {
    "renew_server": {"months": 1},
    "update_server": {"auto_renew": True},
    "update_domain": {"auto_renew": True},
    "update_webhook": {"active": True},
}


@pytest.mark.skipif(not SPEC.exists(), reason="spec file not in this checkout")
def test_every_operation_id_has_an_op_builder():
    text = SPEC.read_text(encoding="utf-8")
    # Только paths; вебхуки (webhook_*) — исходящие события, не вызовы SDK.
    paths_section = text.split("\nwebhooks:\n", 1)[0]
    operation_ids = set(re.findall(r"operationId:\s*(\w+)", paths_section))
    assert operation_ids, "no operationId found in spec"
    missing = sorted(op for op in operation_ids if not hasattr(_ops, op))
    assert missing == []


def _builders():
    """Строители операций из ``_ops`` (не импортированные туда helpers)."""
    return {
        name: fn
        for name, fn in inspect.getmembers(_ops, inspect.isfunction)
        if not name.startswith("_") and fn.__module__ == _ops.__name__
    }


def _build(name, fn):
    """Собрать ``Op``, заполнив обязательные аргументы заглушками."""
    kwargs = {}
    for p in inspect.signature(fn).parameters.values():
        if p.default is not inspect.Parameter.empty:
            continue
        kwargs[p.name] = _STUBS.get(p.name, 1)
    kwargs.update(_EXTRA_ARGS.get(name, {}))
    return fn(**kwargs)


@pytest.mark.skipif(not SPEC.exists(), reason="spec file not in this checkout")
def test_op_paths_exist_in_spec():
    """Запасная проверка без PyYAML: путь каждого строителя есть в спеке."""
    text = SPEC.read_text(encoding="utf-8")
    spec_paths = set(re.findall(r"^  (/[^\s:]*):\s*$", text, re.MULTILINE))
    for name, fn in _builders().items():
        op = _build(name, fn)
        template = re.sub(r"/\d+", "/{id}", op.path)
        matches = [p for p in spec_paths if re.sub(r"\{[^}]+\}", "{id}", p) == template]
        assert matches, f"{name}: {op.path} not in spec"


def test_every_op_builder_is_reachable_from_a_resource_group():
    """Строитель, до которого нельзя дойти через client.<группа>.<метод>, —
    мёртвый код: ручка есть в спеке и в таблице, но пользователю недоступна."""
    used = set(re.findall(r"ops\.(\w+)\(", inspect.getsource(_resources)))
    used_async = set(re.findall(r"ops\.(\w+)\(", inspect.getsource(_async_resources)))
    unreachable = sorted(set(_builders()) - used - CLIENT_LEVEL_OPS)
    assert unreachable == []
    assert sorted(used) == sorted(used_async)


# ------------------------------------------------------------------ спека ↔ таблица

try:  # PyYAML входит в [dev]; без него сверка со схемами пропускается,
    import yaml  # а остальные тесты в этом файле продолжают работать
except ImportError:  # pragma: no cover
    yaml = None

needs_spec = pytest.mark.skipif(
    not SPEC.exists() or yaml is None, reason="spec file or PyYAML not available in this checkout"
)


def _spec():
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))


def _ref_name(node):
    if isinstance(node, dict) and "$ref" in node:
        return node["$ref"].rsplit("/", 1)[-1]
    return None


def _spec_operations():
    """operationId -> (METHOD, path, {статус: схема успешного ответа})."""
    out = {}
    # только paths: секция webhooks описывает исходящие события, их SDK не вызывает
    for path, item in _spec()["paths"].items():
        for method, op in item.items():
            if method not in ("get", "post", "put", "patch", "delete", "head"):
                continue
            success = {}
            for status, response in (op.get("responses") or {}).items():
                if not str(status).startswith("2"):
                    continue
                media = (response.get("content") or {}).get("application/json")
                success[int(status)] = media.get("schema") if media else None
            out[op["operationId"]] = (method.upper(), path, success)
    return out


def _item_schema(node, schemas):
    """``ServerPage`` -> ``Server``; работает и со встроенной схемой ``{data: [...]}``."""
    name = _ref_name(node)
    schema = schemas.get(name) if name else node
    data = ((schema or {}).get("properties") or {}).get("data") or {}
    return _ref_name(data.get("items")) if data.get("type") == "array" else None


@needs_spec
def test_op_method_and_path_match_the_spec():
    """Регрессия: раньше сверялся только шаблон пути, так что GET вместо POST
    на том же URL тест бы не заметил."""
    operations = _spec_operations()
    for name, fn in _builders().items():
        assert name in operations, f"{name}: no such operationId in the spec"
        method, path, _ = operations[name]
        op = _build(name, fn)
        assert op.method == method, f"{name}: {op.method} != {method}"
        assert re.sub(r"\{[^}]+\}", "{id}", path) == re.sub(r"/\d+", "/{id}", op.path), name


@needs_spec
def test_response_models_match_the_spec_schemas():
    """Каждый успешный статус разбирается в модель той схемы, которую обещает
    спека. Именно здесь ловится ``POST /servers`` 202: он описан как ``Order``,
    а не как ``ServerCreated``."""
    spec = _spec()
    schemas = spec["components"]["schemas"]
    operations = _spec_operations()
    for name, fn in _builders().items():
        op = _build(name, fn)
        for status, schema in sorted(operations[name][2].items()):
            if op.kind in (_ops.KIND_BINARY, _ops.KIND_RAW, _ops.KIND_EMPTY):
                continue  # PDF, сырой openapi.json и 204 моделей не имеют
            expected = (op.models_by_status or {}).get(status, op.model)
            wanted = (
                _item_schema(schema, schemas)
                if op.kind in (_ops.KIND_PAGE, _ops.KIND_LIST)
                else _ref_name(schema)
            )
            got = expected.__name__ if expected else None
            assert wanted == got, f"{name} {status}: spec {wanted}, sdk {got}"
