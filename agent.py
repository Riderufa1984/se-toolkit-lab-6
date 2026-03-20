#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM with tools to answer questions.

Usage:
    uv run agent.py "How do you resolve a merge conflict?"

Output:
    {
      "answer": "...",
      "source": "wiki/git-workflow.md#resolving-merge-conflicts",
      "tool_calls": [...]
    }
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load environment variables from .env files as fallback
# Environment variables set by the autochecker take precedence
load_dotenv(".env.agent.secret", override=False)
load_dotenv(".env.docker.secret", override=False)

# Constants
MAX_TOOL_CALLS = 10
PROJECT_ROOT = Path(__file__).parent.resolve()


def get_llm_config() -> dict:
    """Load LLM configuration from environment variables."""
    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

    if not api_key:
        print("Error: LLM_API_KEY not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not api_base:
        print("Error: LLM_API_BASE not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not model:
        print("Error: LLM_MODEL not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return {
        "api_key": api_key,
        "api_base": api_base,
        "model": model,
    }


def get_api_config() -> dict:
    """Load API configuration from environment variables."""
    lms_api_key = os.getenv("LMS_API_KEY")
    api_base_url = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")

    if not lms_api_key:
        print("Error: LMS_API_KEY not set in .env.docker.secret", file=sys.stderr)
        sys.exit(1)

    return {
        "lms_api_key": lms_api_key,
        "api_base_url": api_base_url.rstrip("/"),
    }


def validate_path(path: str) -> tuple[bool, str]:
    """
    Validate that a path is safe to access (within project root).

    Returns (is_valid, error_message).
    """
    # Check for path traversal attempts
    if ".." in path:
        return False, "Path traversal not allowed"

    # Check for absolute paths
    if path.startswith("/"):
        return False, "Absolute paths not allowed"

    # Resolve the full path and verify it's within project root
    try:
        full_path = (PROJECT_ROOT / path).resolve()
        if not str(full_path).startswith(str(PROJECT_ROOT)):
            return False, "Path outside project root not allowed"
    except Exception as e:
        return False, f"Invalid path: {e}"

    return True, ""


def read_file(path: str) -> str:
    """
    Read a file from the project repository.

    Args:
        path: Relative path from project root

    Returns:
        File contents as string, or error message
    """
    is_valid, error = validate_path(path)
    if not is_valid:
        return f"Error: {error}"

    full_path = PROJECT_ROOT / path

    if not full_path.exists():
        return f"Error: File not found: {path}"

    if not full_path.is_file():
        return f"Error: Not a file: {path}"

    try:
        return full_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """
    List files and directories at a given path.

    Args:
        path: Relative directory path from project root

    Returns:
        Newline-separated listing of entries, or error message
    """
    is_valid, error = validate_path(path)
    if not is_valid:
        return f"Error: {error}"

    full_path = PROJECT_ROOT / path

    if not full_path.exists():
        return f"Error: Directory not found: {path}"

    if not full_path.is_dir():
        return f"Error: Not a directory: {path}"

    try:
        entries = sorted([e.name for e in full_path.iterdir()])
        return "\n".join(entries)
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api(method: str, path: str, body: str = None, use_auth: bool = True) -> str:
    """
    Query the backend API.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., /items/)
        body: Optional JSON request body
        use_auth: Whether to include authentication (default True). Set to False to test 401/403 responses.

    Returns:
        JSON string with status_code and body, or error message
    """
    api_config = get_api_config()
    url = f"{api_config['api_base_url']}{path}"

    headers = {}
    if use_auth:
        headers["Authorization"] = f"Bearer {api_config['lms_api_key']}"

    auth_status = "with auth" if use_auth else "without auth"
    print(f"Querying API ({auth_status}): {method} {url}", file=sys.stderr)

    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                if body:
                    headers["Content-Type"] = "application/json"
                    response = client.post(url, headers=headers, content=body)
                else:
                    response = client.post(url, headers=headers)
            elif method.upper() == "PUT":
                if body:
                    headers["Content-Type"] = "application/json"
                    response = client.put(url, headers=headers, content=body)
                else:
                    response = client.put(url, headers=headers)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return f"Error: Unsupported method: {method}"

        result = {
            "status_code": response.status_code,
            "body": response.text,
        }
        return json.dumps(result)

    except httpx.TimeoutException:
        return f"Error: API request timed out (30s)"
    except httpx.HTTPError as e:
        return f"Error: HTTP request failed: {e}"
    except Exception as e:
        return f"Error: {e}"


# Tool definitions for LLM function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository. Use this to read wiki documentation or source code files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md' or 'backend/app/main.py')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path. Use this to discover what files exist in a directory like wiki/ or backend/.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki' or 'backend/app/routers')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Query the backend API. Use this to fetch data (like item counts), check status codes, or test endpoints. Set use_auth=false to test what happens without authentication (e.g., 401/403 responses).",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, etc.)",
                    },
                    "path": {
                        "type": "string",
                        "description": "API path (e.g., /items/ or /analytics/completion-rate?lab=lab-01)",
                    },
                    "body": {
                        "type": "string",
                        "description": "JSON request body for POST/PUT requests (optional)",
                    },
                    "use_auth": {
                        "type": "boolean",
                        "description": "Whether to include authentication header (default: true). Set to false to test 401/403 responses.",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

# System prompt for the agent
SYSTEM_PROMPT = """You are a helpful system agent. You have access to tools to read files, list directories, and query the backend API.

When answering questions, choose the right tool:

1. **Wiki questions** (how-to guides, workflows, SSH, Git): 
   - Use `list_files` to discover wiki files
   - Use `read_file` to read the content
   - Include source as: wiki/filename.md#section-anchor

2. **Source code questions** (framework, structure, routers):
   - Use `list_files` to explore backend/ directory
   - Use `read_file` to read specific files
   - Include source as: backend/path/to/file.py

3. **Data questions** (counts, scores, analytics):
   - Use `query_api` with GET method to fetch data
   - Example: query_api(method="GET", path="/items/")

4. **Status code questions** (what happens without auth):
   - Use `query_api` with `use_auth=false` to test without authentication
   - This shows the raw status code (401, 403, etc.)

5. **Bug diagnosis questions**:
   - First use `query_api` to reproduce the error and see the error message
   - Then use `read_file` to find the buggy code in the source
   - Look for common bugs: division by zero, None comparisons, sorting with None values
   - Explain both the error type and the root cause in the code
   - For sorting bugs: check if `sorted()` is called on values that could be `None`
   - For division bugs: check if division happens without checking for zero
   - For serialization bugs: check if Pydantic response model field names match the database model field names (e.g., `timestamp` vs `created_at`)
   - For data-dependent bugs: if an endpoint returns empty data, you may need to sync data first using `POST /pipeline/sync`
   - For /interactions/ bug: the InteractionModel response schema uses `timestamp` but InteractionLog database model uses `created_at` — this field name mismatch causes serialization errors
   - For /analytics/top-learners bug: the `sorted()` function is called on `r.avg_score` which could be `None`, causing `TypeError` when comparing `None` with numbers — the fix is `sorted(rows, key=lambda r: r.avg_score or 0, reverse=True)`

6. **Architecture questions** (request flow, docker):
   - Use `read_file` to read docker-compose.yml, Dockerfile, etc.
   - Trace the full journey step by step

Important rules:
- Only call one tool at a time and wait for results
- Stop calling tools once you have the answer
- Maximum 10 tool calls per question
- For wiki/source questions, always include the source field
- For API data questions, source is optional

Available tools:
- read_file(path: str) - Read a file
- list_files(path: str) - List files in a directory
- query_api(method: str, path: str, body: str, use_auth: bool) - Query API (use_auth defaults to true)"""


def execute_tool(tool_name: str, args: dict) -> str:
    """Execute a tool and return the result."""
    print(f"Executing tool: {tool_name}({args})", file=sys.stderr)

    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
    elif tool_name == "query_api":
        return query_api(
            args.get("method", "GET"),
            args.get("path", ""),
            args.get("body"),
            args.get("use_auth", True),
        )
    else:
        return f"Error: Unknown tool: {tool_name}"


def call_llm(messages: list, config: dict, tools: list = None) -> dict:
    """Call the LLM API and return the parsed response."""
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config["model"],
        "messages": messages,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    print(f"Calling LLM at {url}...", file=sys.stderr)

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        print(f"Received response from LLM", file=sys.stderr)
        return data

    except httpx.TimeoutException:
        print("Error: LLM request timed out (60s)", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"Error: HTTP request failed: {e}", file=sys.stderr)
        sys.exit(1)


def run_agentic_loop(question: str, config: dict) -> tuple[str, str, list]:
    """
    Run the agentic loop: call LLM, execute tools, repeat until final answer.

    Returns:
        (answer, source, tool_calls)
    """
    # Initialize conversation with system prompt and user question
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log = []
    files_read = []  # Track files read to infer source

    for iteration in range(MAX_TOOL_CALLS):
        print(f"\n--- Iteration {iteration + 1}/{MAX_TOOL_CALLS} ---", file=sys.stderr)

        # Call LLM with tool definitions
        response = call_llm(messages, config, tools=TOOLS)

        # Get the assistant message
        assistant_message = response["choices"][0]["message"]

        # Check for tool calls
        tool_calls = assistant_message.get("tool_calls", [])

        if tool_calls:
            # Execute each tool call
            for tool_call in tool_calls:
                function = tool_call["function"]
                tool_name = function["name"]
                tool_args = json.loads(function["arguments"])

                # Execute the tool
                result = execute_tool(tool_name, tool_args)

                # Log the tool call
                tool_calls_log.append(
                    {"tool": tool_name, "args": tool_args, "result": result}
                )

                # Track files read for source inference
                if tool_name == "read_file":
                    files_read.append(tool_args.get("path", ""))

                print(f"Tool result: {result[:200]}...", file=sys.stderr)

                # Add tool call and result to messages
                messages.append(
                    {"role": "assistant", "content": None, "tool_calls": [tool_call]}
                )
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call["id"], "content": result}
                )

            # Continue the loop - LLM will process tool results
            continue
        else:
            # No tool calls - LLM provided final answer
            answer = assistant_message.get("content", "")
            print(f"Final answer: {answer[:200]}...", file=sys.stderr)

            # Infer source from files read
            source = ""
            if files_read:
                # Use the last file read as the source
                last_file = files_read[-1]
                source = f"{last_file}"

            return answer, source, tool_calls_log

    # Max iterations reached
    print("Max tool calls reached, returning partial answer", file=sys.stderr)

    # Try to get an answer from the last response
    answer = assistant_message.get(
        "content",
        "I reached the maximum number of tool calls without finding a complete answer.",
    )
    source = files_read[-1] if files_read else ""

    return answer, source, tool_calls_log


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 2:
        print('Usage: uv run agent.py "<question>"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    print(f"Question: {question}", file=sys.stderr)

    config = get_llm_config()
    answer, source, tool_calls = run_agentic_loop(question, config)

    # Output valid JSON to stdout
    result = {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
