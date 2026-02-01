# Architecture Decision Log

This document captures the key architectural decisions and iterations made during development.

## Overview

Doc Sanitizer is an MCP (Model Context Protocol) server that sanitizes PII from documents using local LLMs via Ollama.

**Target Hardware**: MacBook Air M3 with 24GB RAM
**Default Model**: phi4:14b (chosen for quality/performance balance on M3)

---

## Iteration 1: Initial Implementation (SSE Transport)

**Decision**: Use SSE (Server-Sent Events) transport for MCP communication.

**Rationale**: SSE is the standard transport for MCP servers that need to work with web-based clients like Claude.ai.

**Implementation**:
- `src/server.py` - Starlette app with SSE endpoints
- Docker deployment with Ollama sidecar container

---

## Iteration 2: Claude Desktop Support (Stdio Transport)

**Problem**: Claude Desktop requires stdio-based MCP servers (command + args), not HTTP URLs.

**Decision**: Create a separate stdio-based server for Claude Desktop.

**Implementation**:
- Added `src/stdio_server.py` - Uses `mcp.server.stdio` transport
- Claude Desktop config uses `command` field pointing to Python interpreter

**Config example**:
```json
{
  "mcpServers": {
    "doc-sanitizer": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "src.stdio_server"],
      "env": {
        "PYTHONPATH": "/path/to/doc-sanitizer-mcp"
      }
    }
  }
}
```

---

## Iteration 3: HTTP Upload Architecture (File ID)

**Problem**: Claude Desktop was encoding files to base64 before sending through MCP, which is:
- Slow (encoding/decoding overhead)
- Memory-intensive (33% size increase)
- Inefficient for large documents

**Decision**: Implement a dual HTTP + MCP architecture:
1. HTTP server handles binary file uploads, returns a UUID `file_id`
2. MCP server accepts `file_id` and retrieves file from shared storage
3. Response is sanitized Markdown text (not binary)

**Benefits**:
- Efficient binary transfer via HTTP multipart
- Small payload through MCP (just UUID string)
- Files auto-delete after 5 minutes (TTL cleanup)

**Implementation**:
- Added `src/file_store.py` - UUID-based storage with TTL cleanup thread
- Added `src/http_server.py` - FastAPI upload endpoint (POST /upload)
- Updated both `stdio_server.py` and `server.py` to use file_id
- Added `start_http_server.sh` for local development

**Workflow**:
```
1. User uploads file:    curl -F "file=@doc.pdf" http://localhost:8080/upload
2. Server returns:       {"file_id": "abc-123-...", ...}
3. User calls MCP tool:  sanitize_document(file_id="abc-123-...")
4. Server returns:       Sanitized Markdown text
5. File auto-deleted after 5 minutes
```

---

## Iteration 4: Docker Portability (Named Volumes)

**Problem**: Initial docker-compose used host path mounts (`~/.doc-sanitizer:/app/data`) which:
- Depends on host filesystem paths
- Different users have different home directories
- Not portable across machines

**Decision**: Use Docker named volumes exclusively.

**Implementation**:
```yaml
volumes:
  ollama_data:     # Ollama models
  uploads_data:    # Temporary uploads (shared between http-server and mcp)
  profiles_data:   # Sanitization profiles (persistent)
```

---

## Current Architecture

### Local Development (Claude Desktop)
```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Claude Desktop │────▶│  stdio_server.py │────▶│   Ollama    │
│                 │     │  (MCP stdio)     │     │  (phi4:14b) │
└─────────────────┘     └────────┬─────────┘     └─────────────┘
                                 │
┌─────────────────┐              │ file_id
│  curl upload    │──▶ http_server.py ──▶ ~/.doc-sanitizer/uploads/
└─────────────────┘     (port 8080)
```

### Docker Deployment
```
┌─────────────────────────────────────────────────────────────┐
│                     docker-compose                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ http-server │  │ doc-sanitizer│  │      ollama        │ │
│  │  :8080      │  │  :8000 (SSE) │  │      :11434        │ │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────┘ │
│         │                │                                  │
│         └───────┬────────┘                                  │
│           uploads_data (shared volume)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
doc-sanitizer-mcp/
├── src/
│   ├── config_schema.py   # Pydantic models for PII types, profiles
│   ├── extractors.py      # Document text extraction (PDF, DOCX, etc.)
│   ├── file_store.py      # UUID storage with TTL cleanup
│   ├── http_server.py     # FastAPI upload server
│   ├── profiles.py        # Profile CRUD with JSON persistence
│   ├── prompts.py         # LLM prompt templates
│   ├── server.py          # SSE-based MCP server (Docker)
│   └── stdio_server.py    # Stdio-based MCP server (Claude Desktop)
├── tests/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── start_http_server.sh
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `phi4:14b` | Model for sanitization |
| `HTTP_BASE_URL` | `http://localhost:8080` | HTTP upload server URL |
| `HTTP_PORT` | `8080` | HTTP server port |
| `PORT` | `8000` | MCP SSE server port |
| `FILE_TTL_SECONDS` | `300` | File auto-delete timeout |
| `PROFILE_STORAGE` | `~/.doc-sanitizer/profiles.json` | Profile storage path |
| `LOG_LEVEL` | `INFO` | Logging level |
