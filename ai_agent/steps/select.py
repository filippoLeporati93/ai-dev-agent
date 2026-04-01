"""
steps/select.py
===============
Pass 1  — select files from the codebase INDEX.md
Pass 1.5 — resolve uncertain files via detailed docs (if any)

Returns the final list of file paths.
"""

from pathlib import Path

import anthropic

from ai_agent.config import MODEL_ENGINEER, MAX_TOKENS_PLAN
from ai_agent.models import SelectResult, parse_json
from ai_agent.errors import SelectionFailed
from ai_agent.batch import batch_single
from ai_agent.fs import read_detailed_docs
from ai_agent.prompts import select as select_prompt
from ai_agent.prompts import resolve as resolve_prompt


def run(
    client: anthropic.Anthropic,
    repo_root: Path,
    repo_name: str,
    handbook: str,
    index: str,
    issue_text: str,
) -> list[str]:
    """
    Select the files relevant to the issue.
    Raises SelectionFailed if no files are selected.
    """
    # ── Pass 1 ────────────────────────────────────────────────────────────
    print("\nPass 1: selecting files…")
    system = select_prompt.system(repo_name, handbook, index)
    output_format = select_prompt.output_format()
    raw = batch_single(client, system, issue_text, MODEL_ENGINEER, MAX_TOKENS_PLAN, output_format)
    result = SelectResult.from_json(raw)
    print(f"  confident={len(result.confident)}  uncertain={len(result.uncertain)}")

    # ── Pass 1.5 ──────────────────────────────────────────────────────────
    selected = list(result.confident)

    if result.uncertain:
        print("\nPass 1.5: resolving uncertain files…")
        detailed = read_detailed_docs(repo_root, result.uncertain)
        system_15 = resolve_prompt.system(repo_name, handbook, detailed)
        raw_15 = batch_single(client, system_15, issue_text, MODEL_ENGINEER, MAX_TOKENS_PLAN)
        resolved = parse_json(raw_15).get("files", [])
        print(f"  resolved {len(resolved)} from uncertain list")
        selected.extend(resolved)

    if not selected:
        raise SelectionFailed("Could not determine which files to change.")

    return selected
