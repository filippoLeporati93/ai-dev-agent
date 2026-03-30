"""
fs.py
=====
File system constants and helpers.
No Anthropic or GitHub dependencies.
"""

from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".github", "docs",
}
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".gz",
    ".tar", ".lock", ".min.js", ".min.css", ".map", ".pyc",
}
MAX_FILE_BYTES = 80_000


def collect_files(root: Path, skip_dirs: set[str] | None = None) -> list[tuple[str, str]]:
    """
    Return (rel_path, content) for every readable source file under root.
    skip_dirs extends SKIP_DIRS, e.g. pass {"docs"} to exclude /docs.
    """
    skip = SKIP_DIRS | (skip_dirs or set())
    results = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(s in path.parts for s in skip):
            continue
        if path.suffix in SKIP_EXTENSIONS:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        results.append((str(path.relative_to(root)), content))
    return results


def read_files(repo_root: Path, paths: list[str]) -> str:
    """
    Read the given source paths and return them packed into a single string,
    each prefixed with a === path === header. Used to feed files to Claude.
    """
    parts = []
    for rel in paths:
        full = repo_root / rel
        if not full.exists():
            parts.append(f"=== {rel} ===\n(file not found)")
            continue
        try:
            parts.append(f"=== {rel} ===\n{full.read_text(encoding='utf-8', errors='replace')}")
        except Exception as e:
            parts.append(f"=== {rel} ===\n(error reading: {e})")
    return "\n\n".join(parts)


def read_repo_file(repo_root: Path, rel_path: str) -> str:
    """
    Read a single repo file. Returns empty string if missing.
    Logs filename and size for visibility in Actions output.
    """
    path = repo_root / rel_path
    if not path.exists():
        print(f"  warning: {rel_path} not found")
        return ""
    text = path.read_text(encoding="utf-8")
    print(f"  loaded {rel_path} ({len(text):,} chars)")
    return text


def read_detailed_docs(repo_root: Path, paths: list[str]) -> str:
    """Read per-file docs from /docs for the given source paths."""
    parts = []
    for rel in paths:
        doc = repo_root / "docs" / (rel + ".md")
        if doc.exists():
            parts.append(f"=== docs/{rel}.md ===\n{doc.read_text(encoding='utf-8')}")
        else:
            parts.append(f"=== {rel} ===\n(no detailed doc available)")
    return "\n\n".join(parts)