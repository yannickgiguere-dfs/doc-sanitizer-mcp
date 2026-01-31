#!/bin/bash
set -e

echo "=== Doc Sanitizer MCP Server Setup ==="
echo ""

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Check for Docker Compose
if ! command -v docker compose &> /dev/null; then
    echo "Error: Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo "Created .env file. Edit it to customize settings."
else
    echo ".env file already exists."
fi

# Create data directory for profile persistence
DATA_DIR="$HOME/.doc-sanitizer"
if [ ! -d "$DATA_DIR" ]; then
    echo "Creating data directory at $DATA_DIR..."
    mkdir -p "$DATA_DIR"
fi

# Build and start containers
echo ""
echo "Building and starting Docker containers..."
docker compose up -d --build

# Wait for services to be healthy
echo ""
echo "Waiting for services to start..."
sleep 10

# Pull the default model
MODEL=$(grep OLLAMA_MODEL .env | cut -d '=' -f2)
MODEL=${MODEL:-phi4:14b}
echo ""
echo "Pulling Ollama model: $MODEL"
echo "This may take a while on first run..."
docker exec doc-sanitizer-ollama ollama pull "$MODEL"

# Verify services
echo ""
echo "Verifying services..."
docker compose ps

echo ""
echo "=== Setup Complete ==="
echo ""
echo "MCP Server URL: http://localhost:8000/sse"
echo "Ollama URL: http://localhost:11434"
echo ""
echo "To configure Claude Desktop, add to ~/Library/Application Support/Claude/claude_desktop_config.json:"
echo '{'
echo '  "mcpServers": {'
echo '    "doc-sanitizer": {'
echo '      "url": "http://localhost:8000/sse"'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "To change models, edit .env and restart: docker compose restart"
