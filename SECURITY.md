# Security Policy

slop-eval sends a screenshot or fetched page content to the Anthropic API
and reports back a judged score. It does not execute, evaluate, or
dynamically import anything read from a scan target -- a screenshot is only
ever read as bytes and base64-encoded, and `--url` mode only ever reads a
response body as text. A vulnerability that breaks either of those
invariants, or that exposes the `ANTHROPIC_API_KEY` a caller provides, is
taken seriously and handled as a priority.

## Supported versions

| Package | Version | Supported |
| --- | --- | --- |
| `slop-eval-cli` (npm) | 0.1.x | Yes |
| `slop-eval-cli` (PyPI) | 0.1.x | Yes |

Both distributions are pre-1.0 and under active development. Security
fixes land on the latest `0.1.x` release of each; there is no older
supported line to backport to yet.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security vulnerability.**

Report it privately via
[GitHub Security Advisories](https://github.com/RudrenduPaul/slop-eval/security/advisories/new)
for this repository. Include:

- Which distribution is affected (npm package, PyPI package, or both).
- A minimal reproduction: the command/library call you ran and the input
  (screenshot or URL) that triggers the issue, or a description of its
  shape if it can't be shared directly.
- What you expected slop-eval to do, and what it actually did.
- Your assessment of impact.

## What counts as in scope

- Any code path where content read from a scan target (a screenshot file,
  a fetched URL's response body) is executed, evaluated, or dynamically
  imported, rather than only read, hashed, and sent to the Anthropic API
  or the report writer.
- `ANTHROPIC_API_KEY` handling: the key is read from the
  `ANTHROPIC_API_KEY` environment variable only, is never written to the
  content-hash cache (`.slop-eval-cache/`, `src/cache/judge-cache.ts` /
  `python/src/slop_eval/cache.py` -- only the judge's *response* is
  cached, never the request headers or key), and is never logged or
  included in `--json`/human-readable output. A code path that leaks the
  key into a log line, a cache file, an error message, or a report is a
  vulnerability.
- `--url` mode's fetch: a target URL/response that causes unbounded
  resource consumption (an unbounded hang past the documented fetch
  timeout, unbounded memory from an oversized or lying `Content-Length`)
  bypassing the existing timeout/size-cap protections.
- A crafted screenshot filename or fetched page content that can
  manipulate what a human sees in the default human-readable CLI output
  in a way that misrepresents the actual judge result.

## What is out of scope

- Disagreement with a specific LLM-judge score or evidence string --
  that's a rubric/prompt quality issue (open a normal issue, or better, a
  PR improving the rubric), not a security vulnerability. The judge is
  inherently a heuristic; see the "What a score means (and doesn't)"
  section of either package's README.
- Vulnerabilities in a target URL or the site it belongs to -- report
  those to that site's own maintainers.
- Vulnerabilities in the Anthropic API itself -- report those to
  Anthropic directly.

## Response

We aim to acknowledge a report within 5 business days and to have a fix or
a mitigation plan within 30 days for a confirmed, in-scope vulnerability.
Credit is given in the release notes unless you ask to remain anonymous.
