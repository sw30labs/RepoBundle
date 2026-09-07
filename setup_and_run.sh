#!/usr/bin/env bash
# Check Python and launch the local RepoBundle browser dashboard.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
SETUP_ONLY=0
PORT="${REPOBUNDLE_PORT:-7790}"
OPEN_BROWSER=1
while [ "$#" -gt 0 ]; do
    case "$1" in
        --setup-only) SETUP_ONLY=1 ;;
        --no-browser) OPEN_BROWSER=0 ;;
        --port)
            if [ "$#" -lt 2 ]; then echo "ERROR: --port needs a value" >&2; exit 2; fi
            PORT="$2"; shift ;;
        --help|-h)
            echo "Usage: ./setup_and_run.sh [--setup-only] [--no-browser] [--port PORT]"
            echo "Set PYTHON_BIN to select Python; REPOBUNDLE_PORT defaults to 7790."
            exit 0 ;;
        *) echo "Unknown option: $1 (use --help)" >&2; exit 2 ;;
    esac
    shift
done
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "ERROR: --port must be between 1 and 65535" >&2; exit 2
fi
check_python() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' 2>/dev/null
}
if [ -n "${PYTHON_BIN:-}" ]; then
    if ! check_python "$PYTHON_BIN"; then
        echo "ERROR: PYTHON_BIN must point to Python 3.7+." >&2; exit 1
    fi
else
    PYTHON_BIN=""
    for candidate in .venv/bin/python python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && check_python "$candidate"; then
            PYTHON_BIN="$candidate"; break
        fi
    done
    if [ -z "$PYTHON_BIN" ]; then echo "ERROR: Install Python 3.7+ or set PYTHON_BIN." >&2; exit 1; fi
fi
echo "==> Using $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"
"$PYTHON_BIN" -c 'import sys; sys.path.insert(0, "scripts"); import web_gui'
echo "==> Environment ready; no pip dependencies required."
if [ "$SETUP_ONLY" -eq 1 ]; then exit 0; fi
GUI_ARGS=(--port "$PORT")
if [ "$OPEN_BROWSER" -eq 0 ]; then GUI_ARGS+=(--no-browser); fi
exec "$PYTHON_BIN" scripts/gui.py "${GUI_ARGS[@]}"
