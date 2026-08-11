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

_TOOL_DESCRIPTION = (
    "Runs the slop-eval CLI (the same `slop-eval` command you'd type on a "
    "terminal) as a subprocess and returns its result as structured JSON, "
    "so an agent can score AI-generated UI for genericness (\"slop\") "
    "against a versioned rubric without shelling out or parsing text "
    "output itself. Call this after a UI has been built or changed -- for "
    "example at the end of a codegen/build step, or as a CI-style quality "
    "gate before declaring a UI task done -- to get a layout/visual-"
    "identity/component-novelty judgment from an LLM judge; don't call it "
    "on a UI that hasn't been rendered yet, since it needs either a real "
    "screenshot file or a reachable URL as input. Requires the "
    "ANTHROPIC_API_KEY environment variable to be set in the server's "
    "environment (BYO Anthropic key, no shared/hosted key); every scoring "
    "call makes one real network request to the Anthropic API and is "
    "billed to that key. This tool is otherwise read-only: it never writes "
    "or modifies any file, only reads the screenshot path you give it (or "
    "fetches the URL you give it) and reads a local rubric JSON file. "
    "Repeat calls with byte-identical input (same screenshot, or same URL "
    "content) hit a local content-hash cache and skip the network call, so "
    "the tool is safe to call again on unchanged input. On any failure -- "
    "the subprocess can't start, it times out after 120 seconds, it exits "
    "non-zero (bad flags, missing/unreadable file, missing API key), or it "
    "prints something that isn't valid JSON -- this handler catches it and "
    "returns a JSON dict describing the failure instead of raising, so a "
    "failed call never surfaces as an MCP protocol error.\n\n"
    "`args` is the CLI's argv as a list of strings, in the exact order "
    "you'd type them after `slop-eval`, minus the program name itself. "
    "The only subcommand today is `score`. Real, verified examples:\n"
    '  ["score", "--screenshot", "./preview.png", "--json"] -- score a '
    "local screenshot file (the stronger, layout-aware input; preferred "
    "over --url).\n"
    '  ["score", "--url", "https://example.com", "--json", '
    '"--fail-below", "50"] -- score a live URL (fetched as raw HTML/text, '
    "not a rendered screenshot -- a v0.1 limitation) and additionally ask "
    "the CLI itself to exit 1 if the composite score comes back under 50.\n"
    '  ["score", "--help"] -- print the CLI\'s own help text; pass '
    '"--help" as an argv item on any (sub)command to discover flags this '
    "description doesn't cover, without needing an API key.\n"
    "--url and --screenshot are mutually exclusive; passing both or "
    "neither is a usage error. Always include --json, since without it "
    "the CLI prints a human-readable report instead of parseable "
    "output. On success this tool returns "
    '{"result": {"target", "rubric", "compositeScore" (0-100), '
    '"findings" (list of {"ruleId", "category", "score", "evidence", '
    '"status"}), "summary" (pass/flagged/notScored counts), "disclaimer"}}'
    '; on a non-JSON-parseable CLI exit it returns {"output": ..., '
    '"stderr": ...} instead; on any error path it returns {"error": ...} '
    "with additional context keys where available."
)


mcp = MCPServer("slop-eval")


@mcp.tool(description=_TOOL_DESCRIPTION)
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
