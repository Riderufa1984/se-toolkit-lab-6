# Task 1 Plan: Call an LLM from Code

## Overview

Build a CLI program (`agent.py`) that takes a question as input, sends it to an LLM, and returns a structured JSON response with `answer` and `tool_calls` fields.

## LLM Provider

**Provider:** Qwen Code API (deployed on VM)

**Configuration:**
- `LLM_API_BASE`: `http://10.93.26.104:42005/v1`
- `LLM_MODEL`: `qwen3-coder-plus`
- `LLM_API_KEY`: Read from `.env.agent.secret`

**Why Qwen Code:**
- 1000 free requests per day
- Works from Russia without VPN
- No credit card required
- OpenAI-compatible API (easy integration)

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

## Implementation Steps

### 1. Environment Loading
- Use `python-dotenv` to load `.env.agent.secret`
- Read `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`

### 2. HTTP Client
- Use `httpx` (already in project dependencies) for async HTTP requests
- POST to `{LLM_API_BASE}/chat/completions`
- Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`

### 3. Request Format
```json
{
  "model": "qwen3-coder-plus",
  "messages": [
    {"role": "user", "content": "<question from CLI>"}
  ]
}
```

### 4. Response Parsing
- Extract `choices[0].message.content` as the `answer`
- `tool_calls` will be empty array `[]` for this task

### 5. Output Format
```json
{"answer": "...", "tool_calls": []}
```
- Single line to stdout
- All debug/logging output to stderr

### 6. Error Handling
- Timeout: 60 seconds max for response
- Network errors: log to stderr, exit with code 1
- Missing env vars: log to stderr, exit with code 1

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI entry point
├── AGENT.md              # Documentation
├── .env.agent.secret     # LLM credentials (gitignored)
├── plans/
│   └── task-1.md         # This plan
└── tests/
    └── test_agent.py     # Regression test
```

## Testing Strategy

**Test:** Run `agent.py` with a simple question, verify:
1. Exit code is 0
2. stdout is valid JSON
3. JSON has `answer` field (non-empty string)
4. JSON has `tool_calls` field (empty array)

## Acceptance Criteria Checklist

- [ ] `plans/task-1.md` exists
- [ ] `agent.py` exists in project root
- [ ] `uv run agent.py "..."` outputs valid JSON
- [ ] API key from `.env.agent.secret` (not hardcoded)
- [ ] `AGENT.md` documents the architecture
- [ ] 1 regression test passes
- [ ] Git workflow followed
