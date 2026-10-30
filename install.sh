#!/usr/bin/env sh
# 8Bit Music Code Studio installer (Linux / macOS). Puts `8bms` on your PATH.
#
#   curl -fsSL https://raw.githubusercontent.com/RechargedIdeas/8bit-music-code-studio/main/install.sh | sh
#   curl -fsSL .../install.sh | sh -s -- --all          # extras: --all --audio --midi --mcp --acp --ml
#   sh install.sh --uninstall                          # remove (keeps ~/.8bms data unless --purge)
#
# Options:
#   --all | --audio | --midi | --mcp | --acp | --ml   optional extras (combine freely)
#   --method auto|pipx|uv|venv   force an installer (default auto: pipx, then uv, then a venv)
#   --source SPEC                install from a local folder, archive URL or git URL instead of GitHub main
#   --python PATH                Python 3.10+ to use
#   --no-modify-path             don't add ~/.local/bin to your shell profile
#   --uninstall [--purge]        remove 8bms (--purge also deletes ~/.8bms: handles, plugins, settings)
#   -y | --yes                   no prompts (there are none today; accepted for scripts)
# Re-running upgrades in place. Never uses sudo; it only prints the system command you may need.
set -eu

PKG="eightbit-music-code-studio"
REPO="https://github.com/RechargedIdeas/8bit-music-code-studio"
SOURCE="${EIGHTBMS_SOURCE:-$REPO/archive/refs/heads/main.zip}"
HOME_DIR="${EIGHTBMS_HOME:-$HOME/.8bms}"
VENV="$HOME_DIR/venv"
BIN_DIR="${EIGHTBMS_BIN_DIR:-$HOME/.local/bin}"
EXTRAS=""
METHOD="auto"
PY="${EIGHTBMS_PYTHON:-}"
UNINSTALL=0
PURGE=0
MODIFY_PATH=1

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then B="$(printf '\033[1m')"; G="$(printf '\033[32m')"; Y="$(printf '\033[33m')"; R="$(printf '\033[31m')"; N="$(printf '\033[0m')"; else B=""; G=""; Y=""; R=""; N=""; fi
say()  { printf '%s==>%s %s\n' "$B" "$N" "$*"; }
ok()   { printf '%s ok%s %s\n' "$G" "$N" "$*"; }
warn() { printf '%swarn%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%serror%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
add_extra() { case ",$EXTRAS," in *",$1,"*) ;; *) EXTRAS="${EXTRAS:+$EXTRAS,}$1" ;; esac; }

while [ $# -gt 0 ]; do
  case "$1" in
    --all) add_extra all ;;
    --audio|--midi|--mcp|--acp|--ml) add_extra "${1#--}" ;;
    --method) shift; METHOD="${1:?--method needs a value}" ;;
    --method=*) METHOD="${1#*=}" ;;
    --source) shift; SOURCE="${1:?--source needs a value}" ;;
    --source=*) SOURCE="${1#*=}" ;;
    --python) shift; PY="${1:?--python needs a value}" ;;
    --python=*) PY="${1#*=}" ;;
    --no-modify-path) MODIFY_PATH=0 ;;
    --uninstall) UNINSTALL=1 ;;
    --purge) PURGE=1 ;;
    -y|--yes) ;;
    -h|--help) sed -n '2,20p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
  shift
done
case "$METHOD" in auto|pipx|uv|venv) ;; *) die "--method must be auto, pipx, uv or venv" ;; esac

OS="$(uname -s 2>/dev/null || echo unknown)"
have() { command -v "$1" >/dev/null 2>&1; }

python_hint() {
  if [ "$OS" = "Darwin" ]; then echo "  brew install python@3.12 python-tk@3.12      (or https://www.python.org/downloads/)"
  elif have apt-get; then echo "  sudo apt-get install -y python3 python3-venv python3-tk"
  elif have dnf; then echo "  sudo dnf install -y python3 python3-tkinter"
  elif have pacman; then echo "  sudo pacman -S --needed python tk"
  elif have zypper; then echo "  sudo zypper install python3 python3-tk"
  elif have apk; then echo "  sudo apk add python3 py3-pip py3-tkinter"
  else echo "  install Python 3.10+ from https://www.python.org/downloads/"; fi
  echo "  or let uv fetch one: curl -LsSf https://astral.sh/uv/install.sh | sh   (then re-run this installer)"
}
tk_hint() {
  if [ "$OS" = "Darwin" ]; then echo "brew install python-tk@3.12 (match your Python version)"
  elif have apt-get; then echo "sudo apt-get install -y python3-tk"
  elif have dnf; then echo "sudo dnf install -y python3-tkinter"
  elif have pacman; then echo "sudo pacman -S --needed tk"
  elif have zypper; then echo "sudo zypper install python3-tk"
  elif have apk; then echo "sudo apk add py3-tkinter"
  else echo "install the Tk bindings for your Python"; fi
}
py_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }
find_python() {
  if [ -n "$PY" ]; then py_ok "$PY" || die "$PY is not Python 3.10+"; return; fi
  # prefer a Python that has tkinter (the GUI needs it), else any 3.10+
  for c in python3 python3.13 python3.12 python3.11 python3.10 python; do
    if have "$c" && py_ok "$c" && "$c" -c 'import tkinter' >/dev/null 2>&1; then PY="$(command -v "$c")"; return; fi
  done
  for c in python3 python3.13 python3.12 python3.11 python3.10 python; do
    if have "$c" && py_ok "$c"; then PY="$(command -v "$c")"; return; fi
  done
  PY=""
}
spec() {
  # PEP 508 direct reference: "name[extras] @ url" works for pip, pipx and uv alike.
  src="$SOURCE"
  if [ -e "$src" ]; then src="file://$(cd "$src" && pwd)"; fi
  case "$src" in git@*|https://github.com/*.git) src="git+$src" ;; esac
  if [ -n "$EXTRAS" ]; then echo "${PKG}[${EXTRAS}] @ $src"; else echo "$PKG @ $src"; fi
}

uninstall() {
  say "Uninstalling 8bms"
  removed=0
  if have pipx && pipx list --short 2>/dev/null | grep -q "^$PKG "; then pipx uninstall "$PKG" && removed=1; fi
  if have uv && uv tool list 2>/dev/null | grep -q "^$PKG "; then uv tool uninstall "$PKG" && removed=1; fi
  if [ -d "$VENV" ]; then rm -rf "$VENV"; removed=1; fi
  if [ -L "$BIN_DIR/8bms" ]; then
    case "$(readlink "$BIN_DIR/8bms")" in "$VENV"/*) rm -f "$BIN_DIR/8bms" ;; esac
  fi
  if [ "$PURGE" = 1 ] && [ -d "$HOME_DIR" ]; then rm -rf "$HOME_DIR"; ok "deleted $HOME_DIR"; fi
  if [ "$removed" = 1 ]; then ok "8bms removed"; else warn "nothing to remove (8bms was not installed by this script)"; fi
  [ "$PURGE" = 1 ] || [ ! -d "$HOME_DIR" ] || echo "   your songs/handles/plugins in $HOME_DIR were kept (add --purge to delete)"
  exit 0
}
[ "$UNINSTALL" = 1 ] && uninstall

say "8Bit Music Code Studio installer ($OS)"
find_python
if [ -z "$PY" ]; then
  if [ "$METHOD" != "venv" ] && have uv; then
    warn "no Python 3.10+ found; uv will download one"
  else
    printf '%sPython 3.10+ is required.%s Install it, then re-run:\n' "$R" "$N" >&2
    python_hint >&2
    exit 1
  fi
else
  ok "Python $("$PY" -c 'import platform; print(platform.python_version())') at $PY"
fi

SPEC="$(spec)"
if [ "$METHOD" = auto ]; then
  if have pipx && [ -n "$PY" ]; then METHOD=pipx; elif have uv; then METHOD=uv; else METHOD=venv; fi
fi
install_with() {  # $1 = spec
  case "$METHOD" in
    pipx)
      have pipx || die "pipx not found"
      pipx install --force --python "$PY" "$1" || return 1
      EXE="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")/8bms"
      ;;
    uv)
      have uv || die "uv not found (curl -LsSf https://astral.sh/uv/install.sh | sh)"
      if [ -n "$PY" ]; then uv tool install --force --reinstall --python "$PY" "$1" || return 1
      else uv tool install --force --reinstall --python 3.12 "$1" || return 1; fi
      EXE="$(uv tool dir --bin 2>/dev/null || echo "$HOME/.local/bin")/8bms"
      ;;
    venv)
      [ -n "$PY" ] || die "venv method needs Python 3.10+"
      mkdir -p "$HOME_DIR"
      if [ ! -x "$VENV/bin/python" ]; then
        "$PY" -m venv "$VENV" 2>/dev/null || {
          rm -rf "$VENV"
          printf '%sCould not create a virtualenv.%s On Debian/Ubuntu: sudo apt-get install -y python3-venv\n' "$R" "$N" >&2
          exit 1
        }
      fi
      "$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip || return 1
      "$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade "$1" || return 1
      # same version number on every main commit: force-refresh the app itself (not numpy etc.)
      "$VENV/bin/python" -m pip install -q --disable-pip-version-check --force-reinstall --no-deps "$1" || return 1
      mkdir -p "$BIN_DIR"
      ln -sf "$VENV/bin/8bms" "$BIN_DIR/8bms"
      EXE="$BIN_DIR/8bms"
      ;;
  esac
}

say "Installing with $METHOD: $SPEC"
if ! install_with "$SPEC"; then
  [ -n "$EXTRAS" ] || die "install failed (see the messages above)"
  warn "extras [$EXTRAS] failed to install (often: no prebuilt wheel for this Python/OS, e.g. python-rtmidi)."
  warn "installing the core app without them; add them later by re-running with the flag once fixed."
  EXTRAS=""
  SPEC="$(spec)"
  install_with "$SPEC" || die "install failed (see the messages above)"
fi

[ -x "$EXE" ] || EXE="$(command -v 8bms || true)"
[ -n "$EXE" ] && [ -x "$EXE" ] || die "install finished but the 8bms command was not found"
VER="$("$EXE" --version 2>&1)" || die "8bms was installed but does not run: $VER"
ok "$VER -> $EXE"

# PATH
EXE_DIR="$(dirname "$EXE")"
case ":$PATH:" in
  *":$EXE_DIR:"*) ok "$EXE_DIR is on PATH" ;;
  *)
    LINE="export PATH=\"$EXE_DIR:\$PATH\"   # added by 8bms installer"
    if [ "$MODIFY_PATH" = 1 ]; then
      for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
        case "$rc" in */.profile) ;; *) [ -f "$rc" ] || continue ;; esac
        grep -qs "added by 8bms installer" "$rc" || printf '\n%s\n' "$LINE" >> "$rc"
      done
      warn "added $EXE_DIR to PATH in your shell profile; open a new terminal or run:"
    else
      warn "$EXE_DIR is not on PATH; add this to your shell profile:"
    fi
    echo "   $LINE"
    ;;
esac

# GUI check (CLI, MCP, ACP and HTTP work without Tk)
TKPY="$PY"
[ "$METHOD" = venv ] && TKPY="$VENV/bin/python"
if [ -n "$TKPY" ] && ! "$TKPY" -c 'import tkinter' >/dev/null 2>&1; then
  warn "tkinter is missing, so the GUI won't open (everything else works). Fix: $(tk_hint)"
fi
if ! have ffmpeg; then echo "   tip: install ffmpeg for OGG/MP3/FLAC export (WAV always works)"; fi

cat <<MSG

${G}Done.${N} Try:
  8bms                      # open the GUI
  8bms studio               # terminal studio
  8bms compose "mellow space loop" --bars 8 --wav space.wav
  8bms soundpack platformer -o sfx/
Upgrade: re-run this installer.  Uninstall: sh install.sh --uninstall
MSG
