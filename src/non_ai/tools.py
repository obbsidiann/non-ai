"""Инструменты, которые агент может вызывать."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

MAX_FILE_SIZE = 50_000
MAX_DIR_ENTRIES = 200
BACKUP_KEEP = 20

BACKUP_DIR = (
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    / "non-ai" / "backups"
)
BACKUP_INDEX = BACKUP_DIR / "index.json"


# --- Бэкапы ---

def _load_index() -> dict:
    if not BACKUP_INDEX.exists():
        return {}
    try:
        return json.loads(BACKUP_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_index(index: dict) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_INDEX.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def backup_file(path: Path) -> Path | None:
    """Сохранить копию файла в ~/.local/share/non-ai/backups/."""
    if not path.exists() or not path.is_file():
        return None

    abs_path = str(path.resolve())
    file_hash = hashlib.sha1(abs_path.encode()).hexdigest()[:12]

    file_backup_dir = BACKUP_DIR / file_hash
    file_backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    backup_path = file_backup_dir / f"{ts}.bak"
    shutil.copy2(path, backup_path)

    index = _load_index()
    index[file_hash] = abs_path
    _save_index(index)

    backups = sorted(file_backup_dir.glob("*.bak"))
    if len(backups) > BACKUP_KEEP:
        for old in backups[:-BACKUP_KEEP]:
            try:
                old.unlink()
            except Exception:
                pass

    return backup_path


# --- Показ diff ---

def _print_preview(path: Path, new_content: str, existed: bool) -> None:
    import difflib

    print()
    action = "изменить" if existed else "создать"
    print(f"  📝 Предлагаю {action}: {path}")
    print()

    if not existed:
        lines = new_content.splitlines()
        print(f"  +++ {path} (новый файл, {len(lines)} строк)")
        for line in lines[:40]:
            print(f"  + {line}")
        if len(lines) > 40:
            print(f"  ... и ещё {len(lines) - 40} строк")
        print()
        return

    try:
        old_content = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  (не удалось прочитать оригинал: {e})")
        return

    diff = list(difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
        n=2,
    ))

    if not diff:
        print("  (файл уже имеет такое содержимое)")
        print()
        return

    shown = 0
    for line in diff:
        if shown >= 60:
            print(f"  ... и ещё {len(diff) - shown} строк diff")
            break
        line = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            print(f"  \033[1m{line}\033[0m")
        elif line.startswith("@@"):
            print(f"  \033[36m{line}\033[0m")
        elif line.startswith("+"):
            print(f"  \033[32m{line}\033[0m")
        elif line.startswith("-"):
            print(f"  \033[31m{line}\033[0m")
        else:
            print(f"  {line}")
        shown += 1
    print()


def _ask_confirm() -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        answer = input("  Применить? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes", "д", "да")


# --- Инструменты ---

def read_file(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"ОШИБКА: файл не найден: {path}"
    if p.is_dir():
        return (
            f'ОШИБКА: {path} — это директория, а не файл. '
            f'Вызови: <list_dir path="{path}" />'
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
        entries = [e for e in p.iterdir() if e.name not in SKIP]
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


def write_file(path: str, content: str) -> str:
    """Создать НОВЫЙ файл. Существующий — отказ, используй edit_file."""
    p = Path(path).expanduser()

    if p.exists():
        return (
            f"ОШИБКА: файл {path} уже существует. "
            f"Для изменения используй edit_file (old/new). "
            f"Если нужно перезаписать целиком — сначала удали файл вручную."
        )

    if not sys.stdin.isatty():
        return "ОШИБКА: подтверждение записи недоступно (stdin не терминал)."

    _print_preview(p, content, existed=False)

    if not _ask_confirm():
        return "ОТМЕНЕНО пользователем."

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except PermissionError:
        return f"ОШИБКА: нет прав на запись {path}"
    except Exception as e:
        return f"ОШИБКА при записи: {e}"

    lines_count = len(content.splitlines())
    return f"OK: создан {path} ({lines_count} строк)"


def edit_file(path: str, old: str, new: str) -> str:
    """Заменить фрагмент old на new в файле.

    old должен встречаться ровно ОДИН раз, иначе ошибка.
    """
    p = Path(path).expanduser()

    if not p.exists():
        return (
            f"ОШИБКА: файл не найден: {path}. "
            f"Для нового файла используй write_file."
        )
    if p.is_dir():
        return f"ОШИБКА: {path} — директория, не файл."

    try:
        content = p.read_text(encoding="utf-8")
    except Exception as e:
        return f"ОШИБКА при чтении: {e}"

    if not old:
        return "ОШИБКА: пустой фрагмент old — нечего искать."

    count = content.count(old)

    if count == 0:
        return (
            f"ОШИБКА: фрагмент old не найден в {path}.\n"
            f"Вероятно, отступы или пробелы отличаются от оригинала.\n"
            f"Прочитай файл заново через read_file и скопируй фрагмент "
            f"ТОЧНО как он есть, включая все отступы."
        )
    if count > 1:
        return (
            f"ОШИБКА: фрагмент old встречается {count} раз в {path}. "
            f"Добавь больше контекста (соседние строки), чтобы замена была "
            f"однозначной."
        )

    new_content = content.replace(old, new, 1)

    if not sys.stdin.isatty():
        return "ОШИБКА: подтверждение недоступно (stdin не терминал)."

    _print_preview(p, new_content, existed=True)

    if not _ask_confirm():
        return "ОТМЕНЕНО пользователем."

    backup_note = ""
    try:
        bp = backup_file(p)
        if bp:
            backup_note = f" (бэкап: {bp})"
    except Exception as e:
        return f"ОШИБКА при создании бэкапа: {e}"

    try:
        p.write_text(new_content, encoding="utf-8")
    except PermissionError:
        return f"ОШИБКА: нет прав на запись {path}"
    except Exception as e:
        return f"ОШИБКА при записи: {e}"

    return f"OK: {path} обновлён{backup_note}"


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
        description="Прочитать содержимое файла.",
        schema='<read_file path="путь/к/файлу" />',
        handler=read_file,
    ),
    "list_dir": Tool(
        name="list_dir",
        description="Показать содержимое директории.",
        schema='<list_dir path="путь/к/папке" />',
        handler=list_dir,
    ),
    "write_file": Tool(
        name="write_file",
        description=(
            "Создать НОВЫЙ файл. Если файл уже существует — будет ошибка, "
            "используй edit_file."
        ),
        schema=(
            '<write_file path="путь/к/новому/файлу">\n'
            'содержимое файла\n'
            '</write_file>'
        ),
        handler=write_file,
    ),
    "edit_file": Tool(
        name="edit_file",
        description=(
            "Изменить СУЩЕСТВУЮЩИЙ файл: заменить фрагмент old на new. "
            "Сначала ВСЕГДА читай файл через read_file, затем копируй old "
            "ДОСЛОВНО (со всеми отступами). old должен встречаться в файле "
            "ровно один раз."
        ),
        schema=(
            '<edit_file path="путь/к/файлу">\n'
            '<old>\n'
            'точный фрагмент из файла\n'
            '</old>\n'
            '<new>\n'
            'чем заменить\n'
            '</new>\n'
            '</edit_file>'
        ),
        handler=edit_file,
    ),
}


# --- Парсер вызовов ---

_SIMPLE_RE = re.compile(
    r'<(read_file|list_dir)\s+path="([^"]*)"\s*/?>',
    re.IGNORECASE,
)

_WRITE_RE = re.compile(
    r'<write_file\s+path="([^"]+)"\s*>\s*\n?(.*?)\n?\s*</write_file>',
    re.DOTALL | re.IGNORECASE,
)

_EDIT_RE = re.compile(
    r'<edit_file\s+path="([^"]+)"\s*>\s*'
    r'<old>\s*\n?(.*?)\n?\s*</old>\s*'
    r'<new>\s*\n?(.*?)\n?\s*</new>\s*'
    r'</edit_file>',
    re.DOTALL | re.IGNORECASE,
)


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Найти все вызовы инструментов в тексте модели."""
    calls: list[tuple[str, dict]] = []

    # edit_file — первым (сложнее, иначе могут пересечься с write)
    for m in _EDIT_RE.finditer(text):
        calls.append((
            "edit_file",
            {"path": m.group(1), "old": m.group(2), "new": m.group(3)},
        ))

    # write_file
    for m in _WRITE_RE.finditer(text):
        calls.append(("write_file", {"path": m.group(1), "content": m.group(2)}))

    # read_file / list_dir
    for m in _SIMPLE_RE.finditer(text):
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
    """Системная инструкция — какие инструменты есть и как их вызывать."""
    lines = [
        "## Инструменты",
        "",
        "Ты можешь вызывать инструменты, чтобы работать с файлами пользователя.",
        "",
    ]
    for t in TOOLS.values():
        lines.append(f"  {t.schema}")
        lines.append(f"     — {t.description}")
        lines.append("")
    lines += [
        "## Правила",
        "",
        "1. Посмотреть файл — read_file. Посмотреть папку — list_dir.",
        "2. Изменить СУЩЕСТВУЮЩИЙ файл — используй edit_file:",
        "   СНАЧАЛА прочитай файл через read_file, потом скопируй нужный фрагмент",
        "   в <old> ДОСЛОВНО (со всеми отступами), а в <new> — чем заменить.",
        "   Фрагмент <old> должен быть уникальным в файле, иначе ошибка.",
        "3. Создать НОВЫЙ файл — используй write_file с полным содержимым.",
        "4. Выводи тег БЕЗ обёрток вида ```xml, только чистый XML.",
        "5. После вызова инструмента придёт <result>...</result> — "
        "продолжи работу или ответь пользователю текстом (без тегов).",
        "6. Не выдумывай содержимое файлов. Не редактируй, не прочитав файл.",
    ]
    return "\n".join(lines)