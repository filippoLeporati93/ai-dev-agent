"""
github_api.py
=============
GitHub API and git operations.

All state (staged files) lives in a Changeset object passed by the caller.
No module-level mutable state.
"""

import subprocess
from pathlib import Path

from github import GithubException

from ai_agent.models import Changeset

from github import InputGitTreeElement, GithubException


def commit_changeset(repo, changeset: Changeset, branch: str, message: str) -> None:
    """
    Commit all files in the changeset in ONE commit.
    """

    # Get branch reference
    ref = repo.get_git_ref(f"heads/{branch}")
    base_commit = repo.get_git_commit(ref.object.sha)
    base_tree = repo.get_git_tree(base_commit.tree.sha)

    elements = []

    for path, content in changeset.items():
        elements.append(InputGitTreeElement(
            path=path,
            mode="100644",
            type="blob",
            content=content,
        ))

    # Create new tree (this handles both new + updated files)
    tree = repo.create_git_tree(elements, base_tree)

    # Create commit
    new_commit = repo.create_git_commit(
        message,
        tree,
        [base_commit],
    )

    # Move branch pointer
    ref.edit(new_commit.sha)

    print(f"    committed {len(changeset.staged_paths)} files in one commit")


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


def open_pull_request(
    repo,
    changeset: Changeset,
    branch: str,
    title: str,
    body: str,
    issue_number: int,
) -> str:
    """Create branch, commit changeset, open PR. Returns PR URL."""
    create_branch(repo, branch)
    commit_changeset(repo, changeset, branch, f"feat: implement #{issue_number}")
    pr = repo.create_pull(
        title=title,
        body=body,
        head=branch,
        base=repo.default_branch,
    )
    print(f"  PR opened: {pr.html_url}")
    return pr.html_url


def collect_pr_feedback(pr) -> str:
    """
    Collect diff, inline review comments, review summaries, and general
    PR comments into a single markdown string. Excludes /claude triggers.
    """
    sections: list[str] = []

    diff_lines = [
        f"\n### {f.filename}\n```diff\n{f.patch}\n```"
        for f in pr.get_files()
        if f.patch
    ]
    if diff_lines:
        sections.append("## Diff\n" + "\n".join(diff_lines))

    inline = [
        f"**{c.path} line {c.original_line}:**\n> {c.diff_hunk}\n\n{c.body}"
        for c in pr.get_review_comments()
    ]
    if inline:
        sections.append("## Inline comments\n\n" + "\n\n---\n\n".join(inline))

    summaries = [
        f"**Review ({r.state}):** {r.body}"
        for r in pr.get_reviews()
        if r.body
    ]
    if summaries:
        sections.append("## Review summaries\n\n" + "\n\n".join(summaries))

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
    subprocess.run(
        ["git", "fetch", "origin", branch], cwd=repo_root, check=True
    )
    subprocess.run(["git", "checkout", branch], cwd=repo_root, check=True)


def get_changed_files(root: Path) -> set[str]:
    """
    Return files changed in the latest commit via git diff.
    Returns empty set on first commit (no HEAD~1), signalling a full run.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return {l.strip() for l in result.stdout.splitlines() if l.strip()}
    except subprocess.CalledProcessError:
        return set()