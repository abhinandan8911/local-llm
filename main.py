"""
Local LLM Chat with optional MCP file access.
Chat UI (streaming) + when the user asks about files, call MCP server for list_files or read_file_content.
"""

import re
import streamlit as st
from openai import OpenAI

import urllib.request

LM_STUDIO_URL = "http://localhost:1234/v1"
OLLAMA_URL = "http://localhost:11434/v1"
DEFAULT_MCP_URL = "http://localhost:8000"

if "messages" not in st.session_state:
    st.session_state.messages = []


def fetch_mcp_list_files(mcp_url: str) -> str | None:
    """GET mcp_url/list_files; return response text or None on error."""
    url = mcp_url.rstrip("/") + "/list_files"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def fetch_mcp_read_file(mcp_url: str, path: str) -> str | None:
    """GET mcp_url/read_file?path=...; return response text or None on error."""
    from urllib.parse import quote
    url = mcp_url.rstrip("/") + "/read_file?path=" + quote(path, safe="")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def wants_list_files(message: str) -> bool:
    """Heuristic: user is asking to list files/directory."""
    m = message.lower().strip()
    if not m:
        return False
    if "list file" in m or "list dir" in m or "list directory" in m:
        return True
    if "what file" in m or "show file" in m or "which file" in m:
        return True
    if m in ("list", "list files", "list dir", "files", "dir", "directory"):
        return True
    if "files in" in m or "files in the" in m or "contents of the folder" in m:
        return True
    return False


def extract_read_file_path(message: str) -> str | None:
    """Extract a file path from 'read file X', 'content of X', 'read X', etc. Handles names with spaces (e.g. 'Costco Expense.xlsx')."""
    m = message.strip()
    if not m:
        return None
    # Quoted path: "read file 'Costco Expense.xlsx'" or 'read file "foo bar.txt"'
    quoted = re.search(r"(?:read\s+file|content\s+of|read|show\s+content\s+of)\s+[\"']([^\"']+)[\"']", m, re.I)
    if quoted:
        return quoted.group(1).strip()
    # "read file Costco Expense.xlsx" or "read file Costco Expense.xlsx please" -> path can have spaces; end at token that contains "."
    prefix = re.search(r"(?:read\s+file|content\s+of|show\s+content\s+of)\s+(.+)", m, re.I | re.DOTALL)
    if prefix:
        rest = prefix.group(1).strip()
        # Take tokens until we hit one containing "." (filename extension)
        tokens = rest.split()
        for i, t in enumerate(tokens):
            if "." in t or "/" in t:
                path = " ".join(tokens[: i + 1]).strip(".,;\"'")
                if path:
                    return path
        if rest and ("." in rest or "/" in rest):
            return rest.strip(".,;\"'")
    # "read foo.txt" (single token after "read")
    match = re.search(r"(?:read\s+file|content\s+of|read|show\s+content\s+of)\s+[\"']?([^\s\"']+(?:\/[^\s\"']+)*)[\"']?", m, re.I)
    if match:
        return match.group(1).strip()
    # Single word that looks like a path
    words = m.split()
    for w in words:
        clean = w.strip(".,;\"'")
        if "/" in clean or (len(clean) > 1 and "." in clean):
            return clean
    return None


def get_file_context(mcp_url: str, user_message: str) -> str | None:
    """If user is asking about files, call MCP and return context string; else None."""
    if wants_list_files(user_message):
        text = fetch_mcp_list_files(mcp_url)
        if text is not None:
            return "Context from file system (list of files and subdirectories):\n" + text
        return None
    path = extract_read_file_path(user_message)
    if path:
        text = fetch_mcp_read_file(mcp_url, path)
        if text is not None:
            return "Context from file system (content of " + path + "):\n" + text
    return None


def render_sidebar():
    with st.sidebar:
        st.header("Settings")
        server = st.selectbox(
            "Server",
            options=["LM Studio (port 1234)", "Ollama (port 11434)"],
            help="Pick the local server you are using.",
        )
        default_url = OLLAMA_URL if "Ollama" in server else LM_STUDIO_URL
        base_url = st.text_input(
            "API Base URL",
            value=default_url,
            help="LM Studio: http://localhost:1234/v1 — Ollama: http://localhost:11434/v1",
        )
        base_url = (base_url or "").rstrip("/")
        default_model = "qwen3:8b" if "Ollama" in server else "local"
        model = st.text_input(
            "Model",
            value=default_model,
            help="Ollama: e.g. qwen3:8b. LM Studio: name shown in app.",
        )
        temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
        max_tokens = st.number_input("Max Tokens", min_value=1, max_value=8192, value=512)
        mcp_url = st.text_input(
            "MCP Server URL",
            value=DEFAULT_MCP_URL,
            help="For file list/read when you ask about files (e.g. list files, read file foo.txt).",
        )
        mcp_url = (mcp_url or "").rstrip("/")
        if st.button("Clear chat"):
            st.session_state.messages = []
            st.rerun()
    return base_url, model, temperature, max_tokens, mcp_url


def stream_completion(client, model, messages, temperature, max_tokens):
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content is not None:
            yield chunk.choices[0].delta.content


def show_server_error():
    st.error(
        "Could not reach the local inference server. Make sure it is running.\n\n"
        "**LM Studio:** Start LM Studio, open the in-app **Local Server**, start the server, and load a model.\n\n"
        "**Ollama:** Run `ollama serve`, then `ollama pull <model>` (e.g. `ollama pull qwen3:8b`). "
        "Set **API Base URL** to `http://localhost:11434/v1` for Ollama."
    )


def show_model_not_found_error(model_name: str):
    st.error(
        f"Model **{model_name}** was not found.\n\n"
        "**Ollama:** Run `ollama list`, then `ollama pull <name>` (e.g. `ollama pull qwen3:8b`). "
        "Set **Model** in the sidebar to that name."
    )


def main():
    st.set_page_config(page_title="Local LLM Chat", page_icon="💬")
    st.title("Local LLM Chat")
    st.caption("Chat with your local model. Ask to list files or read a file (e.g. \"list files\", \"read file foo.txt\") to use the MCP server.")

    base_url, model, temperature, max_tokens, mcp_url = render_sidebar()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Message..."):
        st.session_state.messages.append({"role": "user", "content": prompt})

        file_context = get_file_context(mcp_url, prompt)
        api_messages = []
        if file_context:
            api_messages.append({"role": "system", "content": file_context})
        for m in st.session_state.messages:
            api_messages.append({"role": m["role"], "content": m["content"]})

        with st.chat_message("assistant"):
            try:
                client = OpenAI(base_url=base_url, api_key="not-needed")
                full_response = st.write_stream(
                    stream_completion(client, model, api_messages, temperature, max_tokens)
                )
                full_response = full_response or ""
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            except Exception as e:
                err_str = str(e).lower()
                if "404" in err_str and ("model" in err_str or "not found" in err_str):
                    show_model_not_found_error(model)
                else:
                    show_server_error()
                st.caption(f"Error: {e}")


if __name__ == "__main__":
    main()
