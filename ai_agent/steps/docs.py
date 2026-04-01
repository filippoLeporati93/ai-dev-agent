from pathlib import Path
from collections import defaultdict
import anthropic

from ai_agent.config import (
    DOCS_DIR,
    MODEL_DOCS,
    DOCS_BATCH_SIZE
)

from ai_agent.batch import batch_submit_and_poll
from ai_agent.prompts import doc_file as file_doc_prompts
from ai_agent.models import Doc

def doc_path(rel_source: str) -> Path:
    """docs/backend/models.py.md for source path backend/models.py"""
    return DOCS_DIR / (rel_source + ".md")

def write_doc(rel_source: str, info: Doc) -> None:
    out = doc_path(rel_source)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# `{rel_source}`", "", info.summary, ""]
    if info.exports:
        lines += [
            "**Exports:** " + " · ".join(f"`{e}`" for e in info.exports),
            "",
        ]
    if info.get("depends_on"):
        lines += [
            "**Depends on:** " + ", ".join(f"`{d}`" for d in info.depends_on),
            "",
        ]
    if info.get("keywords"):
        lines += ["**Keywords:** " + ", ".join(info.keywords), ""]
    out.write_text("\n".join(lines), encoding="utf-8")

def rebuild_docs(client: anthropic.Anthropic, to_document: list[tuple[str,str]]) -> None:
    chunks = [
        to_document[i : i + DOCS_BATCH_SIZE]
        for i in range(0, len(to_document), DOCS_BATCH_SIZE)
    ]
    for idx, chunk in enumerate(chunks):
        print(f"\nBatch {idx + 1}/{len(chunks)}…")
        system = file_doc_prompts.system()
        output_format = file_doc_prompts.output_format()
        requests = [
        {
            "custom_id": f"f-{idx}-{i}",
            "params": {
                "model": MODEL_DOCS,
                "max_tokens": 256,
                "system": system,
                "messages": [
                    {
                        "role": "user",
                        "content": f"File: {rel}\n\n```\n{content[:60_000]}\n```",
                    }
                ],
                "output_config": {
                  "format": output_format
                }
            },
        }
        for i, (rel, content) in enumerate(chunk)
        ]

        results = batch_submit_and_poll(client, requests)
        for i, (rel, _) in enumerate(chunk):
            cid = f"f-{idx}-{i}"
            if cid in results:
                text = "".join(
                    b.text for b in results[cid].content if b.type == "text"
                )
                write_doc(rel, Doc.from_json(text))
                print(f"  documented: {rel}")

def rebuild_index() -> None:
    entries: list[tuple[str, str]] = []
    for doc in sorted(DOCS_DIR.rglob("*.md")):
        if doc.name == "INDEX.md":
            continue
        source_rel = str(doc.relative_to(DOCS_DIR))[:-3]
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
        "# Codebase Index",
        "",
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
    print(
        f"  INDEX.md rebuilt ({len(entries)} entries, {index.stat().st_size:,} bytes)"
    )

def is_first_doc() -> bool:
    return not (DOCS_DIR / "INDEX.md").exists()
