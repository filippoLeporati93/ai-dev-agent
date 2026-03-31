"""
steps/write.py
==============
Pass 2b — write all files in parallel via the Batch API.

This is the one step that genuinely needs parallel batch requests
(one per file). The others use batch_single.
"""

import re
from pathlib import Path

import anthropic

from ai_agent.config import MODEL_ENGINEER, MAX_TOKENS_WRITE
from ai_agent.models import FileInstruction, Changeset
from ai_agent.errors import WriteFailed
from ai_agent.batch import batch_submit_and_poll
from ai_agent.fs import read_file_content
from ai_agent.prompts import write as write_prompt


def run(
    client: anthropic.Anthropic,
    file_instructions: list[FileInstruction],
    repo_root: Path,
    repo_name: str,
    handbook: str,
    task_description: str,
    changeset: Changeset,
) -> None:
    """
    Submit one batch request per file, all in parallel.
    Results are staged into the changeset.
    Raises WriteFailed if ALL files fail.
    """
    print(f"\n  writing {len(file_instructions)} file(s) in parallel…")

    system = write_prompt.system(repo_name, handbook)

    requests: list[dict] = []
    for i, fi in enumerate(file_instructions):
        original = read_file_content(repo_root, fi.path)
        original_section = (
            f"CURRENT CONTENT:\n```\n{original}\n```\n\n"
            if original
            else "This is a new file.\n\n"
        )
        requests.append({
            "custom_id": f"file-{i}",
            "params": {
                "model": MODEL_ENGINEER,
                "max_tokens": MAX_TOKENS_WRITE,
                "system": system,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"{task_description}\n\n"
                        f"FILE: {fi.path}\n\n"
                        f"{original_section}"
                        f"INSTRUCTION:\n{fi.instruction}"
                    ),
                }],
            },
        })

    results = batch_submit_and_poll(client, requests)

    written = 0
    for i, fi in enumerate(file_instructions):
        cid = f"file-{i}"
        if cid not in results:
            print(f"  warning: no result for {fi.path} — skipping")
            continue
        content = "".join(
            b.text for b in results[cid].content if b.type == "text"
        ).strip()
        content = re.sub(r"^```[^\n]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
        changeset.stage(fi.path, content)
        print(f"  written: {fi.path}")
        written += 1

    if written == 0:
        raise WriteFailed(f"All {len(file_instructions)} file writes failed.")