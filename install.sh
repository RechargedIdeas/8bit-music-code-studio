#!/usr/bin/env sh
# 8Bit Music Code Studio installer (Linux / macOS). Puts `8bms` on your PATH.
#
#   curl -fsSL https://raw.githubusercontent.com/RechargedIdeas/8bit-music-code-studio/main/install.sh | sh
#   curl -fsSL .../install.sh | sh -s -- --all          # extras: --all --audio --midi --mcp --acp --ml
#   sh install.sh --uninstall                          # remove (keeps ~/.8bms data unless --purge)
#
# Always the newest installer (raw.githubusercontent.com caches for up to 5 minutes and ignores ?query
# strings; the GitHub API does not, and a stale piped copy of this script hands over to the current one):
#   curl -fsSL -H "Accept: application/vnd.github.raw" https://api.github.com/repos/RechargedIdeas/8bit-music-code-studio/contents/install.sh | sh
#
# Options:
#   --all | --audio | --midi | --mcp | --acp | --ml   optional extras (combine freely)
#   --method auto|pipx|uv|venv   force an installer (default auto: pipx, then uv, then a venv)
#   --source SPEC                install from a local folder, archive URL or git URL instead of GitHub main
#   --python PATH                Python 3.10+ to use
#   --no-modify-path             don't add the 8bms folder to your shell profile
#   --no-self-update             never swap a stale piped copy of this script for the current one
#   --verbose                    print diagnostics and every command (or EIGHTBMS_DEBUG=1)
#   --uninstall [--purge]        remove 8bms (--purge also deletes ~/.8bms: handles, plugins, settings)
#   -y | --yes                   no prompts (there are none today; accepted for scripts)
# Missing or broken pipx/uv are installed or repaired automatically (user-level), and if a method fails the
# next one is tried: pipx -> uv -> a private venv in ~/.8bms (venv -> ensurepip -> virtualenv -> uv venv).
# Re-running upgrades in place. Never uses sudo; it only prints the system command you may need.
set -u

INSTALLER_VERSION="1.1.1"
REPO_PATH="RechargedIdeas/8bit-music-code-studio"
PKG="eightbit-music-code-studio"
REPO="https://github.com/$REPO_PATH"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then B="$(printf '\033[1m')"; G="$(printf '\033[32m')"; Y="$(printf '\033[33m')"; R="$(printf '\033[31m')"; D="$(printf '\033[2m')"; N="$(printf '\033[0m')"; else B=""; G=""; Y=""; R=""; D=""; N=""; fi
say()  { printf '%s==>%s %s\n' "$B" "$N" "$*"; }
ok()   { printf '%s ok%s %s\n' "$G" "$N" "$*"; }
warn() { printf '%swarn%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%serror%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
DEBUG="${EIGHTBMS_DEBUG:-0}"
dbg()  { [ "$DEBUG" = 1 ] && printf '%s  .. %s%s\n' "$D" "$*" "$N" >&2; return 0; }
have() { command -v "$1" >/dev/null 2>&1; }
# run CMD...: output visible; on failure print the command and its exit code
run()  { dbg "> $*"; "$@"; _rc=$?; [ "$_rc" -eq 0 ] || printf '%s  command failed (exit %s): %s%s\n' "$Y" "$_rc" "$*" "$N" >&2; return "$_rc"; }
# probe CMD...: quiet; succeeds if it exits 0
probe() { if "$@" >/dev/null 2>&1; then dbg "probe $* -> ok"; return 0; else dbg "probe $* -> FAILED"; return 1; fi; }
fetch() {  # fetch URL [HEADER] -> stdout
  if have curl; then if [ -n "${2:-}" ]; then curl -fsSL --max-time 30 -H "$2" "$1"; else curl -fsSL --max-time 30 "$1"; fi
  elif have wget; then if [ -n "${2:-}" ]; then wget -qO- --timeout=30 --header="$2" "$1"; else wget -qO- --timeout=30 "$1"; fi
  else return 1; fi
}
main_sha() { fetch "https://api.github.com/repos/$REPO_PATH/commits/main" "Accept: application/vnd.github.sha" 2>/dev/null | grep -E '^[0-9a-f]{40}$' | head -n 1; }

# ---- a stale piped copy (CDN cache) hands over to the installer of the commit being installed ----
_self_update=1; _has_source=0
for _a in "$@"; do case "$_a" in --no-self-update) _self_update=0 ;; --source|--source=*) _has_source=1 ;; esac; done
[ "${EIGHTBMS_NO_SELFUPDATE:-0}" = 1 ] && _self_update=0
[ -n "${EIGHTBMS_SOURCE:-}" ] && _has_source=1
case "$0" in *install.sh) [ -z "${EIGHTBMS_INSTALLER_URL:-}" ] && _self_update=0 ;; esac   # run from a file: use it as is
if [ "$_self_update" = 1 ] && { [ "$_has_source" = 0 ] || [ -n "${EIGHTBMS_INSTALLER_URL:-}" ]; }; then
  _url="${EIGHTBMS_INSTALLER_URL:-}"
  if [ -z "$_url" ]; then
    EIGHTBMS_COMMIT="${EIGHTBMS_COMMIT:-$(main_sha || true)}"
    [ -n "$EIGHTBMS_COMMIT" ] && _url="https://raw.githubusercontent.com/$REPO_PATH/$EIGHTBMS_COMMIT/install.sh"
  fi
  if [ -n "$_url" ]; then
    _tmp="$(mktemp 2>/dev/null || echo "/tmp/8bms-install.$$")"
    if { [ -f "$_url" ] && cp "$_url" "$_tmp"; } || fetch "$_url" > "$_tmp" 2>/dev/null; then
      _v="$(sed -n 's/^INSTALLER_VERSION="\(.*\)"$/\1/p' "$_tmp" | head -n 1)"
      if [ -n "$_v" ] && [ "$_v" != "$INSTALLER_VERSION" ]; then
        warn "this installer copy ($INSTALLER_VERSION) is stale (cached download); running the current installer $_v"
        EIGHTBMS_NO_SELFUPDATE=1 EIGHTBMS_COMMIT="${EIGHTBMS_COMMIT:-}" sh "$_tmp" "$@"; _rc=$?
        rm -f "$_tmp"; exit "$_rc"
      fi
    fi
    rm -f "$_tmp"
  fi
fi

SOURCE="${EIGHTBMS_SOURCE:-}"
HOME_DIR="${EIGHTBMS_HOME:-$HOME/.8bms}"
VENV="$HOME_DIR/venv"
BIN_DIR="${EIGHTBMS_BIN_DIR:-$HOME/.local/bin}"
EXTRAS=""
METHOD="${EIGHTBMS_METHOD:-auto}"
PY="${EIGHTBMS_PYTHON:-}"
UNINSTALL=0
PURGE=0
MODIFY_PATH=1
add_extra() { case ",$EXTRAS," in *",$1,"*) ;; *) EXTRAS="${EXTRAS:+$EXTRAS,}$1" ;; esac; }
[ -n "${EIGHTBMS_EXTRAS:-}" ] && for _e in $(echo "$EIGHTBMS_EXTRAS" | tr ',' ' '); do add_extra "$_e"; done

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
    --no-self-update) ;;
    --verbose|-v) DEBUG=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --purge) PURGE=1 ;;
    -y|--yes) ;;
    -h|--help) sed -n '2,26p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
  shift
done
case "$METHOD" in auto|pipx|uv|venv) ;; *) die "--method must be auto, pipx, uv or venv" ;; esac

OS="$(uname -s 2>/dev/null || echo unknown)"

# ---- environment that breaks pip/pipx/uv: fix for this run only ----
for _n in PYTHONHOME PYTHONPATH PIP_TARGET PIP_PREFIX PIP_REQUIRE_VIRTUALENV PIP_USER VIRTUAL_ENV; do
  eval "_v=\${$_n:-}"
  if [ -n "$_v" ]; then dbg "$_n=$_v (cleared for this install)"; unset "$_n"; fi
done
for _n in PIPX_HOME PIPX_BIN_DIR PIPX_SHARED_LIBS PIPX_MAN_DIR UV_TOOL_DIR UV_TOOL_BIN_DIR UV_CACHE_DIR UV_PYTHON_INSTALL_DIR UV_INSTALL_DIR PIP_CACHE_DIR PYTHONUSERBASE TMPDIR; do
  eval "_v=\${$_n:-}"
  if [ -n "$_v" ] && ! mkdir -p "$_v" 2>/dev/null; then warn "$_n=$_v is not a usable folder; ignoring it for this install"; unset "$_n"; fi
done
for _n in PIPX_DEFAULT_PYTHON UV_PYTHON; do
  eval "_v=\${$_n:-}"
  case "$_v" in */*) [ -x "$_v" ] || { warn "$_n=$_v does not exist; ignoring it for this install"; unset "$_n"; } ;; esac
done

python_hint() {
  if [ "$OS" = "Darwin" ]; then echo "  brew install python@3.12 python-tk@3.12      (or https://www.python.org/downloads/)"
  elif have apt-get; then echo "  sudo apt-get install -y python3 python3-venv python3-tk"
  elif have dnf; then echo "  sudo dnf install -y python3 python3-tkinter"
  elif have pacman; then echo "  sudo pacman -S --needed python tk"
  elif have zypper; then echo "  sudo zypper install python3 python3-tk"
  elif have apk; then echo "  sudo apk add python3 py3-pip py3-tkinter"
  else echo "  install Python 3.10+ from https://www.python.org/downloads/"; fi
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
# resolve to the base interpreter when the found python lives inside a venv
py_base() { "$1" -c 'import sys; print((getattr(sys, "_base_executable", "") or sys.executable) if sys.prefix != sys.base_prefix else sys.executable)' 2>/dev/null; }
find_python() {
  if [ -n "$PY" ]; then
    py_ok "$PY" || die "$PY is not Python 3.10+"
    PY="$(command -v "$PY" 2>/dev/null || echo "$PY")"; return
  fi
  for _tk in 1 0; do
    for c in python3 python3.13 python3.12 python3.11 python3.10 python; do
      have "$c" && py_ok "$c" || continue
      if [ "$_tk" = 1 ]; then "$c" -c 'import tkinter' >/dev/null 2>&1 || continue; fi
      _b="$(py_base "$c")"
      if [ -n "$_b" ] && [ -x "$_b" ] && py_ok "$_b"; then PY="$_b"; else PY="$(command -v "$c")"; fi
      return
    done
  done
  PY=""
}

COMMIT="${EIGHTBMS_COMMIT:-}"
if [ -z "$SOURCE" ]; then
  if [ "$UNINSTALL" = 0 ] && [ -z "$COMMIT" ]; then COMMIT="$(main_sha || true)"; fi
  if [ -n "$COMMIT" ]; then SOURCE="$REPO/archive/$COMMIT.zip"; else SOURCE="$REPO/archive/refs/heads/main.zip"; fi
fi
SHORT="main"; [ -n "$COMMIT" ] && SHORT="$(echo "$COMMIT" | cut -c1-7)"
spec() {
  # PEP 508 direct reference: "name[extras] @ url" works for pip, pipx and uv alike.
  src="$SOURCE"
  if [ -e "$src" ]; then src="file://$(cd "$src" && pwd)"; fi
  case "$src" in git@*|https://github.com/*.git) src="git+$src" ;; esac
  if [ -n "$EXTRAS" ]; then echo "${PKG}[${EXTRAS}] @ $src"; else echo "$PKG @ $src"; fi
}

diagnostics() {
  {
    echo "---- diagnostics (installer $INSTALLER_VERSION, commit $SHORT) ----"
    echo "  $(uname -a 2>/dev/null)"
    echo "  shell: $0; python: ${PY:-(none found)}"
    for c in python3 python pipx uv 8bms; do
      for p in $(command -v -a "$c" 2>/dev/null || command -v "$c" 2>/dev/null); do echo "  $c -> $p"; done
    done
    for v in HOME TMPDIR; do eval "_x=\${$v:-}"; [ -n "$_x" ] && { [ -d "$_x" ] && echo "  $v=$_x (exists)" || echo "  $v=$_x (MISSING)"; }; done
    env | grep -E '^(PIPX_|UV_|PIP_|PYTHON|VIRTUAL_ENV|CONDA)' | sed 's/^/  /'
    if [ -n "$PY" ]; then
      echo "  python -m pip: $("$PY" -m pip --version 2>/dev/null || echo '(not installed or broken)')"
      echo "  python -m pipx: $("$PY" -m pipx --version 2>/dev/null || echo '(not installed or broken)')"
      echo "  python -m venv/ensurepip: $("$PY" -c 'import venv, ensurepip; print("ok")' 2>/dev/null || echo 'missing (Debian/Ubuntu: python3-venv)')"
      [ -f "$("$PY" -c 'import sysconfig; print(sysconfig.get_path("stdlib"))' 2>/dev/null)/EXTERNALLY-MANAGED" ] && echo "  python is externally managed (PEP 668): pip --user is blocked"
    fi
    echo "---- end diagnostics ----"
  } >&2
}

# ---- pip / pipx / uv bootstrapping (through the found Python where possible) ----
ensure_pip() {
  probe "$PY" -m pip --version && return 0
  say "pip is missing for $PY; bootstrapping it (ensurepip)"
  run "$PY" -m ensurepip --upgrade --user >/dev/null 2>&1 || true
  probe "$PY" -m pip --version
}
pip_user() { ensure_pip || return 1; run "$PY" -m pip install --user --upgrade --disable-pip-version-check --no-warn-script-location "$@"; }
PIPX=""
ensure_pipx() {
  [ -n "$PY" ] || return 1
  if probe "$PY" -m pipx --version; then PIPX="$PY -m pipx"; return 0; fi
  if have pipx && probe pipx --version; then PIPX="pipx"; return 0; fi
  have pipx && warn "a pipx command is on PATH but does not run; ignoring it"
  say "pipx is not installed (or is broken); installing it: python -m pip install --user pipx"
  pip_user pipx || return 1
  probe "$PY" -m pipx --version || return 1
  PIPX="$PY -m pipx"
  $PIPX ensurepath >/dev/null 2>&1 || true
}
UV=""
ensure_uv() {
  [ -n "$UV" ] && return 0
  if have uv && probe uv --version; then UV="uv"; return 0; fi
  have uv && warn "a uv command is on PATH but does not run; ignoring it"
  if [ -n "$PY" ]; then
    if ! probe "$PY" -m uv --version; then say "uv is not installed; installing it: python -m pip install --user uv"; pip_user uv || true; fi
    if probe "$PY" -m uv --version; then UV="$PY -m uv"; return 0; fi
  fi
  say "installing uv with the official installer (astral.sh)"
  _ud="${UV_INSTALL_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
  if fetch https://astral.sh/uv/install.sh > "${TMPDIR:-/tmp}/uv-install.$$.sh"; then
    run env UV_NO_MODIFY_PATH=1 sh "${TMPDIR:-/tmp}/uv-install.$$.sh" || true
  fi
  rm -f "${TMPDIR:-/tmp}/uv-install.$$.sh"
  for _u in "$_ud/uv" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    if [ -x "$_u" ] && probe "$_u" --version; then UV="$_u"; return 0; fi
  done
  return 1
}

uninstall() {
  say "Uninstalling 8bms"
  removed=0
  if [ -n "$PY" ] && probe "$PY" -m pipx --version; then P="$PY -m pipx"; elif have pipx && probe pipx --version; then P="pipx"; else P=""; fi
  if [ -n "$P" ] && $P list --short 2>/dev/null | grep -q "^$PKG "; then $P uninstall "$PKG" && removed=1; fi
  if have uv && probe uv --version; then U="uv"; elif [ -n "$PY" ] && probe "$PY" -m uv --version; then U="$PY -m uv"; else U=""; fi
  if [ -n "$U" ] && $U tool list 2>/dev/null | grep -q "^$PKG "; then $U tool uninstall "$PKG" && removed=1; fi
  if [ -d "$VENV" ]; then rm -rf "$VENV"; removed=1; fi
  if [ -L "$BIN_DIR/8bms" ]; then
    case "$(readlink "$BIN_DIR/8bms")" in "$VENV"/*) rm -f "$BIN_DIR/8bms" ;; esac
  fi
  if [ "$PURGE" = 1 ] && [ -d "$HOME_DIR" ]; then rm -rf "$HOME_DIR"; ok "deleted $HOME_DIR"; fi
  if [ "$removed" = 1 ]; then ok "8bms removed"; else warn "nothing to remove (8bms was not installed by this script)"; fi
  [ "$PURGE" = 1 ] || [ ! -d "$HOME_DIR" ] || echo "   your songs/handles/plugins in $HOME_DIR were kept (add --purge to delete)"
  exit 0
}

say "8Bit Music Code Studio installer $INSTALLER_VERSION (app commit $SHORT; $OS)"
find_python
[ "$DEBUG" = 1 ] && diagnostics
[ "$UNINSTALL" = 1 ] && uninstall
if [ -z "$PY" ]; then
  warn "no Python 3.10+ found; uv will install one"
  METHODS="uv"
else
  ok "Python $("$PY" -c 'import platform; print(platform.python_version())') at $PY"
  if [ "$METHOD" = auto ]; then METHODS="pipx uv venv"; else METHODS="$METHOD"; fi
fi

EXE=""
PIPX_REPAIRED=0
install_pipx() {
  ensure_pipx || return 1
  if ! run $PIPX install --force --python "$PY" "$1"; then
    [ "$PIPX_REPAIRED" = 0 ] || return 1
    PIPX_REPAIRED=1
    warn "pipx install failed; repairing pipx (upgrade it, reset its shared libraries and the old 8bms env) and retrying once"
    [ "$PIPX" = "pipx" ] || pip_user pipx || true
    _s="$($PIPX environment --value PIPX_SHARED_LIBS 2>/dev/null || true)"; [ -n "$_s" ] && [ -d "$_s" ] && rm -rf "$_s"
    _l="$($PIPX environment --value PIPX_LOCAL_VENVS 2>/dev/null || true)"; [ -n "$_l" ] && [ -d "$_l/$PKG" ] && rm -rf "${_l:?}/$PKG"
    run $PIPX install --force --python "$PY" "$1" || return 1
  fi
  EXE="$($PIPX environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")/8bms"
}
install_uv() {
  ensure_uv || return 1
  if [ -n "$PY" ]; then run $UV tool install --force --reinstall --python "$PY" "$1" || return 1
  else run $UV tool install --force --reinstall --python 3.12 "$1" || return 1; fi
  EXE="$($UV tool dir --bin 2>/dev/null || echo "$HOME/.local/bin")/8bms"
}
new_venv() {
  if [ -x "$VENV/bin/python" ] && probe "$VENV/bin/python" -c 'import sys'; then return 0; fi
  [ -e "$VENV" ] && { warn "removing a broken venv at $VENV"; rm -rf "$VENV"; }
  mkdir -p "$HOME_DIR"
  run "$PY" -m venv "$VENV" && return 0
  rm -rf "$VENV"
  warn "python -m venv failed (Debian/Ubuntu: python3-venv is missing); trying a venv without pip plus ensurepip"
  if run "$PY" -m venv --without-pip "$VENV" && run "$VENV/bin/python" -m ensurepip --upgrade; then return 0; fi
  rm -rf "$VENV"
  warn "trying virtualenv instead"
  if probe "$PY" -m virtualenv --version || pip_user virtualenv; then run "$PY" -m virtualenv "$VENV" && return 0; fi
  rm -rf "$VENV"
  warn "trying uv venv instead"
  if ensure_uv; then run $UV venv --seed --python "$PY" "$VENV" && return 0; fi
  rm -rf "$VENV"
  printf '%sCould not create a virtualenv.%s On Debian/Ubuntu: sudo apt-get install -y python3-venv\n' "$R" "$N" >&2
  return 1
}
install_venv() {
  new_venv || return 1
  probe "$VENV/bin/python" -m pip --version || run "$VENV/bin/python" -m ensurepip --upgrade || return 1
  run "$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip || true
  run "$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade "$1" || return 1
  # same version number on every main commit: force-refresh the app itself (not numpy etc.)
  run "$VENV/bin/python" -m pip install -q --disable-pip-version-check --force-reinstall --no-deps "$1" || return 1
  mkdir -p "$BIN_DIR"
  ln -sf "$VENV/bin/8bms" "$BIN_DIR/8bms"
  EXE="$BIN_DIR/8bms"
}
try_install() { case "$1" in pipx) install_pipx "$2" ;; uv) install_uv "$2" ;; venv) install_venv "$2" ;; esac; }

INSTALLED=""
LAST="$(echo "$METHODS" | awk '{print $NF}')"
for M in $METHODS; do
  SPEC="$(spec)"
  say "Installing with $M: $SPEC"
  if ! try_install "$M" "$SPEC" && [ -n "$EXTRAS" ]; then
    warn "extras [$EXTRAS] failed to install (often: no prebuilt wheel for this Python/OS, e.g. python-rtmidi)."
    warn "installing the core app without them; add them later by re-running with the flag once fixed."
    EXTRAS=""
    try_install "$M" "$(spec)" || true
  fi
  [ -n "$EXE" ] && [ -x "$EXE" ] || EXE=""
  if [ -n "$EXE" ] && probe "$EXE" --version; then INSTALLED="$M"; break; fi
  [ -n "$EXE" ] && warn "$M finished but $EXE does not run"
  EXE=""
  [ "$M" = "$LAST" ] || warn "install with $M failed; trying the next method"
done
if [ -z "$INSTALLED" ]; then
  diagnostics
  printf '%serror%s install failed with: %s. The messages above show each failing command and its exit code.\n' "$R" "$N" "$METHODS" >&2
  echo "   Please copy everything above into an issue: $REPO/issues/new" >&2
  exit 1
fi
METHOD="$INSTALLED"
VER="$("$EXE" --version 2>&1)"
ok "$VER -> $EXE (via $METHOD)"

# PATH
EXE_DIR="$(dirname "$EXE")"
case ":$PATH:" in
  *":$EXE_DIR:"*) ok "$EXE_DIR is on PATH" ;;
  *)
    LINE="export PATH=\"$EXE_DIR:\$PATH\"   # added by 8bms installer"
    if [ "$MODIFY_PATH" = 1 ]; then
      for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
        case "$rc" in */.profile) ;; *) [ -f "$rc" ] || continue ;; esac
        grep -qsF "$LINE" "$rc" || printf '\n%s\n' "$LINE" >> "$rc"
      done
      warn "added $EXE_DIR to PATH in your shell profile; open a new terminal or run:"
    else
      warn "$EXE_DIR is not on PATH; add this to your shell profile:"
    fi
    echo "   $LINE"
    ;;
esac
_first="$(command -v 8bms 2>/dev/null || true)"
[ -n "$_first" ] && [ "$_first" != "$EXE" ] && warn "another 8bms comes first on PATH: $_first"

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
