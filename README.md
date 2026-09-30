# non-ai

> Локальный ИИ-агент для программирования на базе **Ollama + Qwen2.5-Coder**.
> Работает полностью офлайн, без API-ключей и подписок.

[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-linux-FCC624?logo=linux&logoColor=black)](#требования)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Ollama](https://img.shields.io/badge/powered%20by-Ollama-black)](https://ollama.com/)

---

## Что это

`non-ai` — минималистичный CLI-агент, который живёт в твоём терминале и помогает с кодом, не отправляя ничего в интернет. Никаких OpenAI, Anthropic и прочих облаков — модель крутится локально на твоей машине.

Идея: сделать «карманного» ассистента, который всегда под рукой, знает контекст твоих файлов и не требует подписки.

---

## Возможности

- 🖥️ **Полностью локально** — никакие данные не покидают твою машину
- 💬 **Интерактивный чат** + одиночные запросы из терминала
- 📎 **Работа с файлами** — передавай агенту код через `-f` или `stdin`
- 🧠 **История сессий** — диалоги сохраняются между запусками
- 🌍 **Русский и английский** — модель отвечает на том языке, на котором спрашиваешь
- ⚙️ **Гибкая конфигурация** через `~/.config/non-ai/config.toml`
- 🐧 **Работает на любом Linux** — Arch, Debian, Ubuntu, Fedora, openSUSE

---

## Требования

- **Linux** (любой дистрибутив)
- **Python** 3.11 или новее
- **~2 ГБ** свободного места на диске (модель + venv)
- **~4 ГБ** оперативной памяти (для модели 1.5B)
- **Интернет** — только на этапе установки (для скачивания Ollama и модели)

GPU не обязателен. Модель `qwen2.5-coder:1.5b` нормально работает на CPU. Если есть NVIDIA или AMD GPU — Ollama подхватит автоматически и будет быстрее.

---

## Установка

```bash
git clone https://github.com/obbsidiann/non-ai.git
cd non-ai
./install.sh
```

Скрипт:

1. Проверит наличие Python 3.11+, curl и Ollama.
2. Установит Ollama (если его нет).
3. Запустит сервис Ollama в фоне.
4. Скачает модель `qwen2.5-coder:1.5b` (~1 ГБ).
5. Создаст виртуальное окружение и поставит `non-ai`.
6. Пропишет команду `non-ai` в `~/.local/bin`.
7. Добавит `~/.local/bin` в PATH (если ещё не там).

После завершения:

```bash
source ~/.bashrc      # или ~/.zshrc / config.fish
non-ai "привет"
```

> ⚠️ **Папку `non-ai` нельзя удалять или перемещать** после установки — там живёт venv, на который ссылается команда `non-ai`. Это стандартная практика (так же работают `nvm`, `pyenv`, `rustup`).

### Ручная установка (без install.sh)

Если хочешь всё контролировать сам:

```bash
git clone https://github.com/obbsidiann/non-ai.git
cd non-ai

python3 -m venv venv
source venv/bin/activate
python -m pip install -e .

# Установить Ollama (по желанию — любым способом)
sudo pacman -S ollama          # Arch
curl -fsSL https://ollama.com/install.sh | sh   # остальные

# Скачать модель
ollama pull qwen2.5-coder:1.5b

# Готово
./venv/bin/non-ai "напиши quicksort на python"
```

---

## Использование

### Интерактивный режим

```bash
non-ai
```

Внутри чата доступны команды:

| Команда | Что делает |
|---------|-----------|
| `/help` | Показать все команды |
| `/new` | Начать новую сессию |
| `/clear` | Очистить контекст текущей сессии |
| `/model <name>` | Сменить модель на лету |
| `/config` | Показать текущий конфиг |
| `/save` | Принудительно сохранить сессию |
| `exit` / `Ctrl+D` | Выйти |

### Одиночный запрос

```bash
non-ai "объясни, что такое замыкание в Python"
non-ai "напиши функцию для чтения CSV"
```

### Работа с файлами

Передать агенту один или несколько файлов:

```bash
non-ai -f src/main.py "найди баги"
non-ai -f main.py -f utils.py "есть ли дублирование логики?"
```

### Работа с пайпами

```bash
# Ревью git diff
git diff | non-ai --stdin "сделай ревью изменений"

# Объяснить файл из любой команды
cat README.md | non-ai --stdin "переведи на английский"

# Логи
journalctl -u ollama -n 100 | non-ai --stdin "что тут не так?"
```

### История сессий

```bash
non-ai --sessions                       # список всех сессий
non-ai --continue                       # продолжить последнюю
non-ai --resume 2026-09-30-1415-a1b2    # загрузить конкретную
non-ai --no-save "разовый вопрос"       # не сохранять
```

### Вся справка

```bash
non-ai --help
```

---

## Конфигурация

Файл `~/.config/non-ai/config.toml` создаётся автоматически командой:

```bash
non-ai --init-config
```

Содержимое по умолчанию:

```toml
[model]
name = "qwen2.5-coder:1.5b"

[generation]
temperature = 0.2
top_p = 0.9
num_predict = 1024

[ui]
lang = "ru"

[prompt]
system = """You are non-ai, a helpful coding assistant..."""
```

Все параметры можно переопределить флагами CLI:

```bash
non-ai --model qwen2.5-coder:7b --temperature 0.5 "…"
```

---

## Модели

По умолчанию используется `qwen2.5-coder:1.5b` — маленькая, быстрая, хорошо понимает русский.

Другие варианты (после `ollama pull <model>`):

| Модель | Размер | RAM | Когда брать |
|--------|--------|-----|-------------|
| `qwen2.5-coder:1.5b` | ~1 ГБ | ~3 ГБ | По умолчанию, для слабых машин |
| `qwen2.5-coder:7b`   | ~5 ГБ | ~8 ГБ | Заметно умнее, если есть RAM |
| `deepseek-coder:6.7b`| ~4 ГБ | ~8 ГБ | Альтернатива для кода |
| `llama3.2:3b`        | ~2 ГБ | ~5 ГБ | Для общих вопросов, не только кода |

Переключение:

```bash
non-ai --model qwen2.5-coder:7b
# или прямо в чате:
Вы: /model qwen2.5-coder:7b
```

---

## Обновление

```bash
cd non-ai
git pull
./venv/bin/python -m pip install -e .
```

Модель обновляется отдельно, если нужно:

```bash
ollama pull qwen2.5-coder:1.5b
```

---

## Удаление

```bash
# Убираем симлинк и PATH-запись (последнюю — вручную из ~/.bashrc)
rm ~/.local/bin/non-ai

# Удаляем папку с агентом
rm -rf ~/non-ai

# По желанию — удалить сохранённые сессии и конфиг
rm -rf ~/.local/share/non-ai ~/.config/non-ai

# По желанию — удалить модель
ollama rm qwen2.5-coder:1.5b
```

---

## Разработка

```bash
git clone https://github.com/obbsidiann/non-ai.git
cd non-ai

python3 -m venv venv
source venv/bin/activate
python -m pip install -e .

# Запускать без установки симлинка:
./venv/bin/non-ai "тестовый запрос"
```

### Структура проекта

```
non-ai/
├── install.sh              # скрипт установки
├── pyproject.toml          # метаданные пакета
├── README.md
└── src/
    └── non_ai/
        ├── __init__.py
        ├── __main__.py     # python -m non_ai
        ├── agent.py        # ядро: стриминг, работа с сессией
        ├── cli.py          # argparse-фронтенд
        ├── config.py       # загрузка конфига
        └── memory.py       # сохранение сессий на диск
```

### Идеи для развития

- [ ] Tools / function calling (агент читает и правит файлы сам)
- [ ] RAG — индексация проектов для контекстных ответов
- [ ] Режимы работы: `--mode chat|code|shell|explain`
- [ ] Цветной вывод через `rich`
- [ ] Автодополнение через `prompt_toolkit`
- [ ] AUR-пакет

---

## FAQ

**Модель отвечает не то / путается.**  
Маленькие модели (1.5B) иногда галлюцинируют. Попробуй `qwen2.5-coder:7b` — заметно умнее. Или переформулируй запрос по-английски.

**Работает ли без интернета?**  
Да, после установки. Интернет нужен только для скачивания Ollama и модели.

**Можно ли на macOS / Windows?**  
Пока нет — `install.sh` рассчитан на Linux. Но Python-часть кроссплатформенная, при желании можно поставить вручную.

**Как использовать свою модель?**  
`ollama pull <model>` и потом `non-ai --model <model>`. Или прописать в `~/.config/non-ai/config.toml`.

**Куда сохраняются сессии?**  
В `~/.local/share/non-ai/sessions/`. Каждая сессия — отдельный JSON.

---

## Лицензия

MIT — см. [LICENSE](LICENSE).

---

## Благодарности

- [Ollama](https://ollama.com/) — за удобный рантайм локальных LLM
- [Qwen](https://github.com/QwenLM/Qwen2.5-Coder) — за отличную маленькую модель
