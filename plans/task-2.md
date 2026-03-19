# Task 2 Plan: The Documentation Agent

## Overview

Extend the agent from Task 1 with two tools (`read_file`, `list_files`) and an agentic loop. The agent will be able to navigate the project wiki, read files, and answer questions with proper source references.

## Architecture

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

### Loop Steps

1. Send user question + tool definitions to LLM
2. Parse response:
   - If `tool_calls` present → execute tools, append results, repeat from step 1
   - If no `tool_calls` → extract answer and source, output JSON
3. Maximum 10 tool calls per question (safety limit)

## Tool Definitions

### `read_file`

**Purpose:** Read a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root

**Returns:** File contents as string, or error message if file doesn't exist.

**Security:**
- Reject paths containing `..` (path traversal)
- Reject absolute paths
- Only allow paths within project root

**Schema:**
```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file from the project repository",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "Relative path from project root"}
      },
      "required": ["path"]
    }
  }
}
```

### `list_files`

**Purpose:** List files and directories at a given path.

**Parameters:**
- `path` (string, required): Relative directory path from project root

**Returns:** Newline-separated listing of entries.

**Security:**
- Same path traversal protections as `read_file`
- Only list directories within project root

**Schema:**
```json
{
  "type": "function",
  "function": {
    "name": "list_files",
    "description": "List files and directories at a given path",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "Relative directory path from project root"}
      },
      "required": ["path"]
    }
  }
}
```

## System Prompt

The system prompt will instruct the LLM to:

1. Use `list_files` to discover wiki files when needed
2. Use `read_file` to read relevant files and find answers
3. Include source references in the final answer (file path + section anchor)
4. Call tools step-by-step, not all at once
5. Stop after finding the answer (max 10 tool calls)

**Example prompt:**
```
You are a helpful documentation agent. You have access to tools to read files and list directories in the project wiki.

When answering questions:
1. First use list_files to discover relevant wiki files
2. Then use read_file to read the content and find the answer
3. Include the source reference as: wiki/filename.md#section-anchor
4. Only call one tool at a time and wait for results

Available tools:
- read_file(path: str) - Read a file from the project
- list_files(path: str) - List files in a directory
```

## Output Format

```json
{
  "answer": "<string>",
  "source": "<file-path>#<section-anchor>",
  "tool_calls": [
    {
      "tool": "<tool-name>",
      "args": {"path": "..."},
      "result": "<tool output>"
    }
  ]
}
```

## Implementation Steps

### 1. Tool Implementation
- Implement `read_file(path)` function with path security
- Implement `list_files(path)` function with path security

### 2. LLM Tool Calling
- Define tool schemas for the LLM API
- Parse `tool_calls` from LLM response
- Execute tools and capture results

### 3. Agentic Loop
- Loop until LLM returns no tool calls (or max 10 iterations)
- Maintain conversation history with tool results
- Extract final answer and source from LLM response

### 4. Output Formatting
- Build `tool_calls` array with tool name, args, and result
- Extract `source` from LLM response or infer from files read
- Output valid JSON to stdout

## Security Considerations

| Threat | Mitigation |
|--------|------------|
| Path traversal (`../`) | Reject paths containing `..` |
| Absolute paths | Reject paths starting with `/` |
| Symlink attacks | Use `os.path.realpath` to resolve and verify |
| Directory listing abuse | Limit listing to project root |

## Testing Strategy

**Test 1:** Question about merge conflicts
- Input: `"How do you resolve a merge conflict?"`
- Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

**Test 2:** Question about wiki structure
- Input: `"What files are in the wiki?"`
- Expected: `list_files` in tool_calls with `wiki` path

## Acceptance Criteria Checklist

- [ ] `plans/task-2.md` exists
- [ ] `read_file` and `list_files` tools implemented
- [ ] Agentic loop executes tool calls
- [ ] `tool_calls` populated in output
- [ ] `source` field identifies wiki section
- [ ] Path security prevents traversal attacks
- [ ] `AGENT.md` updated with tools documentation
- [ ] 2 regression tests pass
- [ ] Git workflow followed
