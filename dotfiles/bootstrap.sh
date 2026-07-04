#!/usr/bin/env bash
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${DOTFILES_DIR}/.." && pwd)"
ZSH_DIR="${DOTFILES_DIR}/zsh"
NVIM_DIR="${DOTFILES_DIR}/nvim"
TMUXP_DIR="${DOTFILES_DIR}/tmuxp"
LOCAL_BIN="${HOME}/.local/bin"
ZSH_HOME="${ZSH:-${HOME}/.oh-my-zsh}"
ZSH_CUSTOM_DIR="${ZSH_CUSTOM:-${ZSH_HOME}/custom}"

log() {
  printf '[dotfiles-bootstrap] %s\n' "$1"
}

ensure_dir() {
  mkdir -p "$1"
}

backup_path() {
  local path="$1"

  if [ -L "$path" ] || [ ! -e "$path" ]; then
    return 0
  fi

  local backup="${path}.backup.$(date +%Y%m%d%H%M%S)"
  log "backing up existing ${path} to ${backup}"
  mv "$path" "$backup"
}

link_file() {
  local source="$1"
  local target="$2"

  if [ ! -e "$source" ]; then
    log "missing ${source}; skipping ${target}"
    return 0
  fi

  ensure_dir "$(dirname "$target")"
  backup_path "$target"
  ln -sfn "$source" "$target"
  log "linked ${target} -> ${source}"
}

link_dir() {
  local source="$1"
  local target="$2"

  if [ ! -d "$source" ]; then
    log "missing ${source}; skipping ${target}"
    return 0
  fi

  ensure_dir "$(dirname "$target")"
  backup_path "$target"
  ln -sfn "$source" "$target"
  log "linked ${target} -> ${source}"
}

clone_or_update() {
  local repo_url="$1"
  local target="$2"

  if [ -d "${target}/.git" ]; then
    log "updating ${target}"
    git -C "$target" pull --ff-only
    return 0
  fi

  log "cloning ${repo_url} -> ${target}"
  git clone --depth 1 "$repo_url" "$target"
}

install_oh_my_zsh() {
  if [ -d "$ZSH_HOME" ]; then
    log "Oh My Zsh already installed"
    return 0
  fi

  log "installing Oh My Zsh"
  RUNZSH=no CHSH=no KEEP_ZSHRC=yes sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
}

install_zsh_plugins() {
  ensure_dir "${ZSH_CUSTOM_DIR}/themes"
  ensure_dir "${ZSH_CUSTOM_DIR}/plugins"

  clone_or_update \
    https://github.com/romkatv/powerlevel10k.git \
    "${ZSH_CUSTOM_DIR}/themes/powerlevel10k"

  clone_or_update \
    https://github.com/zsh-users/zsh-autosuggestions.git \
    "${ZSH_CUSTOM_DIR}/plugins/zsh-autosuggestions"

  clone_or_update \
    https://github.com/zsh-users/zsh-syntax-highlighting.git \
    "${ZSH_CUSTOM_DIR}/plugins/zsh-syntax-highlighting"
}

install_yazi() {
  if command -v yazi >/dev/null 2>&1 && command -v ya >/dev/null 2>&1; then
    log "yazi already installed"
    return 0
  fi

  local arch target asset tmpdir release_json download_url archive yazi_bin ya_bin
  arch="$(uname -m)"

  case "$arch" in
    x86_64|amd64)
      target="x86_64"
      ;;
    aarch64|arm64)
      target="aarch64"
      ;;
    *)
      log "unsupported architecture for automatic yazi install: ${arch}"
      return 1
      ;;
  esac

  asset="yazi-${target}-unknown-linux-gnu.zip"
  tmpdir="$(mktemp -d)"
  release_json="${tmpdir}/release.json"
  archive="${tmpdir}/${asset}"

  log "resolving latest yazi release asset ${asset}"
  curl -fsSL https://api.github.com/repos/sxyazi/yazi/releases/latest -o "$release_json"

  download_url="$(python3 - "$asset" "$release_json" <<'PY'
import json
import sys

asset_name = sys.argv[1]
release_path = sys.argv[2]

with open(release_path, encoding="utf-8") as handle:
    release = json.load(handle)

for asset in release.get("assets", []):
    if asset.get("name") == asset_name:
        print(asset["browser_download_url"])
        break
else:
    raise SystemExit(f"asset not found: {asset_name}")
PY
)"

  log "downloading ${download_url}"
  curl -fL "$download_url" -o "$archive"
  unzip -q "$archive" -d "$tmpdir"

  yazi_bin="$(find "$tmpdir" -type f -name yazi -perm -111 | head -n 1)"
  ya_bin="$(find "$tmpdir" -type f -name ya -perm -111 | head -n 1)"

  if [ -z "$yazi_bin" ] || [ -z "$ya_bin" ]; then
    log "downloaded yazi archive did not contain yazi and ya executables"
    return 1
  fi

  ensure_dir "$LOCAL_BIN"
  install -m 0755 "$yazi_bin" "${LOCAL_BIN}/yazi"
  install -m 0755 "$ya_bin" "${LOCAL_BIN}/ya"
  rm -rf "$tmpdir"
  log "installed yazi and ya into ${LOCAL_BIN}"
}

install_dotfile_links() {
  ensure_dir "$LOCAL_BIN"
  ensure_dir "${HOME}/.config"
  ensure_dir "${HOME}/.tmuxp"

  link_file "${ZSH_DIR}/.zshrc" "${HOME}/.zshrc"
  link_file "${ZSH_DIR}/.p10k.zsh" "${HOME}/.p10k.zsh"
  link_dir "$NVIM_DIR" "${HOME}/.config/nvim"
  link_file "${TMUXP_DIR}/nvim-omp-term.yaml" "${HOME}/.tmuxp/nvim-omp-term.yaml"

  if [ -f "${DOTFILES_DIR}/tmux/.tmux.conf" ]; then
    link_file "${DOTFILES_DIR}/tmux/.tmux.conf" "${HOME}/.tmux.conf"
  fi
}

main() {
  log "using repo root ${REPO_ROOT}"
  install_oh_my_zsh
  install_zsh_plugins
  install_yazi
  install_dotfile_links
  log "complete"
}

main "$@"
