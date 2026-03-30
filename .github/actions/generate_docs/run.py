"""
generate_docs.py
================
Generates and maintains /docs — the AI documentation layer for Claude Engineer.

STRUCTURE
---------
docs/
  INDEX.md              — one line per file, read in Pass 1
  backend/
    models.py.md
  frontend/
    src/components/
      Navbar.tsx.md

HOW UPDATES WORK
----------------
- First run: all files documented, docs/ created from scratch.
- Subsequent runs: only files changed in the latest commit are re-documented.
  Docs for deleted files are removed. INDEX.md is always rebuilt at the end.
  A one-file commit = one Batch API request.
"""

import json
import os
import re
from collections import defaultdict
from pathlib import Path

import anthropic

from ai_agent.fs import collect_files
from ai_agent.batch import batch_submit_and_poll
from ai_agent.github_helpers import get_changed_files

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL             = "claude-haiku-4-5"

REPO_ROOT  = Path(os.environ.get("GITHUB_WORKSPACE", "."))
DOCS_DIR   = REPO_ROOT / "docs"
BATCH_SIZE = 100

# ── Docs path helper ─────────────────────────────────────────────────────────
def doc_path(rel_source: str) -> Path:
    """docs/backend/models.py.md for source path backend/models.py"""
    return DOCS_DIR / (rel_source + ".md")


# ── Describe files via Batch API ──────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are writing compact AI-readable documentation for a source file.
An AI will read this to decide whether to include the file when implementing a feature.

Respond ONLY with valid JSON (no markdown fences):
{
  "summary": "One precise sentence (max 20 words) — what this file does and its role.",
  "exports": ["PublicFunction", "ClassName", "CONSTANT"],
  "depends_on": ["relative/path/to/other/repo/file.py"],
  "keywords": ["auth", "user", "jwt"]
}

Rules:
- summary: specific enough to distinguish this file from similar ones.
- depends_on: only other files in this repo, not packages.
- keywords: 3-6 terms a developer would search to find this file.
- Omit any key whose value would be an empty list.
"""


def build_requests(files: list[tuple[str, str]], chunk_idx: int) -> list[dict]:
    """One Batch API request per file."""
    return [
        {
            "custom_id": f"f-{chunk_idx}-{i}",
            "params": {
                "model":      MODEL,
                "max_tokens": 256,
                "system":     SYSTEM_PROMPT,
                "messages": [{
                    "role": "user",
                    "content": f"File: {rel}\n\n```\n{content[:60_000]}\n```",
                }],
            },
        }
        for i, (rel, content) in enumerate(files)
    ]


# ── Parse and write per-file doc ──────────────────────────────────────────────
def parse_response(raw: str) -> dict:
    """Parse Claude's JSON, stripping accidental markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\n?|```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r'"summary"\s*:\s*"([^"]+)"', cleaned)
        return {"summary": m.group(1) if m else cleaned[:200]}


def write_doc(rel_source: str, info: dict) -> None:
    """Write docs/<rel_source>.md"""
    out = doc_path(rel_source)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# `{rel_source}`", "", info.get("summary", "—"), ""]
    if info.get("exports"):
        lines += ["**Exports:** " + " · ".join(f"`{e}`" for e in info["exports"]), ""]
    if info.get("depends_on"):
        lines += ["**Depends on:** " + ", ".join(f"`{d}`" for d in info["depends_on"]), ""]
    if info.get("keywords"):
        lines += ["**Keywords:** " + ", ".join(info["keywords"]), ""]
    out.write_text("\n".join(lines), encoding="utf-8")


# ── Rebuild INDEX.md ──────────────────────────────────────────────────────────
def rebuild_index() -> None:
    """
    Rebuild docs/INDEX.md from all per-file docs.
    One line per file: - `source/path.py` — summary
    Grouped by top-level directory.
    """
    entries: list[tuple[str, str]] = []
    for doc in sorted(DOCS_DIR.rglob("*.md")):
        if doc.name == "INDEX.md":
            continue
        source_rel = str(doc.relative_to(DOCS_DIR))[:-3]  # strip .md
        past_h1, summary = False, ""
        for line in doc.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                past_h1 = True
                continue
            if past_h1 and line.strip():
                summary = line.strip()
                break
        entries.append((source_rel, summary))

    groups: dict[str, list] = defaultdict(list)
    for source_rel, summary in entries:
        groups[source_rel.split("/")[0]].append((source_rel, summary))

    lines = [
        "# Codebase Index", "",
        "Auto-generated — do not edit manually.",
        "Read by Claude Engineer in Pass 1 to select relevant files.",
        "",
    ]
    for group in sorted(groups):
        lines += [f"## {group}/", ""]
        for source_rel, summary in groups[group]:
            lines.append(f"- `{source_rel}` — {summary}")
        lines.append("")

    index = DOCS_DIR / "INDEX.md"
    index.write_text("\n".join(lines), encoding="utf-8")
    print(f"  INDEX.md rebuilt ({len(entries)} entries, {index.stat().st_size:,} bytes)")


# ── Main ──────────────────────────────────────────────────────────────────────
def run() -> None:
    client      = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    all_files   = collect_files(REPO_ROOT, skip_dirs={"docs"})
    all_by_path = {rel for rel, _ in all_files}
    is_first    = not (DOCS_DIR / "INDEX.md").exists()

    if is_first:
        print(f"First run — documenting all {len(all_files)} files…")
        to_document = all_files
    else:
        changed     = get_changed_files(REPO_ROOT)
        to_document = [(rel, c) for rel, c in all_files if rel in changed]

        for rel in changed:
            if rel not in all_by_path:
                p = doc_path(rel)
                if p.exists():
                    p.unlink()
                    print(f"  removed doc for deleted file: {rel}")

        print(f"Incremental run — {len(to_document)} changed file(s)")

    if to_document:
        chunks = [to_document[i:i + BATCH_SIZE] for i in range(0, len(to_document), BATCH_SIZE)]
        for idx, chunk in enumerate(chunks):
            print(f"\nBatch {idx + 1}/{len(chunks)}…")
            results = batch_submit_and_poll(client, build_requests(chunk, idx))
            for i, (rel, _) in enumerate(chunk):
                cid = f"f-{idx}-{i}"
                if cid in results:
                    text = "".join(
                        b.text for b in results[cid].content if b.type == "text"
                    )
                    write_doc(rel, parse_response(text))
                    print(f"  documented: {rel}")

    print("\nRebuilding INDEX.md…")
    rebuild_index()


if __name__ == "__main__":
    run()