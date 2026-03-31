"""
main.py
=======
Entry point for Claude Engineer.
Parses environment, picks the right mode, runs it.
"""

from pathlib import Path

import anthropic
from github import Auth, Github

from ai_agent.config import (
    ANTHROPIC_API_KEY,
    GITHUB_TOKEN,
    GITHUB_WORKSPACE,
    REPO_FULL_NAME,
    EVENT_NAME,
    TRIGGER_COMMENT,
    REVIEW_BODY,
    ISSUE_NUMBER,
    PR_NUMBER,
)
from ai_agent.errors import AgentError
from ai_agent.modes import issue as issue_mode
from ai_agent.modes import pr_fix as pr_fix_mode


def main() -> None:
    gh = Github(auth=Auth.Token(GITHUB_TOKEN))
    repo = gh.get_repo(REPO_FULL_NAME)
    repo_root = Path(GITHUB_WORKSPACE)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    trigger = (TRIGGER_COMMENT or REVIEW_BODY).strip()
    is_pr_fix = PR_NUMBER and (
        "pull_request" in EVENT_NAME or trigger.startswith("/claude fix")
    )

    try:
        if is_pr_fix:
            print(f"Mode: PR fix (PR #{PR_NUMBER})")
            pr_fix_mode.run(repo, client, repo_root, PR_NUMBER)
        elif ISSUE_NUMBER:
            print(f"Mode: issue (Issue #{ISSUE_NUMBER})")
            issue_mode.run(repo, client, repo_root, ISSUE_NUMBER)
        else:
            print("Error: no ISSUE_NUMBER or PR_NUMBER set.")
    except AgentError as e:
        print(f"\nAgent failed: {e}")

if __name__ == "__main__":
    main()