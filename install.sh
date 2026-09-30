#!/usr/bin/env bash
# non-ai installer
#
# Устанавливает Ollama, скачивает модель и ставит агент из ТЕКУЩЕЙ папки.
#
# Использование:
#   git clone https://github.com/obbsidiann/non-ai.git
#   cd non-ai
#   ./install.sh

set -euo pipefail

# --- Настройки ---
MODEL="${NON_AI_MODEL:-qwen2.5-coder:1.5b}"
BIN_DIR="$HOME/.local/bin"
MIN_PYTHON="3.11"

# --- Цветной вывод (только если в терминале) ---
if [[ -t 1 ]]; then
    c_reset="\033[0m"; c_blue="\033[1;34m"; c_green="\033[1;32m"
    c_yellow="\033[1;33m"; c_red="\033[1;31m"; c_bold="\033[1m"
else
    c_reset=""; c_blue=""; c_green=""; c_yellow=""; c_red=""; c_bold=""
fi

log()  { echo -e "${c_blue}[non-ai]${c_reset} $*"; }
ok()   { echo -e "${c_green}  ✓${c_reset} $*"; }
warn() { echo -e "${c_yellow}  !${c_reset} $*"; }
err()  { echo -e "${c_red}  ✗${c_reset} $*" >&2; }
die()  { err "$*"; exit 1; }

# --- Проверка, что мы в корне репозитория ---
check_repo_root() {
    if [[ ! -f "pyproject.toml" || ! -d "src/non_ai" ]]; then
        die "Этот скрипт нужно запускать из корня репозитория non-ai."
        die "Сделай так:"
        die "  git clone https://github.com/obbsidiann/non-ai.git"
        die "  cd non-ai"
        die "  ./install.sh"
    fi
}

# --- Проверки системы ---
require_linux() {
    if [[ "$(uname -s)" != "Linux" ]]; then
        die "Поддерживается только Linux. На macOS/Windows ставь вручную (см. README)."
    fi
}

check_command() {
    local cmd="$1" hint="$2"
    command -v "$cmd" >/dev/null 2>&1 || die "Не найдена команда: $cmd. Установи: $hint"
}

check_deps() {
    log "Проверяю системные зависимости..."
    check_command python3 "Arch: sudo pacman -S python | Debian: sudo apt install python3 python3-venv | Fedora: sudo dnf install python3"
    check_command curl    "Arch: sudo pacman -S curl   | Debian: sudo apt install curl                 | Fedora: sudo dnf install curl"
    ok "python3, curl"
}

check_python() {
    log "Проверяю версию Python..."

    local pyver
    pyver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        die "Нужен Python >= $MIN_PYTHON, у тебя $pyver."
    fi

    # Модуль venv — на Debian/Ubuntu отдельный пакет
    if ! python3 -m venv --help >/dev/null 2>&1; then
        err "Модуль venv недоступен. Установи:"
        err "  Debian/Ubuntu: sudo apt install python3-venv"
        err "  Fedora:        sudo dnf install python3"
        exit 1
    fi

    ok "Python $pyver (с venv)"
}

# --- Ollama ---
check_ollama() {
    log "Проверяю Ollama..."
    if command -v ollama >/dev/null 2>&1; then
        ok "Ollama: $(ollama --version 2>/dev/null | head -1 || echo 'уже установлен')"
        return
    fi

    warn "Ollama не найден, устанавливаю..."
    if command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm ollama
    else
        # Официальный скрипт — работает на Debian/Ubuntu/Fedora/RHEL/openSUSE
        curl -fsSL https://ollama.com/install.sh | sh
    fi
    ok "Ollama установлен"
}

start_ollama() {
    log "Проверяю, отвечает ли сервер Ollama..."

    # 1. Уже запущен?
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        ok "Сервер слушает 127.0.0.1:11434"
        return
    fi

    # 2. Пробуем системный systemd-сервис
    if systemctl list-unit-files 2>/dev/null | grep -q '^ollama\.service'; then
        sudo systemctl enable --now ollama 2>/dev/null || true
        sleep 2
    fi

    # 3. Если всё ещё не отвечает — запускаем вручную в фоне
    if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        warn "Сервис не поднялся, запускаю 'ollama serve' в фоне..."
        nohup ollama serve >/dev/null 2>&1 &
        sleep 3
    fi

    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        ok "Ollama готов"
    else
        die "Ollama не отвечает на 127.0.0.1:11434. Проверь: journalctl -u ollama -n 50"
    fi
}

pull_model() {
    log "Скачиваю модель $MODEL (~1 ГБ, может занять пару минут)..."
    ollama pull "$MODEL"
    ok "Модель готова"
}

# --- Установка non-ai в текущую папку ---
install_agent() {
    local repo_dir
    repo_dir="$(pwd)"
    log "Устанавливаю non-ai из $repo_dir..."

    # venv в текущей папке
    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
        ok "Создан venv"
    else
        ok "venv уже существует"
    fi

    ./venv/bin/python -m pip install --quiet --upgrade pip
    ./venv/bin/python -m pip install --quiet -e .

    if [[ ! -x "$repo_dir/venv/bin/non-ai" ]]; then
        die "Установка не удалась: не создан venv/bin/non-ai"
    fi
    ok "Пакет установлен в venv"
}

# --- Симлинк в ~/.local/bin ---
link_binary() {
    mkdir -p "$BIN_DIR"
    ln -sf "$(pwd)/venv/bin/non-ai" "$BIN_DIR/non-ai"
    ok "Симлинк: $BIN_DIR/non-ai → $(pwd)/venv/bin/non-ai"
}

# --- PATH в rc-файле пользователя ---
setup_shell() {
    local shell_name shell_rc
    shell_name="$(basename "${SHELL:-bash}")"

    case "$shell_name" in
        bash) shell_rc="$HOME/.bashrc" ;;
        zsh)  shell_rc="$HOME/.zshrc" ;;
        fish) shell_rc="$HOME/.config/fish/config.fish" ;;
        *)    shell_rc="$HOME/.bashrc" ;;
    esac

    if [[ "$shell_name" == "fish" ]]; then
        mkdir -p "$(dirname "$shell_rc")"
        if grep -q 'non-ai agent' "$shell_rc" 2>/dev/null; then
            ok "PATH уже настроен в $shell_rc"
            return
        fi
        {
            echo ""
            echo "# non-ai agent (auto-added)"
            echo "fish_add_path \$HOME/.local/bin"
        } >> "$shell_rc"
        ok "PATH настроен в $shell_rc"
        return
    fi

    if grep -q 'non-ai agent' "$shell_rc" 2>/dev/null; then
        ok "PATH уже настроен в $shell_rc"
        return
    fi

    # Если пользователь уже добавлял ~/.local/bin — не дублируем
    if grep -q '\.local/bin' "$shell_rc" 2>/dev/null; then
        ok "~/.local/bin уже в PATH ($shell_rc)"
        return
    fi

    {
        echo ""
        echo "# non-ai agent (auto-added)"
        echo 'export PATH="$HOME/.local/bin:$PATH"'
    } >> "$shell_rc"
    ok "PATH настроен в $shell_rc"
}

# --- Финальное сообщение ---
final_message() {
    local shell_name rc_file
    shell_name="$(basename "${SHELL:-bash}")"
    case "$shell_name" in
        zsh)  rc_file="~/.zshrc" ;;
        fish) rc_file="~/.config/fish/config.fish" ;;
        *)    rc_file="~/.bashrc" ;;
    esac

    echo ""
    echo -e "${c_green}${c_bold}═══════════════════════════════════════════════${c_reset}"
    echo -e "${c_green}${c_bold}  non-ai успешно установлен!${c_reset}"
    echo -e "${c_green}${c_bold}═══════════════════════════════════════════════${c_reset}"
    echo ""
    echo "  Активировать PATH в текущем терминале:"
    echo -e "    ${c_blue}source $rc_file${c_reset}"
    echo "  (или просто открой новый терминал)"
    echo ""
    echo "  Попробуй:"
    echo -e "    ${c_blue}non-ai \"напиши hello world на python\"${c_reset}"
    echo -e "    ${c_blue}non-ai${c_reset}                              # интерактивный режим"
    echo -e "    ${c_blue}non-ai --help${c_reset}                       # вся справка"
    echo ""
    echo "  Обновить в будущем:"
    echo -e "    ${c_blue}cd $(pwd) && git pull && ./venv/bin/python -m pip install -e .${c_reset}"
    echo ""
    echo "  Репозиторий: https://github.com/obbsidiann/non-ai"
    echo ""
}

# --- Запуск ---
main() {
    echo ""
    log "Установка non-ai"
    echo ""
    check_repo_root
    require_linux
    check_deps
    check_python
    check_ollama
    start_ollama
    pull_model
    install_agent
    link_binary
    setup_shell
    final_message
}

main "$@"