"""
modes/pr_fix.py
===============
PR fix mode: /claude fix on a pull request.

Pipeline: collect feedback → plan fixes → write files → push fixup commit.
"""

from pathlib import Path

import anthropic

from ai_agent.config import REPO_FULL_NAME
from ai_agent.models import Changeset
from ai_agent.errors import AgentError
from ai_agent.fs import read_repo_file, read_detailed_docs
from ai_agent.github_api import collect_pr_feedback, checkout_branch, commit_changeset
from ai_agent.steps import plan as plan_step
from ai_agent.steps import write as write_step


def run(repo, client: anthropic.Anthropic, repo_root: Path, pr_number: int) -> None:
    pr = repo.get_pull(pr_number)
    branch = pr.head.ref
    handbook = read_repo_file(repo_root, "CLAUDE.md")

    print(f"\nPR #{pr_number}: {pr.title} (branch: {branch})")
    pr.create_issue_comment(
        "🤖 **Claude Engineer** reviewing feedback — fix coming shortly."
    )

    checkout_branch(repo_root, branch)

    feedback = collect_pr_feedback(pr)
    touched_docs = read_detailed_docs(
        repo_root, [f.filename for f in pr.get_files()]
    )
    feedback_text = f"**PR:** {pr.title}\n\n{feedback}"

    try:
        fix_plan = plan_step.run_fix(
            client, REPO_FULL_NAME,
            handbook, pr_number, feedback_text, touched_docs,
        )

        changeset = Changeset()
        write_step.run(
            client, fix_plan.files, repo_root,
            REPO_FULL_NAME, handbook, feedback_text, changeset,
        )

        commit_changeset(repo, changeset, branch, fix_plan.commit_message)
        print(f"  fix pushed to {branch}")

    except AgentError as e:
        pr.create_issue_comment(f"❌ **Claude Engineer:** {e}")
        raise