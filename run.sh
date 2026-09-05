#!/usr/bin/env bash
# One-click launcher for OmniSearch Universal Discovery Dashboard

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${OMNISEARCH_PORT:-8000}"
HOST="${OMNISEARCH_HOST:-0.0.0.0}"

# Check / create virtual environment if not present
if [ ! -d ".venv" ]; then
    echo "⚙️  Setting up virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e .
fi

# Ensure dependencies are installed
if [ ! -f ".venv/bin/uvicorn" ]; then
    echo "⚙️  Installing dependencies..."
    .venv/bin/pip install -e .
fi

# Refuse to start if the port is already taken
if command -v ss > /dev/null 2>&1; then
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE ":${PORT}$"; then
        echo "❌ Port ${PORT} is already in use. Stop the other process or set OMNISEARCH_PORT."
        exit 1
    fi
elif command -v lsof > /dev/null 2>&1; then
    if lsof -iTCP:"${PORT}" -sTCP:LISTEN > /dev/null 2>&1; then
        echo "❌ Port ${PORT} is already in use. Stop the other process or set OMNISEARCH_PORT."
        exit 1
    fi
fi

# Print sleek startup banner
echo ""
echo "======================================================================"
echo "  🚀 OmniSearch Universal Discovery Engine v2.2.0"
echo "======================================================================"
echo "  🌐 Live Dashboard:  http://localhost:${PORT}"
echo "  📡 API Docs:        http://localhost:${PORT}/docs"
echo "  🔍 Local URL:       http://127.0.0.1:${PORT}"
echo "======================================================================"
echo "  Explicit content source: set OMNISEARCH_ADULT_ENABLED=0 to disable"
echo "  Press Ctrl+C to stop the server"
echo ""

# Attempt to open browser in desktop environment (non-blocking)
if command -v xdg-open > /dev/null 2>&1; then
    (sleep 1 && xdg-open "http://localhost:${PORT}") > /dev/null 2>&1 &
elif command -v open > /dev/null 2>&1; then
    (sleep 1 && open "http://localhost:${PORT}") > /dev/null 2>&1 &
fi

# Start server
exec .venv/bin/uvicorn omnisearch.api.app:app --host "$HOST" --port "$PORT"
