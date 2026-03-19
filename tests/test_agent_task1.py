"""
Regression tests for agent.py (Task 1).

Tests verify that the agent:
1. Runs successfully with exit code 0
2. Outputs valid JSON to stdout
3. Has required fields: answer (string) and tool_calls (array)
"""

import json
import subprocess
import sys


def test_agent_outputs_valid_json():
    """Test that agent.py outputs valid JSON with required fields."""
    question = "What is 2+2?"

    # Run agent.py as a subprocess
    result = subprocess.run(
        ["uv", "run", "agent.py", question],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, (
        f"Agent exited with code {result.returncode}: {result.stderr}"
    )

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"Agent output is not valid JSON: {e}\nOutput: {result.stdout}"
        )

    # Check required fields exist
    assert "answer" in output, "Missing 'answer' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check field types
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must not be empty"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"
    assert len(output["tool_calls"]) == 0, "'tool_calls' must be empty for Task 1"


if __name__ == "__main__":
    test_agent_outputs_valid_json()
    print("All tests passed!")
