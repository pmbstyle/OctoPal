#!/usr/bin/env bash
set -euo pipefail

install_nodejs_with_available_manager() {
  if command -v npm >/dev/null 2>&1; then
    if command -v node >/dev/null 2>&1; then
      local current_major
      current_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
      if [[ "$current_major" =~ ^[0-9]+$ ]] && (( current_major >= 20 )); then
        return 0
      fi
    fi
  fi

  echo "Node.js 20+ and npm are required. Installing/upgrading..."

  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | sudo tee /etc/apt/sources.list.d/nodesource.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y nodejs
  elif command -v dnf >/dev/null 2>&1; then
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo dnf install -y nodejs
  elif command -v yum >/dev/null 2>&1; then
    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
    sudo yum install -y nodejs
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm nodejs npm
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper --non-interactive install nodejs npm
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add --no-cache nodejs npm
  elif command -v brew >/dev/null 2>&1; then
    brew install node
  else
    echo "Could not auto-install Node.js/npm: no supported package manager was found." >&2
    echo "Install Node.js 20+ and npm, then rerun ./scripts/bootstrap.sh." >&2
    exit 1
  fi

  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "Node.js/npm installation did not make node and npm available on PATH." >&2
    echo "Open a new shell or add Node.js to PATH, then rerun ./scripts/bootstrap.sh." >&2
    exit 1
  fi

  local installed_major
  installed_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  if [[ ! "$installed_major" =~ ^[0-9]+$ ]] || (( installed_major < 20 )); then
    echo "Node.js 20 or newer is required, but found $(node --version 2>/dev/null || echo unknown)." >&2
    exit 1
  fi
}

if [[ ! -f "pyproject.toml" ]]; then
  echo "Run this script from the repository root (pyproject.toml not found)." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

if ! command -v uv >/dev/null 2>&1; then
  if [[ -f "$HOME/.local/bin/env" ]]; then
    # shellcheck source=/dev/null
    source "$HOME/.local/bin/env"
  fi
fi

# Ensure ~/.local/bin is in PATH persistently
UV_BIN_DIR="$HOME/.local/bin"
if [[ -d "$UV_BIN_DIR" ]] && [[ ":$PATH:" != *":$UV_BIN_DIR:"* ]]; then
  SHELL_CONFIG=""
  if [[ "$SHELL" == */zsh ]]; then
    SHELL_CONFIG="$HOME/.zshrc"
  elif [[ "$SHELL" == */bash ]]; then
    SHELL_CONFIG="$HOME/.bashrc"
  fi

  if [[ -n "$SHELL_CONFIG" ]]; then
    if ! grep -q "$UV_BIN_DIR" "$SHELL_CONFIG" 2>/dev/null; then
      echo "Adding $UV_BIN_DIR to PATH in $SHELL_CONFIG"
      echo "export PATH=\"\$PATH:$UV_BIN_DIR\"" >> "$SHELL_CONFIG"
    fi
  fi
  export PATH="$PATH:$UV_BIN_DIR"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is still not available on PATH." >&2
  echo "Run: source \"$HOME/.local/bin/env\"  and retry." >&2
  exit 1
fi

echo "Using $(uv --version)"
uv sync

echo "Installing Playwright browser binaries..."
uv run playwright install chromium

install_nodejs_with_available_manager

echo "Installing WhatsApp bridge dependencies..."
(
  cd scripts/whatsapp_bridge
  npm install
)

echo
echo "Launching onboarding..."
uv run octopal configure

echo
echo "Bootstrap complete."
echo "Next steps:"
echo "  uv run octopal start"
