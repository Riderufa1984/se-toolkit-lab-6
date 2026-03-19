"""
Regression tests for agent.py (Task 2) - Documentation Agent.

Tests verify that the agent:
1. Uses tools (read_file, list_files) to answer questions
2. Populates tool_calls array with tool name, args, and result
3. Includes source field referencing wiki files
"""

import json
import subprocess
import sys


def test_agent_uses_read_file_for_merge_conflict_question():
    """Test that agent uses read_file tool when asked about merge conflicts."""
    question = "How do you resolve a merge conflict?"

    # Run agent.py as a subprocess
    result = subprocess.run(
        ["uv", "run", "agent.py", question],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {e}\nOutput: {result.stdout}")

    # Check required fields exist
    assert "answer" in output, "Missing 'answer' field in output"
    assert "source" in output, "Missing 'source' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check field types
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must not be empty"
    assert isinstance(output["source"], str), "'source' must be a string"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"

    # Check that read_file was used
    tool_names = [call["tool"] for call in output["tool_calls"]]
    assert "read_file" in tool_names, f"Expected 'read_file' in tool_calls, got: {tool_names}"

    # Check that source references a wiki file
    assert "wiki/" in output["source"] or output["source"].endswith(".md"), \
        f"Source should reference a wiki file, got: {output['source']}"


def test_agent_uses_list_files_for_wiki_structure_question():
    """Test that agent uses list_files tool when asked about wiki structure."""
    question = "What files are in the wiki?"

    # Run agent.py as a subprocess
    result = subprocess.run(
        ["uv", "run", "agent.py", question],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {e}\nOutput: {result.stdout}")

    # Check required fields exist
    assert "answer" in output, "Missing 'answer' field in output"
    assert "source" in output, "Missing 'source' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check field types
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must not be empty"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"

    # Check that list_files was used
    tool_names = [call["tool"] for call in output["tool_calls"]]
    assert "list_files" in tool_names, f"Expected 'list_files' in tool_calls, got: {tool_names}"

    # Check that list_files was called with 'wiki' path
    list_files_calls = [
        call for call in output["tool_calls"]
        if call["tool"] == "list_files"
    ]
    assert len(list_files_calls) > 0, "Expected at least one list_files call"
    
    wiki_path_calls = [
        call for call in list_files_calls
        if call["args"].get("path") == "wiki"
    ]
    assert len(wiki_path_calls) > 0, \
        f"Expected list_files to be called with path='wiki', got args: {[c['args'] for c in list_files_calls]}"


if __name__ == "__main__":
    test_agent_uses_read_file_for_merge_conflict_question()
    print("Test 1 passed: read_file test")
    
    test_agent_uses_list_files_for_wiki_structure_question()
    print("Test 2 passed: list_files test")
    
    print("All tests passed!")
