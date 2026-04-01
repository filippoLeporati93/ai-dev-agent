"""
prompts/select.py
=================
Pass 1 — select files from the codebase index.
Asks Claude for a JSON response, no tool_use.
"""


def system(repo_name: str, handbook: str, index: str) -> str:
    ctx = f"ENGINEERING HANDBOOK:\n{handbook}\n\n" if handbook else ""
    return (
        f"You are a senior engineer on `{repo_name}`.\n"
        f"{ctx}"
        f"Given the issue and the codebase index, select the files needed.\n\n"
        f"Include shared utilities, type definitions, and entry-point files.\n"
        f"Better to include too many than too few.\n\n"
        f"Respond ONLY with valid JSON (no markdown fences):\n"
        f'{{\n'
        f'  "files": ["path/to/confident_file.py", ...],\n'
        f'  "uncertain": ["path/to/maybe_needed.py", ...]\n'
        f'}}\n\n'
        f"CODEBASE INDEX:\n{index}"
    )

def output_format() -> dict:
    return {
        "type": "json_schema",
        "schema": {
          "type": "object",
          "properties": {
            "files": {"type": "array", "items": {"type": "string"}},
            "uncertain": {"type": "array", "items": {"type": "string"}}
          },
          "additionalProperties": False,
        }
      }
