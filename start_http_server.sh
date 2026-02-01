#!/bin/bash
# Start the HTTP server for file uploads
# This should be running before using the MCP sanitize_document tool

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set defaults
export HTTP_HOST="${HTTP_HOST:-127.0.0.1}"
export HTTP_PORT="${HTTP_PORT:-8080}"
export FILE_TTL_SECONDS="${FILE_TTL_SECONDS:-300}"
export PYTHONPATH="${PYTHONPATH:-$SCRIPT_DIR}"

echo "Starting Doc Sanitizer HTTP Server..."
echo "  Upload endpoint: http://${HTTP_HOST}:${HTTP_PORT}/upload"
echo "  File TTL: ${FILE_TTL_SECONDS} seconds"
echo ""

python -m src.http_server
