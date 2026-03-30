"""
github_helpers.py
=================
GitHub API operations used by claude_engineer.py.

- Staging and committing files
- Branch creation
- PR creation
- PR feedback collection
- Checking out a branch locally
"""

import subprocess
from pathlib import Path

from github import GithubException

# Staged files waiting to be committed (reset per run via clear_staged).
_staged: dict[str, str] = {}


def clear_staged() -> None:
    """Reset staged files. Call at the start of each run."""
    _staged.clear()


def stage_files(files: list[dict]) -> tuple[str, bool]:
    """
    Stage files for a future commit.
    Each entry must have 'path' and 'content'.
    Returns a tool-result tuple (message, is_done=False).
    """
    for f in files:
        _staged[f["path"]] = f["content"]
    names = ", ".join(f["path"] for f in files)
    return f"Staged {len(files)} file(s): {names}", False


def commit_staged(repo, branch: str, message: str) -> None:
    """
    Commit all staged files to the given branch via the GitHub Contents API.
    Creates the file if it doesn't exist yet, updates it otherwise.
    """
    for path, content in _staged.items():
        try:
            existing = repo.get_contents(path, ref=branch)
            repo.update_file(path, message, content, existing.sha, branch=branch)
        except GithubException:
            repo.create_file(path, message, content, branch=branch)
        print(f"    committed: {path}")


def create_branch(repo, branch: str) -> None:
    """
    Create a new branch off the repo's default branch.
    Silently ignores 'already exists' errors so re-runs are safe.
    """
    base_sha = repo.get_branch(repo.default_branch).commit.sha
    try:
        repo.create_git_ref(f"refs/heads/{branch}", base_sha)
    except GithubException as e:
        if "already exists" not in str(e):
            raise


def open_pull_request(repo, branch: str, title: str, body: str, issue_number: int) -> str:
    """
    Commit staged files, create the branch, and open a pull request.
    Returns the PR URL.
    """
    create_branch(repo, branch)
    commit_staged(repo, branch, f"feat: implement #{issue_number}")
    pr = repo.create_pull(
        title=title, body=body,
        head=branch, base=repo.default_branch,
    )
    print(f"  PR opened: {pr.html_url}")
    return pr.html_url


def collect_pr_feedback(pr) -> str:
    """
    Collect the full diff, inline review comments, review summaries, and
    general PR comments into a single markdown string for Claude.
    /claude commands are excluded from feedback.
    """
    sections = []

    # Diff
    diff_lines = [
        f"\n### {f.filename}\n```diff\n{f.patch}\n```"
        for f in pr.get_files() if f.patch
    ]
    if diff_lines:
        sections.append("## Diff\n" + "\n".join(diff_lines))

    # Inline review comments (attached to specific lines)
    inline = [
        f"**{c.path} line {c.original_line}:**\n> {c.diff_hunk}\n\n{c.body}"
        for c in pr.get_review_comments()
    ]
    if inline:
        sections.append("## Inline comments\n\n" + "\n\n---\n\n".join(inline))

    # Review summaries
    summaries = [
        f"**Review ({r.state}):** {r.body}"
        for r in pr.get_reviews() if r.body
    ]
    if summaries:
        sections.append("## Review summaries\n\n" + "\n\n".join(summaries))

    # General PR comments (excluding /claude triggers)
    comments = [
        f"**{c.user.login}:** {c.body}"
        for c in pr.as_issue().get_comments()
        if c.body and not c.body.startswith("/claude")
    ]
    if comments:
        sections.append("## Comments\n\n" + "\n\n".join(comments))

    return "\n\n".join(sections) or "(no feedback found)"


def checkout_branch(repo_root: Path, branch: str) -> None:
    """Fetch and checkout a remote branch locally."""
    subprocess.run(["git", "fetch", "origin", branch], cwd=repo_root, check=True)
    subprocess.run(["git", "checkout", branch],        cwd=repo_root, check=True)

def get_changed_files(root: Path) -> set[str]:
    """
    Return the set of files changed in the latest commit using git diff.
    Returns an empty set on the first commit (no HEAD~1 exists), which
    signals the caller to treat all files as changed.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        )
        return {l.strip() for l in result.stdout.splitlines() if l.strip()}
    except subprocess.CalledProcessError:
        return set()