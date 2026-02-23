#!/usr/bin/env bash
# Harness installer — curl -fsSL https://raw.githubusercontent.com/AgentBoardTT/openharness/main/install.sh | bash
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
RESET="\033[0m"

info()  { printf "${BOLD}%s${RESET}\n" "$*"; }
ok()    { printf "${GREEN}%s${RESET}\n" "$*"; }
warn()  { printf "${YELLOW}%s${RESET}\n" "$*"; }
err()   { printf "${RED}%s${RESET}\n" "$*" >&2; }

# --- OS check ---
OS="$(uname -s)"
case "$OS" in
    Linux|Darwin) ;;
    MINGW*|MSYS*|CYGWIN*)
        err "Windows is not supported by this installer."
        err "Please install with:  pip install harness-agent"
        exit 1
        ;;
    *)
        err "Unsupported OS: $OS"
        exit 1
        ;;
esac

info "Installing Harness on $OS..."

# --- Install uv if missing ---
if ! command -v uv &>/dev/null; then
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Source the env so uv is available in this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        err "uv installation succeeded but 'uv' is not on PATH."
        err "Add ~/.local/bin to your PATH and re-run this installer."
        exit 1
    fi
    ok "uv installed"
else
    ok "uv already installed ($(uv --version))"
fi

# --- Install harness ---
info "Installing harness-agent..."
uv tool install --python 3.12 harness-agent

# --- Verify ---
if command -v harness &>/dev/null; then
    ok "harness installed successfully! ($(harness --version 2>/dev/null || echo 'ok'))"
else
    # uv tool bin may not be on PATH yet
    warn "'harness' is not on PATH yet."
    echo "Add the uv tool bin directory to your PATH:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "Then open a new terminal or run:  source ~/.bashrc  (or ~/.zshrc)"
    exit 0
fi

echo ""
ok "All done!"
info "Run 'harness' to get started, then type '/connect' to set up your API key."
