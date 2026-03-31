"""
prompts/write.py
================
System prompt for Pass 2b — parallel file writing.
Each batch request gets this system prompt + file-specific user content.
"""


def system(repo_name: str, handbook: str) -> str:
    ctx = f"ENGINEERING HANDBOOK:\n{handbook}\n\n" if handbook else ""
    return (
        f"You are a senior engineer on `{repo_name}`.\n"
        f"{ctx}"
        f"Write the complete content of ONE file as instructed.\n"
        f"Output ONLY the raw file content — no explanation, no markdown fences."
    )