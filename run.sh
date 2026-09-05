#!/usr/bin/env bash
# One-click launcher for OmniSearch Universal Discovery Dashboard

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT=8000
HOST="0.0.0.0"

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

# Print sleek startup banner
echo ""
echo "======================================================================"
echo "  🚀 OmniSearch Universal Discovery Engine"
echo "======================================================================"
echo "  🌐 Live Dashboard:  http://localhost:${PORT}"
echo "  📡 API Docs:        http://localhost:${PORT}/docs"
echo "  🔍 Local URL:       http://127.0.0.1:${PORT}"
echo "======================================================================"
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
