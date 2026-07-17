"""
Error types shared across the scoring pipeline. Ported from the error
classes defined inline in src/sources/LLMJudgeSource.ts -- kept as their own
module here (rather than inline in sources/llm_judge.py) so cli.py can
import them without importing the Anthropic SDK just to catch an error type.
"""
from __future__ import annotations


class MissingApiKeyError(Exception):
    """Raised when ANTHROPIC_API_KEY is not set. Maps to CLI exit code 2."""

    def __init__(self) -> None:
        super().__init__(
            "ANTHROPIC_API_KEY environment variable is not set.\n"
            "slop-eval calls the Anthropic API to run the LLM judge, and is BYO-key "
            "(bring your own key) -- there is no default or shared key baked into this "
            "tool. Set your key and try again:\n\n"
            '  export ANTHROPIC_API_KEY="sk-ant-..."\n\n'
            "Get a key at https://console.anthropic.com/"
        )


class RubricLoadError(Exception):
    """Raised when the requested rubric file is missing or malformed. Maps to CLI exit code 2."""
