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

# Create data and uploads directories
RUN mkdir -p /app/data /app/uploads

# Environment variables (can be overridden via docker-compose or .env)
ENV OLLAMA_MODEL=phi4:14b
ENV OLLAMA_HOST=http://ollama:11434
ENV HTTP_BASE_URL=http://localhost:8080
ENV PORT=8000
ENV HTTP_PORT=8080
ENV FILE_TTL_SECONDS=300
ENV LOG_LEVEL=INFO
ENV PROFILE_STORAGE=/app/data/profiles.json

# Expose MCP server port (8000) and HTTP upload port (8080)
EXPOSE 8000 8080

# Health check (can be overridden in docker-compose)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Default: Run the SSE-based MCP server
# Override in docker-compose to run HTTP server: ["python", "-m", "src.http_server"]
CMD ["python", "-m", "src.server"]
