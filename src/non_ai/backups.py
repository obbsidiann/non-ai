"""Управление бэкапами non-ai (CLI-команды)."""
from __future__ import annotations

import difflib
import hashlib
import shutil
from pathlib import Path

from .tools import BACKUP_DIR, backup_file, _load_index


def _file_hash(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:12]


def _backups_for(path: Path) -> list[Path]:
    d = BACKUP_DIR / _file_hash(path)
    if not d.exists():
        return []
    return sorted(d.glob("*.bak"))


def format_all() -> str:
    """Показать все файлы, для которых есть бэкапы."""
    index = _load_index()
    if not index:
        return "Бэкапов пока нет.\nОни появятся после первого edit_file."

    items = []
    for file_hash, orig_path in index.items():
        d = BACKUP_DIR / file_hash
        if not d.exists():
            continue
        backups = sorted(d.glob("*.bak"))
        if not backups:
            continue
        latest_mtime = backups[-1].stat().st_mtime
        items.append((latest_mtime, orig_path, len(backups), backups[-1].name))

    if not items:
        return "Бэкапов пока нет."

    items.sort(reverse=True)

    lines = [f"📦 Файлов с бэкапами: {len(items)}", ""]
    for _, orig_path, count, last_name in items:
        ts = last_name.replace(".bak", "")
        lines.append(f"  {count:>3} версий  {orig_path}")
        lines.append(f"              последний: {ts}")
    lines.append("")
    lines.append(f"Подробнее о файле:  non-ai --backups-for <FILE>")
    lines.append(f"Восстановить:       non-ai --restore <FILE> [TIMESTAMP]")
    return "\n".join(lines)


def format_one(path_str: str) -> str:
    path = Path(path_str).expanduser()
    backups = _backups_for(path)

    if not backups:
        return f"Бэкапов для {path} нет."

    lines = [f"📦 Бэкапы {path} ({len(backups)} версий):", ""]
    for b in reversed(backups):
        ts = b.name.replace(".bak", "")
        size = b.stat().st_size
        lines.append(f"  {ts}  ({size} байт)")

    lines.append("")
    lines.append(f"  Восстановить последнюю:   non-ai --restore {path}")
    lines.append(f"  Восстановить конкретную:  non-ai --restore {path} <TIMESTAMP>")
    lines.append(f"  Diff с последней:         non-ai --diff-backup {path}")
    return "\n".join(lines)


def restore(path_str: str, timestamp: str | None = None) -> str:
    path = Path(path_str).expanduser()
    backups = _backups_for(path)

    if not backups:
        return f"Бэкапов для {path} нет."

    if timestamp:
        candidates = [b for b in backups if timestamp in b.name]
        if not candidates:
            names = [b.name for b in backups]
            return (
                f"Бэкап с '{timestamp}' не найден.\n"
                f"Доступные: {names}"
            )
        target = candidates[-1]
    else:
        target = backups[-1]

    # Сохраняем текущее состояние перед восстановлением
    if path.exists():
        backup_file(path)

    try:
        shutil.copy2(target, path)
    except Exception as e:
        return f"ОШИБКА при восстановлении: {e}"

    return f"✅ {path} восстановлен из {target.name}"


def diff_latest(path_str: str) -> str:
    path = Path(path_str).expanduser()
    backups = _backups_for(path)

    if not backups:
        return f"Бэкапов для {path} нет."

    if not path.exists():
        return f"ОШИБКА: {path} не существует (только бэкапы)."

    last = backups[-1]
    try:
        old = last.read_text(encoding="utf-8").splitlines(keepends=True)
        new = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except Exception as e:
        return f"ОШИБКА: {e}"

    diff = list(difflib.unified_diff(
        old, new,
        fromfile=f"backup/{last.name}",
        tofile=f"current/{path.name}",
        n=2,
    ))

    if not diff:
        return f"{path} идентичен последнему бэкапу."

    # Цветной вывод
    lines = []
    for line in diff:
        line = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            lines.append(f"\033[1m{line}\033[0m")
        elif line.startswith("@@"):
            lines.append(f"\033[36m{line}\033[0m")
        elif line.startswith("+"):
            lines.append(f"\033[32m{line}\033[0m")
        elif line.startswith("-"):
            lines.append(f"\033[31m{line}\033[0m")
        else:
            lines.append(line)

    return "\n".join(lines)