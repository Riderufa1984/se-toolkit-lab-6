"""
Regression tests for agent.py (Task 3) - System Agent.

Tests verify that the agent:
1. Uses query_api tool for data questions
2. Uses read_file tool for source code questions
3. Populates tool_calls array correctly
"""

import json
import subprocess
import sys


def test_agent_uses_read_file_for_framework_question():
    """Test that agent uses read_file when asked about the backend framework."""
    question = "What framework does the backend use?"

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
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check field types
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must not be empty"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"

    # Check that read_file was used
    tool_names = [call["tool"] for call in output["tool_calls"]]
    assert "read_file" in tool_names, f"Expected 'read_file' in tool_calls, got: {tool_names}"

    # Check that answer mentions FastAPI
    answer_lower = output["answer"].lower()
    assert "fastapi" in answer_lower, f"Answer should mention 'FastAPI', got: {output['answer'][:200]}"


def test_agent_uses_query_api_for_item_count_question():
    """Test that agent uses query_api when asked about item count in database."""
    question = "How many items are in the database?"

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
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check field types
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must not be empty"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"

    # Check that query_api was used
    tool_names = [call["tool"] for call in output["tool_calls"]]
    assert "query_api" in tool_names, f"Expected 'query_api' in tool_calls, got: {tool_names}"

    # Check that answer contains a number > 0
    import re
    numbers = re.findall(r"\d+", output["answer"])
    assert len(numbers) > 0, f"Answer should contain a number, got: {output['answer'][:200]}"
    
    # At least one number should be positive (item count)
    positive_numbers = [int(n) for n in numbers if int(n) > 0]
    assert len(positive_numbers) > 0, f"Answer should contain a positive number, got: {output['answer'][:200]}"


if __name__ == "__main__":
    test_agent_uses_read_file_for_framework_question()
    print("Test 1 passed: read_file for framework question")
    
    test_agent_uses_query_api_for_item_count_question()
    print("Test 2 passed: query_api for item count question")
    
    print("All tests passed!")
