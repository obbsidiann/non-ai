"""Configuration loader for non-ai."""
from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "non-ai"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_MODEL = "qwen2.5-coder:1.5b"

DEFAULT_SYSTEM_PROMPT = (
    "You are non-ai, a helpful coding assistant. "
    "Answer concisely. When asked to write code, provide the code first, "
    "then a brief explanation. Use markdown code blocks."
)

DEFAULT_CONFIG_TOML = '''# non-ai configuration file
# Location: ~/.config/non-ai/config.toml

[model]
# Имя модели в Ollama (проверить: `ollama list`)
name = "qwen2.5-coder:1.5b"

[generation]
temperature = 0.2
top_p = 0.9
num_predict = 1024

[ui]
# Язык ответов: "ru" или "en"
lang = "ru"

[prompt]
# Системный промпт для модели
system = """You are non-ai, a helpful coding assistant. Answer concisely. When asked to write code, provide the code first, then a brief explanation. Use markdown code blocks."""
'''


@dataclass
class Config:
    model: str = DEFAULT_MODEL
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    temperature: float = 0.2
    top_p: float = 0.9
    num_predict: int = 1024
    lang: str = "ru"

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_FILE.exists():
            return cls()
        try:
            with CONFIG_FILE.open("rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            print(f"[non-ai] Не удалось прочитать {CONFIG_FILE}: {e}")
            return cls()
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Config":
        model_cfg = data.get("model", {})
        gen_cfg = data.get("generation", {})
        ui_cfg = data.get("ui", {})
        prompt_cfg = data.get("prompt", {})

        return cls(
            model=model_cfg.get("name", DEFAULT_MODEL),
            system_prompt=prompt_cfg.get("system", DEFAULT_SYSTEM_PROMPT),
            temperature=float(gen_cfg.get("temperature", 0.2)),
            top_p=float(gen_cfg.get("top_p", 0.9)),
            num_predict=int(gen_cfg.get("num_predict", 1024)),
            lang=str(ui_cfg.get("lang", "ru")),
        )

    def ensure_config_file(self) -> Path:
        """Создаёт дефолтный конфиг, если его нет. Возвращает путь."""
        if CONFIG_FILE.exists():
            return CONFIG_FILE
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
        return CONFIG_FILE

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)