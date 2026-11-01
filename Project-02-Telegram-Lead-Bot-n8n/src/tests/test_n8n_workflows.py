"""Статическая проверка n8n-воркфлоу без запуска n8n.

Проверяются структура, связи, выражения и безопасность JSON-экспортов:
валидность JSON, наличие триггера, уникальность имён/id, отсутствие висячих
связей и недостижимых узлов, отсутствие зашитых секретов, использование только
`$env.*` и совпадение правил маршрутизации с Python-реализацией.

Это дешёвый «линтер контракта»: реальный прогон n8n — отдельный E2E-этап.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.services.routing import DEFAULT_HIGH_VALUE_KEYWORDS

WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "n8n" / "workflows"
WORKFLOW_FILES = sorted(WORKFLOWS_DIR.glob("*.json"))

TRIGGER_TYPES = {
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.errorTrigger",
}
ANNOTATION_TYPES = {"n8n-nodes-base.stickyNote"}
TERMINAL_TYPES = {
    "n8n-nodes-base.respondToWebhook",
    "n8n-nodes-base.telegram",
    "n8n-nodes-base.noOp",
}

# Заголовки/поля, которые обязаны брать значение из окружения, а не из литерала.
ENV_ONLY_MARKERS = ("TELEGRAM_ADMIN_CHAT_ID", "ADMIN_API_TOKEN", "LEAD_API_URL", "CRM_TARGET")

SECRET_PATTERNS = (
    re.compile(r"\d{8,}:[A-Za-z0-9_-]{30,}"),  # токен Telegram
    re.compile(r"-----BEGIN [A-Z ]+-----"),  # приватный ключ
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),  # OpenAI-подобный ключ
)


def load_workflow(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in iter_strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in iter_strings(item)]
    return []


def outgoing_targets(workflow: dict[str, Any], node_name: str) -> list[str]:
    targets: list[str] = []
    for branches in workflow.get("connections", {}).get(node_name, {}).get("main", []):
        for connection in branches or []:
            targets.append(connection["node"])
    return targets


def reachable_from_triggers(workflow: dict[str, Any]) -> set[str]:
    nodes = {node["name"]: node for node in workflow["nodes"]}
    start = [name for name, node in nodes.items() if node["type"] in TRIGGER_TYPES]
    seen: set[str] = set()
    queue = list(start)
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(outgoing_targets(workflow, current))
    return seen


def workflow_ids() -> list[str]:
    return [path.name for path in WORKFLOW_FILES]


def test_workflows_directory_is_not_empty() -> None:
    assert WORKFLOW_FILES, "в n8n/workflows нет ни одного воркфлоу"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_workflow_is_valid_json_with_required_keys(path: Path) -> None:
    workflow = load_workflow(path)

    assert workflow["name"].strip(), f"{path.name}: пустое имя воркфлоу"
    assert workflow["nodes"], f"{path.name}: нет узлов"
    assert workflow.get("connections") is not None, f"{path.name}: нет секции connections"
    assert workflow.get("settings", {}).get("executionOrder"), f"{path.name}: нет executionOrder"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_node_names_and_ids_are_unique(path: Path) -> None:
    nodes = load_workflow(path)["nodes"]

    names = [node["name"] for node in nodes]
    ids = [node["id"] for node in nodes]

    assert len(names) == len(set(names)), f"{path.name}: дубли имён узлов"
    assert len(ids) == len(set(ids)), f"{path.name}: дубли id узлов"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_nodes_have_type_and_position(path: Path) -> None:
    for node in load_workflow(path)["nodes"]:
        assert node["type"].startswith("n8n-nodes-base."), f"{path.name}: {node['name']} — чужой префикс типа"
        position = node.get("position")
        assert isinstance(position, list) and len(position) == 2, f"{path.name}: {node['name']} без позиции"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_workflow_has_single_trigger(path: Path) -> None:
    nodes = load_workflow(path)["nodes"]
    triggers = [node["name"] for node in nodes if node["type"] in TRIGGER_TYPES]

    assert len(triggers) == 1, f"{path.name}: ожидался ровно один триггер, найдено {triggers}"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_connections_reference_existing_nodes(path: Path) -> None:
    workflow = load_workflow(path)
    names = {node["name"] for node in workflow["nodes"]}

    for source, channels in workflow.get("connections", {}).items():
        assert source in names, f"{path.name}: связь из несуществующего узла {source}"
        for branches in channels.get("main", []):
            for connection in branches or []:
                assert connection["node"] in names, f"{path.name}: связь в несуществующий узел {connection['node']}"
                assert connection["type"] == "main", f"{path.name}: неожиданный тип связи"
                assert connection.get("index", 0) == 0, f"{path.name}: неожиданный выходной индекс"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_every_executable_node_is_reachable_from_trigger(path: Path) -> None:
    workflow = load_workflow(path)
    executable = {node["name"] for node in workflow["nodes"] if node["type"] not in ANNOTATION_TYPES}

    unreachable = executable - reachable_from_triggers(workflow)

    assert not unreachable, f"{path.name}: узлы недостижимы от триггера: {sorted(unreachable)}"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_workflow_has_terminal_node(path: Path) -> None:
    types = {node["type"] for node in load_workflow(path)["nodes"]}

    assert types & TERMINAL_TYPES, f"{path.name}: нет терминального узла (respond/telegram/noOp)"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_webhook_workflows_respond_to_caller(path: Path) -> None:
    nodes = load_workflow(path)["nodes"]
    types = {node["type"] for node in nodes}

    if "n8n-nodes-base.webhook" in types:
        webhook = next(node for node in nodes if node["type"] == "n8n-nodes-base.webhook")
        assert webhook["parameters"].get("responseMode") == "responseNode", f"{path.name}: webhook без responseNode"
        assert any(node["type"] == "n8n-nodes-base.respondToWebhook" for node in nodes), (
            f"{path.name}: webhook-воркфлоу обязан ответить вызывающей стороне"
        )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_cron_workflows_use_valid_expression(path: Path) -> None:
    nodes = load_workflow(path)["nodes"]
    schedules = [node for node in nodes if node["type"] == "n8n-nodes-base.scheduleTrigger"]

    for node in schedules:
        intervals = node["parameters"]["rule"]["interval"]
        assert intervals, f"{path.name}: расписание без интервалов"
        for interval in intervals:
            expression = interval.get("expression", "")
            assert len(expression.split()) == 5, f"{path.name}: cron не из 5 полей: {expression!r}"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_workflow_documents_itself(path: Path) -> None:
    notes = [node for node in load_workflow(path)["nodes"] if node["type"] in ANNOTATION_TYPES]

    assert notes, f"{path.name}: нет sticky note с описанием контракта"
    assert any(len(node["parameters"].get("content", "")) > 80 for node in notes), (
        f"{path.name}: sticky note слишком короткая, чтобы быть контрактом"
    )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_no_hardcoded_secrets(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")

    for pattern in SECRET_PATTERNS:
        match = pattern.search(raw)
        assert match is None, f"{path.name}: похоже на зашитый секрет ({pattern.pattern})"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_environment_values_come_from_env(path: Path) -> None:
    """Реальные значения env обязаны идти через $env (sticky note — только текст)."""
    workflow = load_workflow(path)

    executable = [node for node in workflow["nodes"] if node["type"] not in ANNOTATION_TYPES]
    for node in executable:
        for text in iter_strings(node):
            for marker in ENV_ONLY_MARKERS:
                if marker in text:
                    assert "$env." in text, (
                        f"{path.name}: узел {node['name']} использует {marker} без $env — возможен литерал"
                    )


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=workflow_ids())
def test_routing_keywords_match_python_implementation(path: Path) -> None:
    """Правило маршрутизации должно совпадать с app/services/routing.py."""
    if path.name != "lead_routing.json":
        return

    workflow = load_workflow(path)
    code = "\n".join(
        node["parameters"].get("jsCode", "") for node in workflow["nodes"] if node["type"].endswith(".code")
    )
    match = re.search(r"const keywords = \[(.*?)\];", code, re.DOTALL)
    assert match, "lead_reminders.json: не найдено объявление keywords"

    js_keywords = set(re.findall(r"'([^']+)'", match.group(1)))
    assert js_keywords == set(DEFAULT_HIGH_VALUE_KEYWORDS), (
        "набор ключевых слов в n8n расходится с app/services/routing.py: "
        f"{js_keywords ^ set(DEFAULT_HIGH_VALUE_KEYWORDS)}"
    )


# --- устойчивость Lead Reminders ---


def _lead_reminders() -> dict[str, Any] | None:
    for path in WORKFLOW_FILES:
        workflow = load_workflow(path)
        if workflow["name"] == "Lead Reminders":
            return workflow
    return None


def _node(workflow: dict[str, Any], node_type_suffix: str) -> dict[str, Any]:
    for node in workflow["nodes"]:
        if node["type"].endswith(node_type_suffix):
            return node
    raise AssertionError(f"нет узла типа *{node_type_suffix}")


def test_lead_reminders_http_node_is_fail_safe() -> None:
    """HTTP-узел не должен ни зависать на минуты, ни ронять прогон без ретраев."""
    workflow = _lead_reminders()
    assert workflow is not None, "Lead Reminders не найден"

    node = _node(workflow, "httpRequest")
    options = node["parameters"].get("options", {})
    response = options.get("response", {}).get("response", {})

    assert response.get("neverError") is True, "нет neverError: не-2xx снова станет ошибкой узла"
    assert response.get("fullResponse") is True, "нет fullResponse: statusCode недоступен для проверки"
    assert 10_000 <= options.get("timeout", 0) <= 15_000, "timeout должен быть 10–15 с"
    assert node.get("retryOnFail") is True, "нет retryOnFail"
    assert 2 <= node.get("maxTries", 0) <= 5, "попыток должно быть 2–5"
    assert "continueErrorOutput" in str(node.get("onError", "")), "ошибка не уходит на отдельный выход"


def test_lead_reminders_fails_loudly_when_api_is_down() -> None:
    """Не-2xx от API обязан завершать прогон ошибкой, а не превращаться в «0 лидов»."""
    workflow = _lead_reminders()
    assert workflow is not None, "Lead Reminders не найден"

    assert _node(workflow, "stopAndError"), "нет узла Stop And Error для контролируемого падения"

    # оба «плохих» выхода (HTTP error и IF=false) должны вести в Stop And Error
    connections = workflow["connections"]
    http_node = _node(workflow, "httpRequest")["name"]
    gate = _node(workflow, "if")["name"]

    def branch_targets(source: str) -> list[str]:
        return [c["node"] for branches in connections[source]["main"] for c in (branches or [])]

    assert any("Stop And Error" in t for t in branch_targets(http_node)), "ошибка HTTP не обработана"
    assert any("Stop And Error" in t for t in branch_targets(gate)), "не-2xx после IF не обработан"


def test_lead_reminders_code_node_respects_telegram_limit() -> None:
    """Code-узел обязан ограничивать длину частей сообщения."""
    workflow = _lead_reminders()
    assert workflow is not None, "Lead Reminders не найден"

    code = _node(workflow, ".code")["parameters"]["jsCode"]

    limits = [int(value) for value in re.findall(r"SAFE_LIMIT\s*=\s*(\d+)", code)]
    assert limits, "нет константы SAFE_LIMIT"
    assert all(3000 <= value <= 4000 for value in limits), f"SAFE_LIMIT вне безопасного диапазона: {limits}"
    assert "parts" in code, "нет разбиения на части"
    assert "items.length === 0" in code or "items.length" in code, "нет защиты от пустого списка"
