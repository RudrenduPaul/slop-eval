"""slop-eval MCP server: exposes the slop-eval CLI over stdio as a single
generic `run` tool, so an MCP-compatible agent runtime can invoke the CLI
programmatically instead of shelling out and parsing stdout text itself.

Requires the `mcp` extra (`pip install "slop-eval-cli[mcp]"`). Started via
`slop-eval-mcp` (stdio transport).

Uses `mcp.server.MCPServer`, the official SDK's current high-level server
class (`mcp` 2.0.0+) -- confirmed directly against the installed package
rather than assumed from older docs/examples. `mcp.server.fastmcp.FastMCP`
was removed in the 2.0.0 release.

This is a thin subprocess wrapper, not a second implementation of the CLI's
behavior: `run()` shells out to `python -m slop_eval.cli` with whatever argv
it is given and relays the result back as structured JSON. Every failure
path (subprocess won't start, times out, exits non-zero, prints non-JSON
output) is caught here and turned into a `{"error": ...}` dict -- this tool
handler must never raise.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from mcp.server import MCPServer

_TIMEOUT_SECONDS = 120

_FALLBACK_DESCRIPTION = (
    'Run the slop-eval CLI with the given argv and return its result as '
    'structured JSON. Pass the same arguments you would on the command '
    'line, without the leading "slop-eval", for example: '
    '["score", "--screenshot", "path/to/shot.png", "--json"]. Always '
    'include --json so the CLI\'s own output is machine-parseable.'
)


def _cli_help_text() -> str:
    """Runs `slop-eval --help` (via the current interpreter, so this works
    even if the `slop-eval` console script isn't on PATH) to build a live
    tool description. Falls back to a short static description if that
    subprocess call fails for any reason -- this function must never raise.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "slop_eval.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        help_text = (completed.stdout or completed.stderr or "").strip()
        if help_text:
            return f"{_FALLBACK_DESCRIPTION}\n\nFull CLI help:\n\n{help_text}"
    except (OSError, subprocess.TimeoutExpired):
        pass
    return _FALLBACK_DESCRIPTION


mcp = MCPServer("slop-eval")


@mcp.tool(description=_cli_help_text())
def run(args: list[str]) -> dict[str, Any]:
    """Shell out to the installed slop-eval CLI and return its result.

    :param args: argv to pass to the CLI, e.g.
        ["score", "--screenshot", "shot.png", "--json"]. Does not include
        the program name itself.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "slop_eval.cli", *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except OSError as exc:
        return {"error": f"failed to start the slop-eval CLI: {exc}"}
    except subprocess.TimeoutExpired:
        return {"error": f"slop-eval CLI timed out after {_TIMEOUT_SECONDS}s"}

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""

    if completed.returncode != 0:
        return {
            "error": f"slop-eval exited with code {completed.returncode}",
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    if not stdout.strip():
        return {"result": None, "stderr": stderr}

    try:
        return {"result": json.loads(stdout)}
    except json.JSONDecodeError:
        # Not every subcommand/flag combination emits JSON (only --json
        # mode does) -- relay the raw text instead of failing the call.
        return {"output": stdout, "stderr": stderr}


def main() -> None:
    """Start the MCP server on stdio transport. Entry point for `slop-eval-mcp`."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
