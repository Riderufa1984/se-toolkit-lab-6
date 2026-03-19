# Agent Architecture

## Overview

This agent is a CLI tool that connects to an LLM to answer questions. It serves as the foundation for the more advanced agent that will be built in Tasks 2–3 with tools and an agentic loop.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Command Line   │────▶│   agent.py   │────▶│  Qwen Code API  │
│  (question)     │     │  (CLI tool)  │     │  (on VM)        │
└─────────────────┘     └──────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  JSON Output │
                        │  (stdout)    │
                        └──────────────┘
```

## Components

### `agent.py`

The main CLI entry point that:

1. **Parses command-line arguments** — expects a single question as the first argument
2. **Loads LLM configuration** — reads from `.env.agent.secret`
3. **Calls the LLM API** — sends the question via HTTP POST
4. **Formats the response** — outputs valid JSON to stdout

**Input:**
```bash
uv run agent.py "What does REST stand for?"
```

**Output:**
```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

### Environment Configuration (`.env.agent.secret`)

The agent reads the following environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for authentication | `my-secret-key` |
| `LLM_API_BASE` | Base URL of the LLM API | `http://10.93.26.104:42005/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

> **Note:** This file is gitignored. Never commit API keys.

## LLM Provider

**Provider:** Qwen Code API

**Why Qwen Code:**
- 1000 free requests per day
- Works from Russia without VPN
- No credit card required
- OpenAI-compatible API

**Deployment:** The Qwen Code API is deployed on the VM at `http://10.93.26.104:42005/v1`.

## API Contract

### Request

```http
POST {LLM_API_BASE}/chat/completions
Authorization: Bearer {LLM_API_KEY}
Content-Type: application/json

{
  "model": "qwen3-coder-plus",
  "messages": [
    {"role": "user", "content": "<question>"}
  ]
}
```

### Response

```json
{
  "choices": [
    {
      "message": {
        "content": "<answer>"
      }
    }
  ]
}
```

## Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "<string>",
  "tool_calls": []
}
```

- `answer`: The LLM's response to the question
- `tool_calls`: Empty array (will be populated in Task 2)

**Debug output:** All progress and error messages go to stderr, not stdout.

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing env vars | Log to stderr, exit code 1 |
| Network timeout (>60s) | Log to stderr, exit code 1 |
| HTTP error | Log to stderr, exit code 1 |
| Invalid response format | Log to stderr, exit code 1 |

## Usage

```bash
# Basic usage
uv run agent.py "What is 2+2?"

# With debug output visible
uv run agent.py "Explain REST API" 2>&1
```

## Testing

Run the regression test:

```bash
pytest tests/test_agent_task1.py
```

The test verifies:
1. Exit code is 0
2. stdout is valid JSON
3. JSON has `answer` field (non-empty string)
4. JSON has `tool_calls` field (empty array)

## Future Extensions (Tasks 2–3)

- **Task 2:** Add tools (file read/write, API queries)
- **Task 3:** Add agentic loop (plan → act → observe → repeat)
