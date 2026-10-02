"""Core agent logic — управляет диалогом и стримингом."""
from __future__ import annotations

import re
from typing import Iterator

import ollama

from .config import Config
from .memory import Message, Session, SessionStore
from .tools import execute_tool, parse_tool_calls, tools_prompt


_TOOL_TAG_RE = re.compile(
    r"```(?:xml|XML)?\s*\n?"
    r"|```\s*\n?"
    r"|</?(?:read_file|list_dir|create_dir|write_file|edit_file|run_shell)\b[^>]*/?>",
    re.IGNORECASE,
)

_WRITE_BLOCK_RE = re.compile(
    r'<write_file\s+path="[^"]+"\s*>.*?</write_file>',
    re.DOTALL | re.IGNORECASE,
)

_EDIT_BLOCK_RE = re.compile(
    r'<edit_file\s+path="[^"]+"\s*>.*?</edit_file>',
    re.DOTALL | re.IGNORECASE,
)

_RUN_SHELL_BLOCK_RE = re.compile(
    r'<run_shell\s*>.*?</run_shell>',
    re.DOTALL | re.IGNORECASE,
)

_FAKE_RESULT_RE = re.compile(
    r'<result\b[^>]*>.*?</result>',
    re.DOTALL | re.IGNORECASE,
)


def _clean_display(text: str) -> str:
    cleaned = _EDIT_BLOCK_RE.sub("", text)
    cleaned = _WRITE_BLOCK_RE.sub("", cleaned)
    cleaned = _RUN_SHELL_BLOCK_RE.sub("", cleaned)
    cleaned = _FAKE_RESULT_RE.sub("", cleaned)
    cleaned = _TOOL_TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


class Agent:
    MAX_TOOL_ITERATIONS = 6

    def __init__(
        self,
        config: Config,
        store: SessionStore | None = None,
        session: Session | None = None,
        autosave: bool = True,
        enable_tools: bool = True,
        allowed_tools: set[str] | None = None,
    ):
        self.config = config
        self.store = store
        self.autosave = autosave and store is not None
        self.enable_tools = enable_tools
        self.allowed_tools = allowed_tools  # None = все разрешены

        system = config.system_prompt
        if enable_tools:
            system = system.rstrip() + "\n\n" + tools_prompt()

        if session is not None:
            self.session = session
            if self.session.messages and self.session.messages[0].role == "system":
                self.session.messages[0].content = system
        elif store is not None:
            self.session = store.new(config.model, system)
        else:
            self.session = Session(
                id="ephemeral",
                created="",
                updated="",
                model=config.model,
                messages=[Message(role="system", content=system)],
            )

    @property
    def messages(self) -> list[Message]:
        return self.session.messages

    def reset(self) -> None:
        system = self.config.system_prompt
        if self.enable_tools:
            system = system.rstrip() + "\n\n" + tools_prompt()

        if self.store is not None:
            self.session = self.store.new(self.config.model, system)
        else:
            self.session.messages = [Message(role="system", content=system)]

    def ask(self, user_input: str, allow_tools: bool = True) -> Iterator[str]:
        self.session.messages.append(Message(role="user", content=user_input))

        iterations = self.MAX_TOOL_ITERATIONS if allow_tools else 1
        seen_calls: set[str] = set()
        fake_result_retries = 0
        MAX_FAKE_RETRIES = 2

        for _ in range(iterations):
            stream = ollama.chat(
                model=self.config.model,
                messages=[
                    {"role": m.role, "content": m.content}
                    for m in self.session.messages
                ],
                stream=True,
                options={
                    "temperature": self.config.temperature,
                    "top_p": self.config.top_p,
                    "num_predict": self.config.num_predict,
                },
            )

            collected = ""
            for chunk in stream:
                collected += chunk["message"]["content"]

            self.session.messages.append(Message(role="assistant", content=collected))

            if not allow_tools:
                yield _clean_display(collected)
                break

            calls = parse_tool_calls(collected)
            if not calls:
                had_fake_result = bool(_FAKE_RESULT_RE.search(collected))
                if had_fake_result and fake_result_retries < MAX_FAKE_RETRIES:
                    fake_result_retries += 1
                    self.session.messages.append(
                        Message(
                            role="user",
                            content=(
                                "## ОШИБКА СИСТЕМЫ\n"
                                "Ты написал <result> сам — это запрещено. "
                                "<result> приходит ТОЛЬКО от системы. "
                                "Если нужна информация — вызови инструмент. "
                                "Попробуй ещё раз."
                            ),
                        )
                    )
                    continue

                yield _clean_display(collected)
                break

            # Отсеиваем повторы + whitelist
            new_calls: list[tuple[str, dict]] = []
            blocked: list[str] = []
            for name, args in calls:
                if self.allowed_tools is not None and name not in self.allowed_tools:
                    blocked.append(name)
                    continue
                key = f"{name}:{args.get('path', '') or args.get('cmd', '')}"
                if key in seen_calls:
                    continue
                seen_calls.add(key)
                new_calls.append((name, args))

            if not new_calls and not blocked:
                yield "\n[non-ai] Повторный вызов, останавливаюсь.\n"
                break

            for name, args in new_calls:
                if name in ("write_file", "edit_file", "create_dir", "run_shell"):
                    continue
                path = args.get("path", "")
                yield f"\n  ⚙  {name}({path})\n"

            results: list[str] = []
            for name in blocked:
                results.append(
                    f'<result tool="{name}">\n'
                    f'ОШИБКА: инструмент {name} недоступен в текущем режиме.\n'
                    f'</result>'
                )
            for name, args in new_calls:
                result = execute_tool(name, args)
                results.append(f'<result tool="{name}">\n{result}\n</result>')

            hint = (
                "\n\n## ВАЖНО\n"
                "Ответь пользователю текстом на основе результатов. "
                "НЕ вызывай инструменты повторно. "
                "Не оборачивай вызовы в ```xml."
            )
            self.session.messages.append(
                Message(role="user", content="\n\n".join(results) + hint)
            )

        self.session.model = self.config.model
        if self.autosave and self.store is not None:
            self.store.save(self.session)