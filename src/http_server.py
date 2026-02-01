"""HTTP Server for binary file uploads.

Provides endpoints for uploading files that will be processed by the MCP server.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .file_store import get_file_store, init_file_store

# Configure logging
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Maximum file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".csv", ".txt", ".eml"}


class UploadResponse(BaseModel):
    """Response model for file upload."""
    file_id: str
    filename: str
    size: int
    message: str


class FileInfo(BaseModel):
    """File information model."""
    file_id: str
    filename: str
    size: int
    created_at: str


class FilesListResponse(BaseModel):
    """Response model for listing files."""
    files: list[FileInfo]
    count: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Initialize file store with 5-minute TTL
    ttl_seconds = int(os.environ.get("FILE_TTL_SECONDS", 300))
    init_file_store(ttl_seconds=ttl_seconds)
    logger.info(f"HTTP Server started (file TTL: {ttl_seconds}s)")
    yield
    # Cleanup
    file_store = get_file_store()
    file_store.stop_cleanup_thread()
    logger.info("HTTP Server stopped")


app = FastAPI(
    title="Doc Sanitizer Upload API",
    description="HTTP API for uploading files to be sanitized by the MCP server",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "doc-sanitizer-http"}


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """Upload a file for sanitization.

    The file will be stored temporarily and can be referenced by file_id
    when calling the sanitize_document MCP tool.

    Files are automatically deleted after 5 minutes.
    """
    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Check file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Read file content
    content = await file.read()

    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # Save to file store
    file_store = get_file_store()
    stored_file = file_store.save_file(content, file.filename)

    logger.info(f"File uploaded: {stored_file.file_id} ({file.filename}, {len(content)} bytes)")

    return UploadResponse(
        file_id=stored_file.file_id,
        filename=stored_file.original_filename,
        size=stored_file.size,
        message="File uploaded successfully. Use this file_id with the sanitize_document tool. File will be deleted after 5 minutes."
    )


@app.get("/files", response_model=FilesListResponse)
async def list_files():
    """List all uploaded files (for debugging/admin purposes)."""
    file_store = get_file_store()
    files = file_store.list_files()

    return FilesListResponse(
        files=[
            FileInfo(
                file_id=f.file_id,
                filename=f.original_filename,
                size=f.size,
                created_at=f.created_at.isoformat(),
            )
            for f in files
        ],
        count=len(files),
    )


@app.delete("/files/{file_id}")
async def delete_file(file_id: str):
    """Delete a file by ID."""
    file_store = get_file_store()

    if file_store.delete_file(file_id):
        return {"message": f"File {file_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail="File not found")


def main():
    """Run the HTTP server."""
    import uvicorn

    host = os.environ.get("HTTP_HOST", "127.0.0.1")  # localhost only for security
    port = int(os.environ.get("HTTP_PORT", 8080))

    logger.info(f"Starting HTTP server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
