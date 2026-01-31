FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create data directory for profile persistence
RUN mkdir -p /app/data

# Environment variables (can be overridden via docker-compose or .env)
ENV OLLAMA_MODEL=phi4:14b
ENV OLLAMA_HOST=http://ollama:11434
ENV PORT=8000
ENV LOG_LEVEL=INFO
ENV PROFILE_STORAGE=/app/data/profiles.json

# Expose MCP server port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the MCP server
CMD ["python", "-m", "src.server"]
