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

# Load environment variables from .env.agent.secret
load_dotenv(".env.agent.secret")

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


# Tool definitions for LLM function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository. Use this to read the content of a specific file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
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
            "description": "List files and directories at a given path. Use this to discover what files exist in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki')",
                    }
                },
                "required": ["path"],
            },
        },
    },
]

# System prompt for the agent
SYSTEM_PROMPT = """You are a helpful documentation agent. You have access to tools to read files and list directories in the project wiki.

When answering questions:
1. First use list_files to discover relevant wiki files if you don't know the exact file path
2. Then use read_file to read the content and find the answer
3. Include the source reference as: wiki/filename.md#section-anchor (use the section heading, lowercase with hyphens)
4. Only call one tool at a time and wait for results
5. After you have found the answer, respond with the final answer without calling more tools

Available tools:
- read_file(path: str) - Read a file from the project
- list_files(path: str) - List files in a directory

Always include the source field in your final answer referencing the wiki file you read."""


def execute_tool(tool_name: str, args: dict) -> str:
    """Execute a tool and return the result."""
    print(f"Executing tool: {tool_name}({args})", file=sys.stderr)

    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
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
                # Try to extract a section anchor from the answer
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
