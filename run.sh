#!/bin/bash
# TrendScope - Local Development Runner
# For production: deploy to Render.com using render.yaml

set -e

echo "════════════════════════════════════════════"
echo "  TrendScope — Local Dev Mode"
echo "════════════════════════════════════════════"

# Detect Python
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "❌ Python is not installed. Install Python 3.9+"
    exit 1
fi

echo "✅ Python: $($PYTHON --version)"

# Install Python dependencies
echo ""
echo "📦 Installing dependencies..."
PIP_REQUIRE_VIRTUALENV=false $PYTHON -m pip install -r requirements.txt --quiet --upgrade || {
    echo "⚠️ Bulk install failed, trying individually..."
    for pkg in flask flask-cors requests beautifulsoup4 lxml apscheduler psycopg2-binary python-dotenv curl-cffi playwright gunicorn; do
        PIP_REQUIRE_VIRTUALENV=false $PYTHON -m pip install $pkg --quiet 2>&1 || echo "  ⚠️ $pkg failed"
    done
}

# Install Playwright browser
echo ""
echo "🎭 Installing Playwright Chromium (~150MB, one-time)..."
$PYTHON -m playwright install chromium 2>&1 || echo "⚠️ Playwright install failed (will use fallback)"

# Linux deps
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    $PYTHON -m playwright install-deps chromium 2>&1 || echo "⚠️ System deps failed (may need sudo)"
fi

# Check for .env file
if [ ! -f .env ]; then
    echo ""
    echo "ℹ️  No .env file found — using local JSON storage"
    echo "   To use Supabase PostgreSQL, copy .env.example to .env and fill in DATABASE_URL"
fi

# Init data file (if no DATABASE_URL)
if [ ! -f data.json ] && [ -z "$DATABASE_URL" ]; then
    echo '{}' > data.json
fi

echo ""
echo "════════════════════════════════════════════"
echo "🚀 Server: http://localhost:5000"
echo "   Press Ctrl+C to stop"
echo "════════════════════════════════════════════"
echo ""
$PYTHON app.py
