"""
config.py
=========
Single source of truth for environment, model settings, and constants.
Import this instead of scattering os.environ calls across modules.
"""

import os

# ── GitHub context ────────────────────────────────────────────────────────────
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
GITHUB_WORKSPACE: str = os.environ.get("GITHUB_WORKSPACE", ".")
REPO_FULL_NAME: str = os.environ.get("REPO_FULL_NAME", "")
EVENT_NAME: str = os.environ.get("EVENT_NAME", "issue_comment")
TRIGGER_COMMENT: str = os.environ.get("TRIGGER_COMMENT", "")
REVIEW_BODY: str = os.environ.get("REVIEW_BODY", "")

ISSUE_NUMBER: int | None = (
    int(os.environ["ISSUE_NUMBER"]) if os.environ.get("ISSUE_NUMBER") else None
)
PR_NUMBER: int | None = (
    int(os.environ["PR_NUMBER"]) if os.environ.get("PR_NUMBER") else None
)

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Models ────────────────────────────────────────────────────────────────────
MODEL_ENGINEER: str = "claude-sonnet-4-5"
MODEL_DOCS: str = "claude-haiku-4-5"

# ── Token budgets ─────────────────────────────────────────────────────────────
MAX_TOKENS_PLAN: int = 8_000
MAX_TOKENS_WRITE: int = 16_000

# ── File system ───────────────────────────────────────────────────────────────
MAX_FILE_BYTES: int = 80_000
DOCS_BATCH_SIZE: int = 100

SKIP_DIRS: set[str] = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    ".github", "docs",
}
SKIP_EXTENSIONS: set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".gz",
    ".tar", ".lock", ".min.js", ".min.css", ".map", ".pyc",
}

DOCS_DIR = f"{GITHUB_WORKSPACE} / docs"

# ── Batch polling ─────────────────────────────────────────────────────────────
POLL_INTERVAL_SEC: int = 15
MAX_WAIT_SEC: int = 3600