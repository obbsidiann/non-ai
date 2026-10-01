"""Инструменты, которые агент может вызывать."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

MAX_FILE_SIZE = 50_000     # символов — больше не суём в контекст
MAX_DIR_ENTRIES = 200


# --- Реализации ---

def read_file(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"ОШИБКА: файл не найден: {path}"
    if p.is_dir():
        return(
            f"ОШИБКА: {path} — это директория, а не файл. "
            f'Вызови инструмент так: <list_dir path="{path}" />'
        )  
    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"ОШИБКА: {path} — не текстовый файл (бинарный?)"
    except PermissionError:
        return f"ОШИБКА: нет прав на чтение {path}"
    except Exception as e:
        return f"ОШИБКА: {e}"

    if len(content) > MAX_FILE_SIZE:
        return content[:MAX_FILE_SIZE] + f"\n\n[...обрезано, всего {len(content)} символов]"
    return content if content else "(пустой файл)"


def list_dir(path: str = ".") -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"ОШИБКА: путь не найден: {path}"
    if not p.is_dir():
        return f"ОШИБКА: {path} — не директория"

    SKIP = {"__pycache__", ".git", ".venv", "venv", ".mypy_cache",
            ".pytest_cache", ".ruff_cache", "node_modules", ".DS_Store"}

    try:
        entries = [
            e for e in p.iterdir()
            if e.name not in SKIP
        ]
        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return f"ОШИБКА: нет прав на чтение {path}"
    if not entries:
        return "(пусто)"

    lines = []
    for e in entries[:MAX_DIR_ENTRIES]:
        suffix = "/" if e.is_dir() else ""
        lines.append(f"{e.name}{suffix}")
    if len(entries) > MAX_DIR_ENTRIES:
        lines.append(f"... и ещё {len(entries) - MAX_DIR_ENTRIES}")

    return "\n".join(lines)


# --- Реестр ---

@dataclass
class Tool:
    name: str
    description: str
    schema: str
    handler: Callable[..., str]


TOOLS: dict[str, Tool] = {
    "read_file": Tool(
        name="read_file",
        description="Прочитать содержимое файла по пути.",
        schema='<read_file path="путь/к/файлу" />',
        handler=read_file,
    ),
    "list_dir": Tool(
        name="list_dir",
        description="Показать содержимое директории.",
        schema='<list_dir path="путь/к/папке" />',
        handler=list_dir,
    ),
}


# --- Парсер вызовов ---

_TOOL_CALL_RE = re.compile(
    r'<(read_file|list_dir)\s+path="([^"]*)"\s*/?>',
    re.IGNORECASE,
)


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Найти все вызовы инструментов в тексте модели."""
    calls = []
    for m in _TOOL_CALL_RE.finditer(text):
        calls.append((m.group(1).lower(), {"path": m.group(2)}))
    return calls


def execute_tool(name: str, args: dict) -> str:
    tool = TOOLS.get(name)
    if tool is None:
        return f"ОШИБКА: неизвестный инструмент: {name}"
    try:
        return tool.handler(**args)
    except TypeError as e:
        return f"ОШИБКА: неверные аргументы для {name}: {e}"
    except Exception as e:
        return f"ОШИБКА: {e}"


def tools_prompt() -> str:
    """Системная инструкция — что умеет агент."""
    lines = [
        "## Инструменты",
        "",
        "Ты можешь вызывать инструменты, чтобы посмотреть файлы пользователя.",
        "Формат вызова — XML-тег, ровно так:",
        "",
    ]
    for t in TOOLS.values():
        lines.append(f"  {t.schema}")
        lines.append(f"     — {t.description}")
    lines += [
        "",
        "Правила:",
        "1. Если нужно посмотреть файл или папку — выведи ТОЛЬКО тег, без лишнего текста.",
        "2. Ты получишь ответ в виде <result>...</result> и продолжишь.",
        "3. Если инструменты не нужны — просто отвечай обычным текстом.",
        "4. Не выдумывай содержимое — сначала читай файл, потом отвечай.",
    ]
    return "\n".join(lines)