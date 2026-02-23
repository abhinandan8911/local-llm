# Local LLM Chat

Streamlit chat UI for a local LLM (Ollama or LM Studio) with optional file access via an MCP server. No cloud API keys required—everything runs locally.

## Features

- **Chat**: Streamlit sidebar (temperature, max tokens, server type, model) and main chat with streaming replies.
- **Local inference**: Connects to LM Studio (port 1234) or Ollama (port 11434) using the OpenAI-compatible API.
- **File access**: When you ask to list files or read a file by name, the app calls the MCP server and injects the result into the conversation.

## Prerequisites

- Python 3.10+
- A local inference server:
  - **Ollama**: `ollama serve`, then `ollama pull <model>` (e.g. `ollama pull qwen3:8b`).
  - **LM Studio**: Start the in-app local server and load a model.

Optional: run the MCP file server if you want to list/read files from a folder (see below).

## Setup

```bash
pip install -r requirements.txt
```

## Run the chat app

```bash
streamlit run main.py
```

In the sidebar, choose **Server** (LM Studio or Ollama), set **API Base URL** and **Model** to match your server, and chat. If you use the MCP server, set **MCP Server URL** (default `http://localhost:8000`).

## MCP file server (optional)

The MCP server exposes a folder for listing and reading files. The chat app calls it when you say things like “list files” or “read file foo.txt”.

**Install (separate from the chat app):**

```bash
pip install "mcp[cli]"
```

**Run:**

```bash
python mcp_server.py --path /path/to/your/audit/folder --port 8000
```

Replace `/path/to/your/audit/folder` with the directory you want to allow listing/reading from. The server listens on port 8000 by default.

- **List files**: In chat, e.g. “list files” or “what files are in the folder”.
- **Read file**: e.g. “read file notes.txt” or “read file subdir/report.txt”. Path is relative to the server’s `--path`. Binary files (e.g. `.xlsx`) return a short message instead of raw bytes.

## Project layout

| File              | Purpose                                      |
|-------------------|----------------------------------------------|
| `main.py`         | Streamlit chat app (local LLM + optional MCP) |
| `mcp_server.py`   | MCP server: list/read files in a target dir   |
| `requirements.txt`| Dependencies for the chat app                |

## Security / credentials

- The app talks only to **local** services (localhost). No cloud API keys are used.
- The chat app uses a placeholder `api_key` for the OpenAI client because LM Studio and Ollama do not require authentication when bound to localhost.
- Do not put secrets in the repo or in Streamlit secrets unless you intend to use them; the app does not require any credentials for local-only use.
- The MCP server only serves files under the directory you pass to `--path`; paths are validated to prevent directory traversal.

## License

MIT
