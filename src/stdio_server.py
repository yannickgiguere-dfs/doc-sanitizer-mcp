"""Stdio-based MCP Server for Claude Desktop integration."""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Optional

import ollama
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .config_schema import PIIAction, PIIType
from .extractors import DocumentExtractor, ExtractionError
from .file_store import get_file_store, init_file_store
from .profiles import ProfileManager, ProfileError, ProfileNotFoundError
from .prompts import build_sanitization_prompt, build_yaml_frontmatter

# Configure logging to stderr (stdout is used for MCP communication)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    stream=sys.stderr,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global instances
profile_manager: Optional[ProfileManager] = None
document_extractor: Optional[DocumentExtractor] = None


def get_ollama_client() -> ollama.Client:
    """Get configured Ollama client."""
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return ollama.Client(host=host)


def get_ollama_model() -> str:
    """Get configured Ollama model name."""
    return os.environ.get("OLLAMA_MODEL", "phi4:14b")


def get_profile_storage_path() -> str:
    """Get profile storage path."""
    if path := os.environ.get("PROFILE_STORAGE"):
        return path
    return os.path.expanduser("~/.doc-sanitizer/profiles.json")


def get_http_base_url() -> str:
    """Get the HTTP server base URL."""
    return os.environ.get("HTTP_BASE_URL", "http://localhost:8080")


def init_globals():
    """Initialize global instances."""
    global profile_manager, document_extractor

    storage_path = get_profile_storage_path()
    profile_manager = ProfileManager(storage_path)
    document_extractor = DocumentExtractor()

    # Initialize file store with 5-minute TTL
    ttl_seconds = int(os.environ.get("FILE_TTL_SECONDS", 300))
    init_file_store(ttl_seconds=ttl_seconds)

    logger.info(f"Initialized with profile storage: {storage_path}")


async def handle_get_profile(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle get_profile tool call."""
    profile_name = arguments.get("profile")
    profile_id = arguments.get("profile_id")

    try:
        if profile_id is not None:
            profile = profile_manager.get_profile_by_id(profile_id)
        elif profile_name is not None:
            profile = profile_manager.get_profile_by_name(profile_name)
        else:
            profile = profile_manager.get_default_profile()

        detail = profile_manager.format_profile_detail(profile.id)
        config_json = json.dumps(profile.config.model_dump(), indent=2)

        result = f"""{detail}

## JSON Configuration

```json
{config_json}
```
"""
        return [TextContent(type="text", text=result)]

    except ProfileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_list_profiles(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle list_profiles tool call."""
    table = profile_manager.format_profiles_table()

    result = f"""## Available Sanitization Profiles

{table}

Use `get_profile` with a profile name or ID to see detailed settings.
"""
    return [TextContent(type="text", text=result)]


async def handle_sanitize_document(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle sanitize_document tool call.

    Accepts a file_id (from HTTP upload) and returns sanitized markdown text.
    """
    file_id = arguments.get("file_id")
    profile_name = arguments.get("profile")
    profile_id = arguments.get("profile_id")

    if not file_id:
        base_url = get_http_base_url()
        return [TextContent(type="text", text=f"""Error: file_id is required.

To sanitize a document:
1. First upload the file: curl -F "file=@document.pdf" {base_url}/upload
2. Use the returned file_id with this tool
""")]

    # Get profile
    try:
        if profile_id is not None:
            profile = profile_manager.get_profile_by_id(profile_id)
        elif profile_name is not None:
            profile = profile_manager.get_profile_by_name(profile_name)
        else:
            profile = profile_manager.get_default_profile()
    except ProfileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]

    # Get file from store
    file_store = get_file_store()
    stored_file = file_store.get_file(file_id)

    if not stored_file:
        return [TextContent(type="text", text=f"Error: File not found: {file_id}. Files are deleted after 5 minutes. Please upload again.")]

    # Read file content
    content = file_store.read_file(file_id)
    if not content:
        return [TextContent(type="text", text=f"Error: Could not read file: {file_id}")]

    # Extract document text
    try:
        extracted = document_extractor.extract(content, stored_file.original_filename)
    except ExtractionError as e:
        return [TextContent(type="text", text=f"Error extracting document: {str(e)}")]

    # Build prompt and call LLM
    prompt = build_sanitization_prompt(extracted.content, profile)
    model = get_ollama_model()

    try:
        client = get_ollama_client()
        logger.info(f"Calling Ollama with model {model} for file {file_id}")
        response = client.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 8192,
            },
        )
        sanitized_content = response["response"]
    except Exception as e:
        logger.exception("LLM call failed")
        return [TextContent(type="text", text=f"Error calling LLM: {str(e)}")]

    # Build output with YAML frontmatter
    frontmatter = build_yaml_frontmatter(
        source_type=extracted.source_type,
        model_used=model,
        profile_name=profile.name,
    )

    # Clean up the uploaded file (already processed)
    file_store.delete_file(file_id)
    logger.info(f"Processed and cleaned up file: {file_id}")

    result = frontmatter + sanitized_content
    return [TextContent(type="text", text=result)]


async def main():
    """Run the stdio MCP server."""
    init_globals()

    server = Server("doc-sanitizer")
    base_url = get_http_base_url()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="get_profile",
                description="Get details of a sanitization profile. Shows how each PII type will be handled.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "profile": {
                            "type": "string",
                            "description": "Profile name (optional, defaults to 'default')",
                        },
                        "profile_id": {
                            "type": "integer",
                            "description": "Profile ID (alternative to name)",
                        },
                    },
                },
            ),
            Tool(
                name="list_profiles",
                description="List all available sanitization profiles with their PII handling settings.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="sanitize_document",
                description=f"""Sanitize a document by removing or transforming PII according to a profile.

IMPORTANT: Before calling this tool, the user must upload the file via HTTP:
  curl -F "file=@document.pdf" {base_url}/upload

This returns a file_id to use with this tool. Files are automatically deleted after 5 minutes.

Returns: Sanitized document as Markdown text with YAML frontmatter.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "UUID of the uploaded file (from HTTP upload endpoint)",
                        },
                        "profile": {
                            "type": "string",
                            "description": "Profile name to use (optional, defaults to 'default')",
                        },
                        "profile_id": {
                            "type": "integer",
                            "description": "Profile ID to use (alternative to name)",
                        },
                    },
                    "required": ["file_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if name == "get_profile":
                return await handle_get_profile(arguments)
            elif name == "list_profiles":
                return await handle_list_profiles(arguments)
            elif name == "sanitize_document":
                return await handle_sanitize_document(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.exception(f"Error in tool {name}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    logger.info("Starting Doc Sanitizer MCP Server (stdio mode)")
    logger.info(f"HTTP upload endpoint: {base_url}/upload")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
