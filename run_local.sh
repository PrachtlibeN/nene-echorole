#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "       EchoRole Local Runner            "
echo "========================================"

# 1. Environment file check
if [ ! -f .env ] && [ -f .env.example ]; then
    echo "[1/3] Creating .env from .env.example..."
    cp .env.example .env
else
    echo "[1/3] .env file checked."
fi

# 2. Setup and run Backend
echo ""
echo "[2/3] Setting up Backend..."
BACKEND_DIR="$SCRIPT_DIR/backend"
mkdir -p "$BACKEND_DIR/data"

PYTHON_CMD="python3"
if [ -f "$BACKEND_DIR/.venv/bin/python" ]; then
    PYTHON_CMD="$BACKEND_DIR/.venv/bin/python"
elif ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

echo "Applying database migrations..."
(cd "$BACKEND_DIR" && "$PYTHON_CMD" -m alembic upgrade head) || echo "Migration warning: check python dependencies."

echo "Starting backend server on port 8000..."
(cd "$BACKEND_DIR" && exec "$PYTHON_CMD" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

cleanup() {
    echo ""
    echo "Shutting down servers..."
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    echo "EchoRole stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 3. Setup and run Frontend
echo ""
echo "[3/3] Setting up Frontend..."
FRONTEND_DIR="$SCRIPT_DIR/frontend"
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "Installing frontend dependencies (npm install)..."
    (cd "$FRONTEND_DIR" && npm install)
fi

echo ""
echo "========================================"
echo " EchoRole is running successfully!      "
echo " - Backend API:  http://127.0.0.1:8000  "
echo " - Frontend UI:  http://localhost:5173  "
echo " Press Ctrl+C to stop both servers.     "
echo "========================================"
echo ""

cd "$FRONTEND_DIR"
npm run dev
