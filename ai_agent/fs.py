"""
fs.py
=====
File system helpers. No external dependencies.
"""

from pathlib import Path

from config import SKIP_DIRS, SKIP_EXTENSIONS, MAX_FILE_BYTES


def collect_files(
    root: Path,
    extra_skip_dirs: set[str] | None = None,
) -> list[tuple[str, str]]:
    """
    Return (rel_path, content) for every readable source file under *root*.
    extra_skip_dirs extends the default SKIP_DIRS.
    """
    skip = SKIP_DIRS | (extra_skip_dirs or set())
    results: list[tuple[str, str]] = []
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
    Read source files and return them packed into a single string,
    each prefixed with a === path === header.
    """
    parts: list[str] = []
    for rel in paths:
        full = repo_root / rel
        if not full.exists():
            parts.append(f"=== {rel} ===\n(file not found)")
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
            parts.append(f"=== {rel} ===\n{text}")
        except Exception as e:
            parts.append(f"=== {rel} ===\n(error reading: {e})")
    return "\n\n".join(parts)


def read_repo_file(repo_root: Path, rel_path: str) -> str:
    """Read a single repo file. Returns empty string if missing."""
    path = repo_root / rel_path
    if not path.exists():
        print(f"  warning: {rel_path} not found")
        return ""
    text = path.read_text(encoding="utf-8")
    print(f"  loaded {rel_path} ({len(text):,} chars)")
    return text


def read_detailed_docs(repo_root: Path, paths: list[str]) -> str:
    """Read per-file docs from /docs for the given source paths."""
    parts: list[str] = []
    for rel in paths:
        doc = repo_root / "docs" / (rel + ".md")
        if doc.exists():
            parts.append(f"=== docs/{rel}.md ===\n{doc.read_text(encoding='utf-8')}")
        else:
            parts.append(f"=== {rel} ===\n(no detailed doc available)")
    return "\n\n".join(parts)


def read_file_content(repo_root: Path, path: str) -> str:
    """Read a single source file, return empty string on any failure."""
    full = repo_root / path
    if not full.exists():
        return ""
    try:
        return full.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""