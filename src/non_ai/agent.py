"""Core agent logic — управляет диалогом и стримингом."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import ollama

from .config import Config


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


class Agent:
    def __init__(self, config: Config):
        self.config = config
        self.messages: list[Message] = [
            Message(role="system", content=config.system_prompt)
        ]

    def reset(self) -> None:
        """Очистить контекст, оставив системный промпт."""
        self.messages = [Message(role="system", content=self.config.system_prompt)]

    def ask(self, user_input: str) -> Iterator[str]:
        """Отправить запрос, вернуть генератор чанков ответа.

        История диалога обновляется автоматически.
        """
        self.messages.append(Message(role="user", content=user_input))

        stream = ollama.chat(
            model=self.config.model,
            messages=[{"role": m.role, "content": m.content} for m in self.messages],
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

        self.messages.append(Message(role="assistant", content=collected))