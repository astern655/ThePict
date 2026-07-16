#!/usr/bin/env bash
set -euo pipefail

# Installs user-local tooling only. It does not use sudo or change Windows settings.
NODE_VERSION="v22.11.0"
NODE_DIR="$HOME/.local/node-$NODE_VERSION"
LOCAL_BIN="$HOME/.local/bin"
NPM_PREFIX="$HOME/.local/npm-global"

mkdir -p "$HOME/.local" "$LOCAL_BIN" "$NPM_PREFIX"

if [[ "$(uname -r)" == 4.*Microsoft* ]]; then
  echo "WSL 1 detected. Codex can install, but current Claude Code requires WSL 2 in this environment." >&2
  echo "In Windows PowerShell, run: wsl --set-version Ubuntu 2" >&2
  exit 65
fi

if [[ ! -x "$NODE_DIR/bin/node" ]]; then
  archive="/tmp/node-$NODE_VERSION-linux-x64.tar.xz"
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz" -o "$archive"
  tar -xJf "$archive" -C "$HOME/.local"
  mv "$HOME/.local/node-$NODE_VERSION-linux-x64" "$NODE_DIR"
  rm -f "$archive"
fi

ln -sfn "$NODE_DIR/bin/node" "$LOCAL_BIN/node"
ln -sfn "$NODE_DIR/bin/npm" "$LOCAL_BIN/npm"
ln -sfn "$NODE_DIR/bin/npx" "$LOCAL_BIN/npx"

path_line='export PATH="$HOME/.local/bin:$HOME/.local/npm-global/bin:$PATH"'
if ! grep -Fqx "$path_line" "$HOME/.bashrc" 2>/dev/null; then
  printf '\n# User-local Node.js and AI CLIs\n%s\n' "$path_line" >> "$HOME/.bashrc"
fi

export PATH="$LOCAL_BIN:$NPM_PREFIX/bin:$PATH"
npm config set prefix "$NPM_PREFIX"
npm install -g @anthropic-ai/claude-code @openai/codex

echo "Installed Node: $(node --version)"
echo "Installed Claude: $(claude --version)"
echo "Installed Codex: $(codex --version)"
echo "Open a new WSL terminal, then run: claude  and  codex login"
