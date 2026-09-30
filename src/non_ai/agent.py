"""Core agent logic — управляет диалогом и стримингом."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import ollama

from .config import Config
from .memory import Message, Session, SessionStore


class Agent:
    def __init__(
        self,
        config: Config,
        store: SessionStore | None = None,
        session: Session | None = None,
        autosave: bool = True,
    ):
        self.config = config
        self.store = store
        self.autosave = autosave and store is not None

        if session is not None:
            self.session = session
        elif store is not None:
            self.session = store.new(config.model, config.system_prompt)
        else:
            self.session = Session(
                id="ephemeral",
                created="",
                updated="",
                model=config.model,
                messages=[Message(role="system", content=config.system_prompt)],
            )

    @property
    def messages(self) -> list[Message]:
        return self.session.messages

    def reset(self) -> None:
        """Начать новую сессию с чистого листа."""
        if self.store is not None:
            self.session = self.store.new(self.config.model, self.config.system_prompt)
        else:
            self.session.messages = [
                Message(role="system", content=self.config.system_prompt)
            ]

    def ask(self, user_input: str) -> Iterator[str]:
        self.session.messages.append(Message(role="user", content=user_input))

        stream = ollama.chat(
            model=self.config.model,
            messages=[{"role": m.role, "content": m.content} for m in self.session.messages],
            stream=True,
            options={
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "num_predict": self.config.num_predict,
            },
        )

        collected = ""
        for chunk in stream:
            content = chunk["message"]["content"]
            collected += content
            yield content

        self.session.messages.append(Message(role="assistant", content=collected))
        self.session.model = self.config.model

        if self.autosave and self.store is not None:
            self.store.save(self.session)