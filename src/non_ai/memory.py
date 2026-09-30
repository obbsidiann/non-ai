"""История сессий non-ai."""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "non-ai"
SESSIONS_DIR = DATA_DIR / "sessions"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _gen_id() -> str:
    """ID вида 2026-09-30-1415-a1b2 — сортируется по времени."""
    ts = datetime.now().strftime("%Y-%m-%d-%H%M")
    suffix = secrets.token_hex(2)  # 4 hex-символа
    return f"{ts}-{suffix}"


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Session:
    id: str
    created: str
    updated: str
    model: str
    messages: list[Message] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return SESSIONS_DIR / f"{self.id}.json"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created": self.created,
            "updated": self.updated,
            "model": self.model,
            "messages": [asdict(m) for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            id=data["id"],
            created=data["created"],
            updated=data["updated"],
            model=data["model"],
            messages=[Message(**m) for m in data.get("messages", [])],
        )

    def preview(self, n: int = 60) -> str:
        """Первое сообщение пользователя для превью в списке."""
        for msg in self.messages:
            if msg.role == "user":
                text = msg.content.replace("\n", " ")
                return text[:n] + ("…" if len(text) > n else "")
        return "(пусто)"


class SessionStore:
    """Управление сессиями на диске."""

    def __init__(self, sessions_dir: Path = SESSIONS_DIR):
        self.dir = sessions_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def new(self, model: str, system_prompt: str) -> Session:
        now = _now_iso()
        return Session(
            id=_gen_id(),
            created=now,
            updated=now,
            model=model,
            messages=[Message(role="system", content=system_prompt)],
        )

    def save(self, session: Session) -> None:
        session.updated = _now_iso()
        tmp = session.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(session.path)

    def load(self, session_id: str) -> Session | None:
        path = self.dir / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Session.from_dict(data)
        except Exception:
            return None

    def latest(self) -> Session | None:
        sessions = self.list_sessions()
        if not sessions:
            return None
        return self.load(sessions[0].id)

    def list_sessions(self) -> list[Session]:
        """Все сессии, отсортированные по времени обновления (новые сверху)."""
        result: list[Session] = []
        for path in self.dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                result.append(Session.from_dict(data))
            except Exception:
                continue
        result.sort(key=lambda s: s.updated, reverse=True)
        return result