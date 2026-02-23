"""
Local MCP Server for folder audit: list_files and read_file_content.
Uses the Python MCP SDK (FastMCP) with streamable HTTP on http://localhost:8000.
Target directory is set via --path.

REST endpoints for chat app:
  GET /list_files  - returns list of files/subdirs (one level)
  GET /read_file?path=foo.txt  - returns text content of file (path relative to target)

Install and run:
    pip install "mcp[cli]"
    python mcp_server.py --path /path/to/audit/dir
    # Or with custom host/port:
    python mcp_server.py --path /path/to/audit/dir --host 127.0.0.1 --port 8000
"""

import argparse
import contextlib
import os

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

# Set by main() after parsing --path
TARGET_PATH: str = ""


def _resolve_target() -> str:
    """Return resolved absolute path of target directory; raise if invalid."""
    if not TARGET_PATH:
        raise ValueError("Target path not set (--path required)")
    resolved = os.path.abspath(os.path.expanduser(TARGET_PATH))
    if not os.path.isdir(resolved):
        raise NotADirectoryError(f"Not a directory: {resolved}")
    return resolved


def _safe_join_and_validate(filename: str) -> str:
    """Join filename to target path and ensure result is inside target; return resolved path or raise."""
    base = _resolve_target()
    # Prevent directory traversal: join and then resolve
    joined = os.path.normpath(os.path.join(base, filename))
    resolved = os.path.abspath(joined)
    if not resolved.startswith(base):
        raise PermissionError(f"Path escapes target directory: {filename}")
    return resolved


mcp = FastMCP(
    "File Audit Server",
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
def list_files() -> str:
    """Returns a list of all files and subdirectories in the target audit directory (one level)."""
    base = _resolve_target()
    try:
        entries = os.listdir(base)
    except OSError as e:
        return f"Error listing directory: {e}"
    lines = []
    for name in sorted(entries):
        full = os.path.join(base, name)
        kind = "dir" if os.path.isdir(full) else "file"
        lines.append(f"  {kind}: {name}")
    return "Target: " + base + "\n\n" + "\n".join(lines) if lines else "Target: " + base + "\n\n(empty)"


def _read_file_as_text(resolved: str, filename: str) -> str:
    """Read file as text; return a clear message for binary formats (e.g. .xlsx)."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".xlsx", ".xls"):
        return (
            f"This file is an Excel spreadsheet ({filename}). "
            "I can only display plain text file contents. "
            "Describe the columns or sample entries in the file to get help, or export the sheet to CSV and ask again."
        )
    if ext in (".docx", ".doc", ".pdf", ".zip", ".png", ".jpg", ".jpeg"):
        return (
            f"This file is binary ({filename}). "
            "I can only display plain text. "
            "Describe what you need (e.g. columns, sample data) to get help."
        )
    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        return f"Error reading file: {e}"


@mcp.tool()
def read_file_content(filename: str) -> str:
    """Read and return the text content of a file in the target audit directory. filename must be relative to the target path (e.g. 'foo.txt' or 'subdir/bar.txt')."""
    try:
        resolved = _safe_join_and_validate(filename)
    except (ValueError, NotADirectoryError, PermissionError) as e:
        return f"Error: {e}"
    if not os.path.isfile(resolved):
        return f"Not a file or not found: {filename}"
    return _read_file_as_text(resolved, filename)


def _list_files_route(request):
    """REST handler: GET /list_files."""
    return PlainTextResponse(list_files())


def _read_file_route(request):
    """REST handler: GET /read_file?path=..."""
    path = request.query_params.get("path", "").strip()
    if not path:
        return PlainTextResponse("Error: missing path query param (e.g. ?path=foo.txt)", status_code=400)
    return PlainTextResponse(read_file_content(path))


@contextlib.asynccontextmanager
async def _lifespan(app):
    async with mcp.session_manager.run():
        yield


def main() -> None:
    global TARGET_PATH
    parser = argparse.ArgumentParser(description="MCP File Audit Server (list_files, read_file_content)")
    parser.add_argument(
        "--path",
        required=True,
        help="Target audit directory path to list and read files from",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    args = parser.parse_args()

    TARGET_PATH = os.path.abspath(os.path.expanduser(args.path))
    if not os.path.isdir(TARGET_PATH):
        raise SystemExit(f"Error: not a directory: {TARGET_PATH}")

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    app = Starlette(
        routes=[
            Route("/list_files", _list_files_route, methods=["GET"]),
            Route("/read_file", _read_file_route, methods=["GET"]),
            Mount("/", mcp.streamable_http_app()),
        ],
        lifespan=_lifespan,
    )
    print(f"Target audit directory: {TARGET_PATH}")
    print(f"Serving MCP + REST at http://{args.host}:{args.port}/")
    print("  GET /list_files   - list files and subdirs")
    print("  GET /read_file?path=... - read file content")
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
