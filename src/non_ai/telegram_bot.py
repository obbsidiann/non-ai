"""Telegram-бот для non-ai (полный доступ ко всем инструментам)."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .agent import Agent
from .backups import diff_latest, format_all, restore
from .config import Config, save_telegram_config
from .memory import Message, Session, SessionStore, _now_iso
from .tools import set_tool_context, tools_prompt

log = logging.getLogger("non-ai.telegram")

MAX_MSG = 4000


def _split_message(text: str, limit: int = MAX_MSG) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


class NonAiTelegramBot:
    def __init__(self, config: Config):
        self.config = config
        self.store = SessionStore()
        self.sessions: dict[int, Agent] = {}
        self._lock = asyncio.Lock()

    def _is_allowed(self, user_id: int) -> bool:
        allowed = self.config.telegram_allowed_users
        return bool(allowed) and user_id in allowed

    async def _send_long(self, update: Update, text: str) -> None:
        if not text.strip():
            text = "(пустой ответ)"
        for chunk in _split_message(text):
            try:
                await update.message.reply_text(chunk, parse_mode=None)
            except Exception as e:
                log.exception("send error")
                try:
                    await update.message.reply_text(f"(ошибка отправки: {e})")
                except Exception:
                    pass

    def _get_or_create_agent(self, chat_id: int) -> Agent:
        agent = self.sessions.get(chat_id)
        if agent is not None:
            return agent

        sid = f"tg-{chat_id}"
        session = self.store.load(sid)
        if session is None:
            system = self.config.system_prompt
            system = system.rstrip() + "\n\n" + tools_prompt()
            now = _now_iso()
            session = Session(
                id=sid,
                created=now,
                updated=now,
                model=self.config.model,
                messages=[Message(role="system", content=system)],
            )
            self.store.save(session)

        agent = Agent(
            self.config,
            store=self.store,
            session=session,
            autosave=True,
            enable_tools=True,
            allowed_tools=None,
        )
        self.sessions[chat_id] = agent
        return agent

    def _run_agent_sync(self, agent: Agent, text: str) -> str:
        parts: list[str] = []
        for chunk in agent.ask(text):
            parts.append(chunk)
        return "".join(parts)

    # --- Handlers ---

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None:
            return

        if not self.config.telegram_allowed_users:
            self.config.telegram_allowed_users = [user.id]
            save_telegram_config(self.config.telegram_token, [user.id])
            await update.message.reply_text(
                f"👋 Привет, {user.first_name}!\n\n"
                f"Ты первый — я записал тебя как владельца.\n"
                f"Твой user_id: {user.id}\n"
                f"Сохранён в ~/.config/non-ai/telegram.toml\n\n"
                f"Рабочая директория: {Path.cwd()}\n\n"
                f"⚠️ В Telegram включено авто-подтверждение:\n"
                f"все правки и команды применяются сразу, но с бэкапом. "
                f"Откат — /undo <файл>.\n\n"
                f"Отправь /help для списка команд."
            )
        elif self._is_allowed(user.id):
            await update.message.reply_text(
                f"Привет снова, {user.first_name}!\n"
                f"Рабочая директория: {Path.cwd()}"
            )
        else:
            await update.message.reply_text(
                f"⛔ Ты не в списке.\nТвой user_id: {user.id}\n"
                f"Попроси владельца добавить тебя."
            )

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 non-ai — локальный ИИ-агент\n\n"
            "Команды:\n"
            "/start    — подключиться\n"
            "/help     — эта справка\n"
            "/new      — новая сессия\n"
            "/whoami   — показать user_id\n"
            "/backups  — файлы с историей правок\n"
            "/undo FILE — откатить файл\n"
            "/diff FILE — что изменилось\n\n"
            "Напиши вопрос — прочитаю / изменю файлы / выполню команду.\n\n"
            "⚠️ Авто-подтверждение: правки применяются сразу с бэкапом."
        )

    async def cmd_whoami(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user:
            await update.message.reply_text(
                f"user_id: {user.id}\nusername: @{user.username or '-'}"
            )

    async def cmd_new(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        agent = self.sessions.pop(chat_id, None)
        if agent is not None:
            try:
                p = agent.session.path
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        await update.message.reply_text("🆕 Новая сессия. Контекст очищен.")

    async def cmd_backups(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await self._send_long(update, format_all())

    async def cmd_undo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        args = ctx.args
        if not args:
            await update.message.reply_text("Использование: /undo FILE [TIMESTAMP]")
            return
        ts = args[1] if len(args) > 1 else None
        result = restore(args[0], ts)
        await self._send_long(update, result)

    async def cmd_diff(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        args = ctx.args
        if not args:
            await update.message.reply_text("Использование: /diff FILE")
            return
        result = diff_latest(args[0])
        await self._send_long(update, result)

    async def on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None:
            return

        if not self._is_allowed(user.id):
            await update.message.reply_text(
                f"⛔ Не авторизован. user_id: {user.id}\n"
                f"Пиши /start если ты первый."
            )
            return

        text = update.message.text or ""
        if not text.strip():
            return

        try:
            await update.message.chat.send_action(ChatAction.TYPING)
        except Exception:
            pass

        agent = self._get_or_create_agent(update.effective_chat.id)

        outputs: list[str] = []

        def collect(line: str) -> None:
            outputs.append(line)

        def auto_confirm() -> bool:
            return True

        async with self._lock:
            set_tool_context(output_cb=collect, confirm_cb=auto_confirm)
            loop = asyncio.get_running_loop()
            try:
                response = await loop.run_in_executor(
                    None, self._run_agent_sync, agent, text
                )
            except Exception as e:
                log.exception("agent error")
                await update.message.reply_text(f"❌ Ошибка: {e}")
                return
            finally:
                set_tool_context(output_cb=None, confirm_cb=None)

        tool_output = "".join(outputs).strip()
        if tool_output:
            for chunk in _split_message("🔧 Действия агента:\n\n" + tool_output):
                try:
                    await update.message.reply_text(chunk, parse_mode=None)
                except Exception:
                    pass

        await self._send_long(update, response)


def run_bot(config: Config) -> int:
    if not config.telegram_token:
        print(
            "Ошибка: токен Telegram не задан.\n"
            "Сначала запусти: non-ai --telegram-setup",
            file=sys.stderr,
        )
        return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    bot = NonAiTelegramBot(config)
    app = Application.builder().token(config.telegram_token).build()
    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("help", bot.cmd_help))
    app.add_handler(CommandHandler("whoami", bot.cmd_whoami))
    app.add_handler(CommandHandler("new", bot.cmd_new))
    app.add_handler(CommandHandler("backups", bot.cmd_backups))
    app.add_handler(CommandHandler("undo", bot.cmd_undo))
    app.add_handler(CommandHandler("diff", bot.cmd_diff))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.on_message)
    )

    log.info("Бот запущен. Рабочая директория: %s", Path.cwd())
    log.info("Владелец: %s", config.telegram_allowed_users)
    app.run_polling()
    return 0


def setup_interactive() -> int:
    print("Настройка Telegram-бота non-ai")
    print()
    print("1. Открой @BotFather в Telegram")
    print("2. Отправь /newbot и следуй инструкциям")
    print("3. Скопируй токен (вида 123456789:ABC-DEF1234567890)")
    print()

    try:
        token = input("Токен: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1

    if not token or ":" not in token or len(token) < 20:
        print("Похоже, это не токен. Отмена.", file=sys.stderr)
        return 1

    path = save_telegram_config(token, [])
    print()
    print(f"✅ Токен сохранён в {path}")
    print()
    print("Дальше:")
    print("  1. Запусти: non-ai --telegram")
    print("  2. В Telegram отправь боту /start")
    print("  3. Первый пользователь станет владельцем.")
    return 0