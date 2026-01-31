# Doc Sanitizer MCP Server

A local, containerized MCP (Model Context Protocol) server that uses a local LLM (via Ollama) to sanitize documents by removing or transforming PII before content is sent to public LLM services.

## Features

- **Document Support**: Word (.docx), PDF, Excel (.xlsx/.xls), CSV, Plain text, Email (.eml)
- **PII Detection**: Names, emails, phone numbers, companies, addresses, financial data, IDs
- **Flexible Actions**: Delete, invent synthetic data, or keep partial information
- **Profile Management**: Create and manage multiple sanitization profiles via CLI
- **MCP Integration**: Works with Claude Desktop, Claude.ai, and Claude Code
- **Privacy First**: All processing happens locally - nothing sent to external services

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Ollama (installed automatically via Docker)

### Installation

```bash
git clone https://github.com/yourusername/doc-sanitizer-mcp.git
cd doc-sanitizer-mcp
./setup.sh
```

### Configuration

Edit `.env` to customize settings:

```bash
# Change LLM model (no rebuild required)
OLLAMA_MODEL=phi4:14b

# Alternative models:
# OLLAMA_MODEL=qwen2.5:7b    # Faster, less RAM
# OLLAMA_MODEL=llama3.2:3b   # Fastest, minimal RAM
```

To switch models:
```bash
# Pull new model
docker exec doc-sanitizer-ollama ollama pull qwen2.5:7b

# Update .env
sed -i '' 's/OLLAMA_MODEL=.*/OLLAMA_MODEL=qwen2.5:7b/' .env

# Restart
docker compose restart doc-sanitizer
```

### Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "doc-sanitizer": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

## Usage

### Via Claude (MCP Tools)

Once configured, you can ask Claude:
- "List available sanitization profiles"
- "Show me the default profile settings"
- "Sanitize this document using the high_privacy profile"

### Via CLI

```bash
# List profiles
doc-sanitizer profiles list

# Create a new profile
doc-sanitizer profiles create high_privacy

# Edit profile settings
doc-sanitizer profiles edit high_privacy --set person_name=delete --set company=delete

# Sanitize a document
doc-sanitizer sanitize document.docx --profile high_privacy
```

## Profile Management

Profiles define how each PII type is handled:

| PII Type | Available Actions |
|----------|-------------------|
| `person_name` | delete, invent, keep_part |
| `email` | delete, keep_part |
| `phone` | delete, invent, keep_part |
| `company` | keep_part, invent |
| `address` | delete, invent |
| `financial` | delete, invent |
| `id_numbers` | delete, invent |
| `date_of_birth` | delete, invent |

Profiles persist across container restarts (stored in `~/.doc-sanitizer/`).

## Documentation

- [Installation Guide](docs/INSTALLATION.md)
- [Usage Guide](docs/USAGE.md)
- [Profile Management](docs/PROFILES.md)
- [API Reference](docs/API.md)
- [Development Guide](docs/DEVELOPMENT.md)

## License

MIT License - see [LICENSE](LICENSE) for details.
