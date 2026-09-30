#!/usr/bin/env bash
# non-ai installer — ставит Ollama, модель и сам агент.
# Использование: curl -fsSL <url>/install.sh | bash

set -euo pipefail

# --- Настройки ---
MODEL="qwen2.5-coder:1.5b"
INSTALL_DIR="$HOME/.local/share/non-ai"
BIN_DIR="$HOME/.local/bin"
SRC_REPO="${NON_AI_REPO:-https://github.com/YOUR-USER/non-ai.git}"
MIN_PYTHON="3.11"

# --- Красивый вывод ---
c_reset="\033[0m"
c_blue="\033[1;34m"
c_green="\033[1;32m"
c_yellow="\033[1;33m"
c_red="\033[1;31m"

log()  { echo -e "${c_blue}[non-ai]${c_reset} $*"; }
ok()   { echo -e "${c_green}✓${c_reset} $*"; }
warn() { echo -e "${c_yellow}!${c_reset} $*"; }
err()  { echo -e "${c_red}✗${c_reset} $*" >&2; }

# --- Проверки ---
require_linux() {
    if [[ "$(uname -s)" != "Linux" ]]; then
        err "Поддерживается только Linux (пока что)."
        exit 1
    fi
}

check_python() {
    log "Проверяю Python..."
    if ! command -v python3 >/dev/null 2>&1; then
        err "Python3 не найден. Установи его и запусти скрипт снова."
        err "  Arch:    sudo pacman -S python"
        err "  Debian:  sudo apt install python3 python3-venv"
        err "  Fedora:  sudo dnf install python3"
        exit 1
    fi

    local pyver
    pyver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
        err "Нужен Python >= $MIN_PYTHON, у тебя $pyver."
        exit 1
    fi
    ok "Python $pyver"
}

check_ollama() {
    log "Проверяю Ollama..."
    if command -v ollama >/dev/null 2>&1; then
        ok "Ollama уже установлен"
        return
    fi

    warn "Ollama не найден. Устанавливаю..."
    if command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm ollama
    elif command -v apt >/dev/null 2>&1; then
        curl -fsSL https://ollama.com/install.sh | sh
    elif command -v dnf >/dev/null 2>&1; then
        curl -fsSL https://ollama.com/install.sh | sh
    else
        curl -fsSL https://ollama.com/install.sh | sh
    fi
    ok "Ollama установлен"
}

start_ollama() {
    log "Запускаю сервис Ollama..."
    if systemctl is-active --quiet ollama 2>/dev/null; then
        ok "Сервис уже запущен"
    elif systemctl --user is-active --quiet ollama 2>/dev/null; then
        ok "Пользовательский сервис уже запущен"
    else
        sudo systemctl enable --now ollama 2>/dev/null \
            || (nohup ollama serve >/dev/null 2>&1 & sleep 2)
        ok "Сервис запущен"
    fi
}

pull_model() {
    log "Скачиваю модель $MODEL (может занять пару минут)..."
    ollama pull "$MODEL"
    ok "Модель готова"
}

install_agent() {
    log "Устанавливаю non-ai в $INSTALL_DIR..."

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log "Найдена существующая установка, обновляю..."
        git -C "$INSTALL_DIR" pull --quiet
    elif [[ -n "${NON_AI_LOCAL_SRC:-}" ]]; then
        # Локальная установка из склонированного репо (для разработки)
        cp -r "$NON_AI_LOCAL_SRC" "$INSTALL_DIR"
    else
        git clone --quiet --depth=1 "$SRC_REPO" "$INSTALL_DIR"
    fi

    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/python" -m pip install --quiet --upgrade pip
    "$INSTALL_DIR/venv/bin/python" -m pip install --quiet -e "$INSTALL_DIR"

    mkdir -p "$BIN_DIR"
    ln -sf "$INSTALL_DIR/venv/bin/non-ai" "$BIN_DIR/non-ai"
    ok "Агент установлен в $BIN_DIR/non-ai"
}

setup_shell() {
    local shell_rc=""
    case "${SHELL:-}" in
        */bash) shell_rc="$HOME/.bashrc" ;;
        */zsh)  shell_rc="$HOME/.zshrc" ;;
        *)      shell_rc="$HOME/.bashrc" ;;
    esac

    local marker="# non-ai agent (auto-added)"
    if grep -q "$marker" "$shell_rc" 2>/dev/null; then
        ok "PATH уже настроен в $shell_rc"
        return
    fi

    {
        echo ""
        echo "$marker"
        echo "export PATH=\"\$HOME/.local/bin:\$PATH\""
    } >> "$shell_rc"

    ok "Добавил ~/.local/bin в PATH ($shell_rc)"
}

final_message() {
    echo ""
    ok "Установка завершена!"
    echo ""
    echo "  Открой новый терминал или выполни:"
    echo "    source ~/.bashrc    # (или ~/.zshrc)"
    echo ""
    echo "  Пробуй:"
    echo "    non-ai \"напиши hello world на python\""
    echo "    non-ai                    # интерактивный режим"
    echo ""
}

# --- Запуск ---
main() {
    echo ""
    log "Установка non-ai"
    echo ""
    require_linux
    check_python
    check_ollama
    start_ollama
    pull_model
    install_agent
    setup_shell
    final_message
}

main "$@"
