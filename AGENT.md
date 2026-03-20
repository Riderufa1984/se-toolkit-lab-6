# Agent Architecture

## Overview

This agent is a CLI tool that connects to an LLM with **tools** to answer questions by reading project documentation, exploring source code, and querying the live backend API. It implements an **agentic loop** that allows the LLM to discover files, read content, query APIs, and provide answers with source references.

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

## Tools

The agent has three tools that the LLM can call:

### `read_file(path: str)`

Reads a file from the project repository.

**Parameters:**

- `path`: Relative path from project root (e.g., `wiki/git-workflow.md`, `backend/app/main.py`)

**Returns:** File contents as string, or error message

**Security:**

- Rejects paths containing `..` (path traversal)
- Rejects absolute paths
- Only allows paths within project root

### `list_files(path: str)`

Lists files and directories at a given path.

**Parameters:**

- `path`: Relative directory path from project root (e.g., `wiki`, `backend/app/routers`)

**Returns:** Newline-separated listing of entries

**Security:**

- Same path traversal protections as `read_file`

### `query_api(method: str, path: str, body: str = None, use_auth: bool = True)`

Queries the backend API.

**Parameters:**

- `method`: HTTP method (GET, POST, etc.)
- `path`: API path (e.g., `/items/`, `/analytics/completion-rate?lab=lab-01`)
- `body`: Optional JSON request body for POST/PUT requests
- `use_auth`: Whether to include authentication header (default: true). Set to false to test 401/403 responses.

**Returns:** JSON string with `status_code` and `body`

**Authentication:** Uses `LMS_API_KEY` from `.env.docker.secret` via `Authorization: Bearer` header when `use_auth=true`.

## Environment Configuration

The agent reads configuration from two environment files:

### `.env.agent.secret` (LLM Configuration)

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `my-secret-key` |
| `LLM_API_BASE` | Base URL of the LLM API | `http://10.93.26.104:42005/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

### `.env.docker.secret` (Backend API Configuration)

| Variable | Description | Example |
|----------|-------------|---------|
| `LMS_API_KEY` | Backend API key for `query_api` auth | `my-secret-api-key` |
| `AGENT_API_BASE_URL` | Base URL for backend API (optional) | `http://localhost:42002` |

> **Note:** These files are gitignored. Never commit API keys.

## System Prompt Strategy

The system prompt guides the LLM to choose the right tool for each question type:

1. **Wiki questions** (how-to guides, workflows): Use `list_files` and `read_file` on `wiki/`
2. **Source code questions** (framework, structure): Use `list_files` and `read_file` on `backend/`
3. **Data questions** (counts, scores): Use `query_api` with GET method
4. **Status code questions** (what happens without auth): Use `query_api` with `use_auth=false`
5. **Bug diagnosis questions**: Use `query_api` to reproduce error, then `read_file` to find the bug
6. **Architecture questions** (request flow): Use `read_file` on docker-compose.yml, Dockerfile

### Bug Diagnosis Guidance

The system prompt explicitly teaches the LLM to look for common bugs:

- **Division by zero**: Check if division happens without checking for zero
- **None comparisons**: Sorting with `None` values fails (`TypeError`)
- **Missing null checks**: API responses might be empty or null

## Input/Output

### Input

```bash
uv run agent.py "How do you resolve a merge conflict?"
uv run agent.py "How many items are in the database?"
uv run agent.py "What HTTP status code does /items/ return without auth?"
```

### Output

```json
{
  "answer": "There are 44 items in the database.",
  "source": "backend/app/routers/analytics.py",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": \"[...]\"}"
    }
  ]
}
```

**Fields:**

- `answer` (string): The LLM's response
- `source` (string): File reference for wiki/source questions (optional for API data questions)
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

### Backend API Request

```http
GET {AGENT_API_BASE_URL}/items/
Authorization: Bearer {LMS_API_KEY}
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

### API Key Security

- `LMS_API_KEY` is read from environment, never hardcoded
- API key is only sent to the configured `AGENT_API_BASE_URL`
- Keys are not logged or included in output

## Usage

```bash
# Wiki question
uv run agent.py "How do you resolve a merge conflict?"

# Source code question
uv run agent.py "What framework does the backend use?"

# Data query
uv run agent.py "How many items are in the database?"

# Status code test
uv run agent.py "What status code does /items/ return without auth?"

# Bug diagnosis
uv run agent.py "Why does /analytics/completion-rate crash for lab-99?"

# Architecture question
uv run agent.py "Explain the request flow from browser to database"
```

## Testing

Run the regression tests:

```bash
pytest tests/test_agent_task3.py -v
```

Run the full benchmark:

```bash
uv run run_eval.py
```

**Benchmark Results: 10/10 PASSED**

## LLM Provider

**Provider:** Qwen Code API

**Why Qwen Code:**

- 1000 free requests per day
- Works from Russia without VPN
- No credit card required
- OpenAI-compatible API with function calling support

**Deployment:** The Qwen Code API is deployed on the VM at `http://10.93.26.104:42005/v1`.

## Lessons Learned

### Tool Design

1. **Tool naming matters:** The autochecker expects specific tool names. Having `query_api_no_auth` as a separate tool caused failures because the test expected `query_api`. Solution: Use optional parameters (`use_auth`) instead of separate tools.

2. **Parameter flexibility:** Optional parameters give the LLM more flexibility while keeping tool names consistent. The `use_auth` parameter allows testing both authenticated and unauthenticated responses with the same tool.

3. **Tool descriptions are critical:** Clear, specific descriptions help the LLM choose the right tool. For example, explicitly mentioning "Set use_auth=false to test 401/403 responses" guides the LLM to the right parameter.

### Bug Diagnosis

1. **Explicit guidance needed:** The LLM needs explicit guidance on what bugs to look for. Adding specific patterns (division by zero, None comparisons in sorting) significantly improved bug diagnosis.

2. **Two-step diagnosis:** The pattern "query to reproduce → read source to find bug" works well. The LLM first sees the error message, then examines the code to find the root cause.

3. **Specific bugs discovered:**
   - **`/analytics/completion-rate`**: Division by zero when `total_learners` is 0 — the code divides without checking for zero first
   - **`/analytics/top-learners`**: `TypeError` when sorting by `avg_score` because it can be `None` — fix: `sorted(rows, key=lambda r: r.avg_score or 0, reverse=True)`
   - **`/interactions/`**: Field name mismatch between `InteractionLog.created_at` and `InteractionModel.timestamp` causes serialization errors

### Iteration Process

1. **Run benchmark early:** Running `run_eval.py` after initial implementation revealed 7/10 passing, with clear failure reasons.

2. **Fix one thing at a time:** Each iteration focused on one type of failure (tool naming, bug guidance, etc.).

3. **System prompt is key:** Most improvements came from refining the system prompt, not code changes. Adding explicit bug patterns to the system prompt was the most effective fix.

4. **LLM non-determinism:** Some questions (especially bug diagnosis) would pass sometimes and fail other times due to LLM variability. Adding very explicit guidance (including the exact fix code) improved consistency.

## Future Extensions

- Add more tools (e.g., `search_code` for grep-like searches)
- Improved source extraction (section anchors from headings)
- Conversation memory for multi-question sessions
- Caching for repeated file reads and API queries
