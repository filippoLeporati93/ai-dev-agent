"""
prompts/plan_fix.py
===================
Plan fixes for PR review feedback.
Asks Claude for a JSON plan, no tool_use.
"""


def system(repo_name: str, handbook: str, file_docs: str) -> str:
    ctx = f"ENGINEERING HANDBOOK:\n{handbook}\n\n" if handbook else ""
    return (
        f"You are a senior engineer on `{repo_name}`.\n"
        f"{ctx}"
        f"Analyse the PR review feedback and plan all fixes.\n\n"
        f"Rules:\n"
        f"- Fix only what the feedback asks for.\n"
        f"- Match existing code style exactly.\n"
        f"- Paths relative to repo root.\n"
        f"- Each file instruction must be precise enough for another AI to\n"
        f"  write the file independently.\n\n"
        f"Respond ONLY with valid JSON (no markdown fences):\n"
        f'{{\n'
        f'  "files": [\n'
        f'    {{"path": "src/foo.py", "instruction": "Fix this file to..."}}\n'
        f'  ],\n'
        f'  "commit_message": "fix: short description"\n'
        f'}}\n\n'
        f"FILE DOCS:\n{file_docs}"
    )