
import anthropic

from config import (
    GITHUB_WORKSPACE,
)
import fs
from steps import docs as docs_step

def run(client: anthropic.Anthropic) -> None:
    all_files = fs.collect_files(GITHUB_WORKSPACE, extra_skip_dirs={"docs"})
    all_by_path = {rel for rel, _ in all_files}
    is_first = docs_step.is_first_doc()

    if is_first:
        print(f"First run — documenting all {len(all_files)} files…")
        to_document = all_files
    else:
        changed = docs_step.get_changed_files(GITHUB_WORKSPACE)
        to_document = [(rel, c) for rel, c in all_files if rel in changed]
        for rel in changed:
            if rel not in all_by_path:
                p = docs_step.doc_path(rel)
                if p.exists():
                    p.unlink()
                    print(f"  removed doc for deleted file: {rel}")
        print(f"Incremental run — {len(to_document)} changed file(s)")

    print("\nRebuilding delta docs...")
    if to_document:
        docs_step.rebuild_docs(client,to_document)

    print("\nRebuilding INDEX.md...")
    docs_step.rebuild_index()