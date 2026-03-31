"""
prompts/plan.py
===============
Pass 2a — plan all changes for an issue.
Asks Claude for a JSON plan, no tool_use.
"""


def system(
    repo_name: str,
    handbook: str,
    issue_number: int,
    file_docs: str,
) -> str:
    ctx = f"ENGINEERING HANDBOOK:\n{handbook}\n\n" if handbook else ""
    return (
        f"You are a senior engineer on `{repo_name}`.\n"
        f"{ctx}"
        f"Analyse the issue and the file docs, then plan all changes.\n\n"
        f"Rules:\n"
        f"- Match existing code style exactly.\n"
        f"- Only change what the issue requires.\n"
        f'- PR body must include "Closes #{issue_number}".\n'
        f"- Branch: lowercase hyphens, e.g. feat/issue-{issue_number}-slug.\n"
        f"- Paths relative to repo root.\n"
        f"- Each file instruction must be precise enough for another AI to\n"
        f"  write the file independently without seeing the other files.\n\n"
        f"Respond ONLY with valid JSON (no markdown fences):\n"
        f'{{\n'
        f'  "files": [\n'
        f'    {{"path": "src/foo.py", "instruction": "Create/modify this file to..."}}\n'
        f'  ],\n'
        f'  "branch_name": "feat/issue-{issue_number}-slug",\n'
        f'  "pr_title": "feat: short description",\n'
        f'  "pr_body": "Description...\\n\\nCloses #{issue_number}"\n'
        f'}}\n\n'
        f"FILE DOCS:\n{file_docs}"
    )