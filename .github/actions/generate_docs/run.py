"""
generate_docs.py
================
Generates and maintains /docs — the AI documentation layer for Claude Engineer.

docs/
  INDEX.md              — one line per file, read in Pass 1
  backend/models.py.md  — detailed doc per file, read in Pass 1.5

First run:  all files documented, docs/ created from scratch.
Subsequent: only changed files re-documented. INDEX.md always rebuilt.
"""

import anthropic

from ai_agent.config import (
    ANTHROPIC_API_KEY
)

from ai_agent.errors import AgentError
from ai_agent.modes import docs as docs_mode

def main() -> None:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        docs_mode.run(client)
    except AgentError as e:
        print(f"\nAgent failed: {e}")

if __name__ == "__main__":
    main()