"""CLI for non-ai."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .agent import Agent
from .config import CONFIG_FILE, Config


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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = Config.load()

    if args.init_config:
        path = config.ensure_config_file()
        print(f"Конфиг: {path}")
        return 0

    # CLI overrides
    if args.model:
        config.model = args.model
    if args.temperature is not None:
        config.temperature = args.temperature
    if args.lang:
        config.lang = args.lang

    if args.show_config:
        _print_config(config)
        return 0

    agent = Agent(config)

    # One-shot режим
    if args.prompt:
        prompt = " ".join(args.prompt)
        try:
            for chunk in agent.ask(prompt):
                print(chunk, end="", flush=True)
            print()
        except KeyboardInterrupt:
            print()
            return 130
        except Exception as e:
            print(f"Ошибка: {e}", file=sys.stderr)
            return 1
        return 0

    # Интерактивный режим
    return _interactive(agent)


def _interactive(agent: Agent) -> int:
    print(f"non-ai {__version__} | модель: {agent.config.model}")
    print("Введите '/help' для команд, 'exit' или Ctrl+D для выхода.\n")

    while True:
        try:
            user_input = input("Вы: ")
        except (EOFError, KeyboardInterrupt):
            print("\nДо встречи!")
            return 0

        stripped = user_input.strip()
        if not stripped:
            continue

        if stripped.lower() in ("exit", "quit", "выход"):
            print("До встречи!")
            return 0

        if stripped.startswith("/"):
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


def _handle_command(cmd: str, agent: Agent) -> None:
    name = cmd.split(maxsplit=1)[0].lower()

    if name in ("/help", "/?"):
        print("Команды:")
        print("  /help          — эта справка")
        print("  /clear         — очистить контекст диалога")
        print("  /config        — показать действующий конфиг")
        print("  /model <name>  — сменить модель на лету")
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
        print(f"[модель: {agent.config.model}]")
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