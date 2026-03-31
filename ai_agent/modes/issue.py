"""
modes/issue.py
==============
Issue mode: /claude on a GitHub issue.

Pipeline: select files → plan changes → write files → open PR.
"""

from pathlib import Path

import anthropic

from config import REPO_FULL_NAME
from models import Changeset
from errors import AgentError
from fs import read_repo_file, read_detailed_docs
from github_api import open_pull_request
from steps import select as select_step
from steps import plan as plan_step
from steps import write as write_step


def run(repo, client: anthropic.Anthropic, repo_root: Path, issue_number: int) -> None:
    issue = repo.get_issue(issue_number)
    handbook = read_repo_file(repo_root, "CLAUDE.md")
    index = read_repo_file(repo_root, "docs/INDEX.md")

    print(f"\nIssue #{issue_number}: {issue.title}")
    issue.create_comment("🤖 **Claude Engineer** is on it. A PR will be opened shortly.")

    if not index:
        issue.create_comment(
            "❌ **Claude Engineer:** `docs/INDEX.md` not found. "
            "Push to `main` to generate docs first."
        )
        return

    issue_text = f"**Title:** {issue.title}\n\n**Body:**\n{issue.body or '(no body)'}"

    try:
        selected = select_step.run(
            client, repo_root, REPO_FULL_NAME,
            handbook, index, issue_text,
        )

        file_docs = read_detailed_docs(repo_root, selected)
        plan = plan_step.run_issue(
            client, REPO_FULL_NAME,
            handbook, issue_number, issue_text, file_docs,
        )

        changeset = Changeset()
        write_step.run(
            client, plan.files, repo_root,
            REPO_FULL_NAME, handbook, issue_text, changeset,
        )

        url = open_pull_request(
            repo, changeset, plan.branch_name,
            plan.pr_title, plan.pr_body, issue_number,
        )
        print(f"  PR opened: {url}")

    except AgentError as e:
        issue.create_comment(f"❌ **Claude Engineer:** {e}")
        raise