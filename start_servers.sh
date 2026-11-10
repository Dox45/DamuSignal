#!/usr/bin/env bash
# Terumo BCT Blood Inventory Intelligence - Launch Script

echo "======================================================================"
echo "🩸 Starting Blood Inventory Intelligence & Early Warning System"
echo "======================================================================"

# 1. Start FastAPI Backend on Port 8000
echo "Starting FastAPI Backend on http://localhost:8000..."
./.venv/bin/uvicorn api:app --app-dir gitcodes --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 2. Start Next.js Frontend on Port 3000
echo "Starting Next.js Frontend on http://localhost:3000..."
cd ui && pnpm dev --port 3000 &
FRONTEND_PID=$!

echo ""
echo "✅ Both services running!"
echo "   - Web UI Dashboard: http://localhost:3000"
echo "   - Backend REST API: http://localhost:8000"
echo "   - Swagger Docs:     http://localhost:8000/docs"
echo "   - Press Ctrl+C to terminate both servers."
echo ""

# Handle clean shutdown on Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT TERM
wait

