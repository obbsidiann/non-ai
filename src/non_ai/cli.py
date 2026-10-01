"""CLI for non-ai."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .agent import Agent
from .config import CONFIG_FILE, Config
from .memory import Session, SessionStore


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="non-ai",
        description="Локальный ИИ-ассистент на базе Ollama.",
    )
    p.add_argument(
        "prompt",
        nargs="*",
        help="Одиночный запрос. Если пусто — интерактивный режим.",
    )
    p.add_argument("-m", "--model", help="Переопределить модель.")
    p.add_argument("-t", "--temperature", type=float, help="Переопределить temperature.")
    p.add_argument("-l", "--lang", choices=["ru", "en"], help="Язык ответов.")
    p.add_argument(
        "--init-config",
        action="store_true",
        help="Создать дефолтный конфиг в ~/.config/non-ai/config.toml и выйти.",
    )
    p.add_argument(
        "--show-config",
        action="store_true",
        help="Показать действующий конфиг и выйти.",
    )
    p.add_argument("--version", action="version", version=f"non-ai {__version__}")
    p.add_argument(
        "-f", "--file",
        action="append",
        default=[],
        metavar="PATH",
        help="Файл для передачи агенту. Можно указать несколько раз.",
    )
    p.add_argument(
        "--stdin",
        action="store_true",
        help="Прочитать вход из stdin (например: cat file.py | non-ai --stdin 'ревью').",
    )
    p.add_argument(
        "-c", "--continue",
        dest="continue_session",
        action="store_true",
        help="Продолжить последнюю сессию.",
    )
    p.add_argument(
        "--resume",
        metavar="SESSION_ID",
        help="Загрузить сессию по ID.",
    )
    p.add_argument(
        "--sessions",
        action="store_true",
        help="Показать список сессий и выйти.",
    )
    p.add_argument(
        "--no-save",
        action="store_true",
        help="Не сохранять сессию на диск.",
    )
    p.add_argument(
        "--no-tools",
        action="store_true",
        help="Отключить инструменты (агент просто отвечает текстом).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = Config.load()

    if args.init_config:
        path = config.ensure_config_file()
        print(f"Конфиг: {path}")
        return 0

    if args.model:
        config.model = args.model
    if args.temperature is not None:
        config.temperature = args.temperature
    if args.lang:
        config.lang = args.lang

    if args.show_config:
        _print_config(config)
        return 0

    # --- Инициализация хранилища сессий ---
    store = SessionStore()

    if args.sessions:
        _list_sessions(store)
        return 0

    session: Session | None = None
    if args.resume:
        session = store.load(args.resume)
        if session is None:
            print(f"[non-ai] Сессия {args.resume} не найдена.", file=sys.stderr)
            return 1
    elif args.continue_session:
        session = store.latest()
        if session is None:
            print("[non-ai] Сессий нет, начинаю новую.")
        else:
            print(
                f"[non-ai] Продолжаю сессию {session.id} "
                f"(сообщений: {len(session.messages) - 1})"
            )
    autosave = not args.no_save
    agent = Agent(
        config,
        store=store,
        session=session,
        autosave=autosave,
        enable_tools=not args.no_tools,
    )
    # --- Собираем контекст из файлов и/или stdin ---
    context_parts: list[str] = []

    for path_str in args.file:
        try:
            content = Path(path_str).read_text(encoding="utf-8")
            context_parts.append(f"### FILE: {path_str}\n```\n{content}\n```")
        except FileNotFoundError:
            print(f"[non-ai] Файл не найден: {path_str}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[non-ai] Не удалось прочитать {path_str}: {e}", file=sys.stderr)
            return 1

    if args.stdin:
        if sys.stdin.isatty():
            print("[non-ai] --stdin указан, но stdin пуст.", file=sys.stderr)
            return 1
        stdin_content = sys.stdin.read()
        context_parts.append(f"### STDIN\n```\n{stdin_content}\n```")

    # --- One-shot режим ---
    if args.prompt or context_parts:
        user_prompt = " ".join(args.prompt).strip() or "Проанализируй этот код."
        full_prompt = (
            "\n\n".join(context_parts) + f"\n\n### REQUEST\n{user_prompt}"
            if context_parts
            else user_prompt
        )
        try:
            for chunk in agent.ask(full_prompt):
                print(chunk, end="", flush=True)
            print()
        except KeyboardInterrupt:
            print()
            return 130
        except Exception as e:
            print(f"Ошибка: {e}", file=sys.stderr)
            return 1
        return 0

    # --- Интерактивный режим ---
    return _interactive(agent)


def _list_sessions(store: SessionStore) -> None:
    sessions = store.list_sessions()
    if not sessions:
        print("Сессий пока нет.")
        return
    print(f"Сессий: {len(sessions)}\n")
    for s in sessions:
        msgs = len([m for m in s.messages if m.role != "system"])
        print(f"  {s.id}  ({msgs} сообщ., модель: {s.model})")
        print(f"    {s.preview()}")
    print("\nПродолжить: non-ai --resume <id>")


def _interactive(agent: Agent) -> int:
    print(
        f"non-ai {__version__} | модель: {agent.config.model} | "
        f"сессия: {agent.session.id}"
    )
    print("Команды: /help, /new, /clear, /model <name>, /save, exit\n")

    while True:
        try:
            user_input = input("Вы: ")
        except (EOFError, KeyboardInterrupt):
            print("\nДо встречи!")
            _final_save(agent)
            return 0

        stripped = user_input.strip()
        if not stripped:
            continue

        if stripped.lower() in ("exit", "quit", "выход"):
            print("До встречи!")
            _final_save(agent)
            return 0

        if stripped.startswith("/"):
            if stripped == "/new":
                agent.reset()
                print(f"[новая сессия: {agent.session.id}]")
                continue
            _handle_command(stripped, agent)
            continue

        try:
            print("\nnon-ai: ", end="", flush=True)
            for chunk in agent.ask(user_input):
                print(chunk, end="", flush=True)
            print("\n")
        except KeyboardInterrupt:
            print("\n[прервано]\n")
            continue
        except Exception as e:
            print(f"\nОшибка: {e}", file=sys.stderr)
            continue


def _final_save(agent: Agent) -> None:
    if agent.autosave and agent.store is not None:
        try:
            agent.store.save(agent.session)
        except Exception:
            pass


def _handle_command(cmd: str, agent: Agent) -> None:
    name = cmd.split(maxsplit=1)[0].lower()

    if name in ("/help", "/?"):
        print("Команды:")
        print("  /help          — эта справка")
        print("  /new           — начать новую сессию")
        print("  /clear         — очистить контекст текущей сессии")
        print("  /config        — показать конфиг")
        print("  /model <name>  — сменить модель на лету")
        print("  /save          — принудительно сохранить")
        print("  exit           — выйти")
    elif name == "/clear":
        agent.reset()
        print("[контекст очищен]")
    elif name == "/config":
        _print_config(agent.config)
    elif name == "/model":
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            print("Использование: /model <name>")
            return
        agent.config.model = parts[1].strip()
        agent.session.model = agent.config.model
        print(f"[модель: {agent.config.model}]")
    elif name == "/save":
        if agent.store is None:
            print("[сохранение отключено]")
            return
        agent.store.save(agent.session)
        print(f"[сохранено: {agent.session.id}]")
    else:
        print(f"Неизвестная команда: {name}. Набери /help.")


def _print_config(config: Config) -> None:
    d = config.as_dict()
    for key, value in d.items():
        if key == "system_prompt":
            preview = value[:60] + "..." if len(value) > 60 else value
            print(f"{key}: {preview!r}")
        else:
            print(f"{key}: {value}")
    print(f"config_file: {CONFIG_FILE} (exists={CONFIG_FILE.exists()})")


if __name__ == "__main__":
    sys.exit(main())