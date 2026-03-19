# Agent Architecture

## Overview

This agent is a CLI tool that connects to an LLM with **tools** to answer questions by reading project documentation. It implements an **agentic loop** that allows the LLM to discover files, read content, and provide answers with source references.

## Architecture

### High-Level Diagram

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Command Line   │────▶│   agent.py   │────▶│  Qwen Code API  │
│  (question)     │     │ (Agentic CLI)│     │  (on VM)        │
└─────────────────┘     └──────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  JSON Output │
                        │  (stdout)    │
                        └──────────────┘
```

### Agentic Loop

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐
│   Question  │────▶│   LLM    │────▶│ tool_calls? │
└─────────────┘     └──────────┘     └──────┬──────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │ yes                   │ no                    │
                    ▼                       ▼                       │
            ┌───────────────┐       ┌───────────────┐               │
            │ Execute tools │       │ Final answer  │               │
            │ Append results│       │ Extract answer│               │
            │ Back to LLM   │       │ + source      │               │
            └───────────────┘       └───────────────┘               │
                    │                                               │
                    └───────────────────────────────────────────────┘
```

**Loop Steps:**

1. Send user question + tool definitions to LLM
2. Parse response:
   - If `tool_calls` present → execute tools, append results to conversation, repeat from step 1
   - If no `tool_calls` → extract answer and source, output JSON
3. Maximum 10 tool calls per question (safety limit)

## Components

### `agent.py`

The main CLI entry point that:

1. **Parses command-line arguments** — expects a single question
2. **Loads LLM configuration** — reads from `.env.agent.secret`
3. **Runs the agentic loop** — calls LLM, executes tools, repeats until final answer
4. **Formats the response** — outputs valid JSON with `answer`, `source`, and `tool_calls`

### Tools

The agent has two tools that the LLM can call:

#### `read_file(path: str)`

Reads a file from the project repository.

**Parameters:**

- `path`: Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns:** File contents as string, or error message

**Security:**

- Rejects paths containing `..` (path traversal)
- Rejects absolute paths
- Only allows paths within project root

#### `list_files(path: str)`

Lists files and directories at a given path.

**Parameters:**

- `path`: Relative directory path from project root (e.g., `wiki`)

**Returns:** Newline-separated listing of entries

**Security:**

- Same path traversal protections as `read_file`

### Tool Schema (for LLM)

Tools are defined as function-calling schemas:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file from the project repository",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string"}
      },
      "required": ["path"]
    }
  }
}
```

### System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to discover relevant wiki files
2. Use `read_file` to read content and find answers
3. Include source references (`wiki/filename.md#section-anchor`)
4. Call one tool at a time and wait for results
5. Stop after finding the answer (max 10 tool calls)

## Environment Configuration (`.env.agent.secret`)

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `my-secret-key` |
| `LLM_API_BASE` | Base URL of the LLM API | `http://10.93.26.104:42005/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

> **Note:** This file is gitignored. Never commit API keys.

## Input/Output

### Input

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Output

```json
{
  "answer": "A merge conflict occurs when two branches modify the same lines...",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "api.md\ngit-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "# Git Workflow\n\n..."
    }
  ]
}
```

**Fields:**

- `answer` (string): The LLM's response
- `source` (string): Wiki file reference (e.g., `wiki/git-workflow.md#section`)
- `tool_calls` (array): All tool calls made during the agentic loop

## API Contract

### LLM Request

```http
POST {LLM_API_BASE}/chat/completions
Authorization: Bearer {LLM_API_KEY}
Content-Type: application/json

{
  "model": "qwen3-coder-plus",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "<question>"}
  ],
  "tools": [...],
  "tool_choice": "auto"
}
```

### LLM Response (with tool calls)

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_abc",
          "function": {
            "name": "read_file",
            "arguments": "{\"path\": \"wiki/git.md\"}"
          }
        }
      ]
    }
  }]
}
```

### LLM Response (final answer)

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "To resolve a merge conflict..."
    }
  }]
}
```

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing env vars | Log to stderr, exit code 1 |
| Network timeout (>60s) | Log to stderr, exit code 1 |
| HTTP error | Log to stderr, exit code 1 |
| Path traversal attempt | Return error message to LLM |
| Max tool calls (10) | Return partial answer with sources found |

## Security

### Path Security

The agent prevents directory traversal attacks:

```python
def validate_path(path: str) -> tuple[bool, str]:
    if ".." in path:
        return False, "Path traversal not allowed"
    if path.startswith("/"):
        return False, "Absolute paths not allowed"
    # Verify resolved path is within project root
    full_path = (PROJECT_ROOT / path).resolve()
    if not str(full_path).startswith(str(PROJECT_ROOT)):
        return False, "Path outside project root"
    return True, ""
```

## Usage

```bash
# Basic usage
uv run agent.py "What is REST?"

# Question requiring file discovery
uv run agent.py "What files are in the wiki?"

# Question requiring file reading
uv run agent.py "How do you resolve a merge conflict?"

# With debug output visible
uv run agent.py "Explain Git workflow" 2>&1
```

## Testing

Run the regression tests:

```bash
pytest tests/test_agent_task2.py -v
```

**Tests verify:**

1. Tool calls are executed (`read_file`, `list_files`)
2. `tool_calls` array is populated in output
3. `source` field references wiki files
4. JSON output is valid

## LLM Provider

**Provider:** Qwen Code API

**Why Qwen Code:**

- 1000 free requests per day
- Works from Russia without VPN
- No credit card required
- OpenAI-compatible API with function calling support

**Deployment:** The Qwen Code API is deployed on the VM at `http://10.93.26.104:42005/v1`.

## Future Extensions (Task 3)

- Add more tools (e.g., `query_api` to query the backend)
- Improved source extraction (section anchors from headings)
- Better conversation management for complex multi-step queries
