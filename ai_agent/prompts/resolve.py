"""
prompts/resolve.py
==================
Pass 1.5 — resolve uncertain files via detailed docs.
Same JSON output format as select.py.
"""


def system(repo_name: str, handbook: str, detailed_docs: str) -> str:
    ctx = f"ENGINEERING HANDBOOK:\n{handbook}\n\n" if handbook else ""
    return (
        f"You are a senior engineer on `{repo_name}`.\n"
        f"{ctx}"
        f"Below are detailed docs for files you were uncertain about.\n"
        f"Select only the ones actually needed for the issue.\n\n"
        f"Respond ONLY with valid JSON (no markdown fences):\n"
        f'{{\n'
        f'  "files": ["path/to/needed_file.py", ...]\n'
        f'}}\n\n'
        f"DETAILED DOCS:\n{detailed_docs}"
    )