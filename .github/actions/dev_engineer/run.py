"""
Claude Engineer
===============
Triggered by comments on GitHub issues and PRs.

Issue mode  → comment /claude on an issue
PR fix mode → comment /claude fix on a PR

Pass 1:   CLAUDE.md + docs/INDEX.md + issue  → Claude picks files (confident + uncertain)
Pass 1.5: docs/<uncertain>.md                → Claude resolves uncertain files
Pass 2a:  CLAUDE.md + selected source files  → Claude plans all changes as {path, instruction}
Pass 2b:  one batch request per file in parallel → all files written simultaneously → PR opened

PR fix:   CLAUDE.md + diff + review feedback → same parallel approach → fixup commit
"""

import os
import re
import textwrap
from pathlib import Path

import anthropic
from github import Auth, Github

from ai_agent.fs import read_files, read_repo_file, read_detailed_docs
from ai_agent.batch import batch_loop, batch_submit_and_poll
from ai_agent.github_helpers import (
    clear_staged, stage_files, commit_staged,
    open_pull_request, collect_pr_feedback, checkout_branch,
)

# ── Env ───────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN      = os.environ["GITHUB_TOKEN"]
REPO_FULL_NAME    = os.environ["REPO_FULL_NAME"]
EVENT_NAME        = os.environ.get("EVENT_NAME", "issue_comment")
TRIGGER_COMMENT   = os.environ.get("TRIGGER_COMMENT", "")
REVIEW_BODY       = os.environ.get("REVIEW_BODY", "")
ISSUE_NUMBER      = int(os.environ["ISSUE_NUMBER"]) if os.environ.get("ISSUE_NUMBER") else None
PR_NUMBER         = int(os.environ["PR_NUMBER"])    if os.environ.get("PR_NUMBER")    else None

MODEL      = "claude-sonnet-4-5"
MAX_TOKENS = 16_000  # per-file budget — 16k is enough for any single file


# ── Tool definitions ──────────────────────────────────────────────────────────
TOOL_PLAN = {
    "name": "plan_changes",
    "description": (
        "Produce a precise implementation plan: list every file to create or modify "
        "with exact instructions for what to change in each one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path":         {"type": "string", "description": "Relative path from repo root."},
                        "instructions": {"type": "string", "description": "Exact changes to make — be specific."},
                        "is_new":       {"type": "boolean", "description": "True if this file does not exist yet."},
                    },
                    "required": ["path", "instructions"],
                },
            },
        },
        "required": ["files"],
    },
}

TOOL_SELECT = {
    "name": "select_files",
    "description": (
        "Select files needed to implement the issue. "
        "`files`: paths you are confident about. "
        "`uncertain`: paths whose role is unclear from the index alone."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "files":     {"type": "array", "items": {"type": "string"}},
            "uncertain": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["files"],
    },
}

TOOL_PLAN = {
    "name": "plan_changes",
    "description": (
        "Plan all changes needed to implement the issue. "
        "For each file to create or modify, provide the path and a precise instruction "
        "describing exactly what to write. Also provide the PR metadata. "
        "All files will be written in parallel after this call."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path":        {"type": "string", "description": "Relative path from repo root."},
                        "instruction": {"type": "string", "description": "Precise description of what to write in this file."},
                    },
                    "required": ["path", "instruction"],
                },
            },
            "branch_name": {"type": "string", "description": "e.g. feat/issue-N-slug"},
            "pr_title":    {"type": "string"},
            "pr_body":     {"type": "string", "description": "Must include 'Closes #N'."},
        },
        "required": ["files", "branch_name", "pr_title", "pr_body"],
    },
}

TOOL_PUSH_FIX = {
    "name": "push_fix",
    "description": "Commit all written files to the existing PR branch.",
    "input_schema": {
        "type": "object",
        "properties": {
            "commit_message": {"type": "string"},
        },
        "required": ["commit_message"],
    },
}


# ── Parallel file writing ─────────────────────────────────────────────────────
def write_files_parallel(
    client: anthropic.Anthropic,
    plan: list[dict],
    codebase: str,
    context: str,
    task_description: str,
) -> None:
    """
    Submit one batch request per planned file, all in parallel.
    Each request gets the full codebase + context + its specific instruction.
    Results are staged as they arrive.

    plan: list of {path, instruction} dicts from plan_changes tool.
    """
    print(f"\n  writing {len(plan)} file(s) in parallel…")

    system = textwrap.dedent(f"""
        You are a senior engineer on `{REPO_FULL_NAME}`.
        {context}
        Write the complete content of ONE file as instructed.
        Output ONLY the raw file content — no explanation, no markdown fences.

        CODEBASE (for reference):
        {codebase}
    """).strip()

    requests = [
        {
            "custom_id": f"file-{i}",
            "params": {
                "model":      MODEL,
                "max_tokens": MAX_TOKENS,
                "system":     system,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"{task_description}\n\n"
                        f"Write the complete content of `{item['path']}`.\n\n"
                        f"Instruction: {item['instruction']}"
                    ),
                }],
            },
        }
        for i, item in enumerate(plan)
    ]

    results = batch_submit_and_poll(client, requests)

    for i, item in enumerate(plan):
        cid = f"file-{i}"
        if cid not in results:
            print(f"  warning: no result for {item['path']} — skipping")
            continue
        content = "".join(
            b.text for b in results[cid].content if b.type == "text"
        ).strip()
        # Strip accidental markdown fences
        content = re.sub(r"^```[^\n]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
        stage_files([{"path": item["path"], "content": content}])
        print(f"  written: {item['path']}")


# ── Issue mode ────────────────────────────────────────────────────────────────
def run_issue(repo, client: anthropic.Anthropic, repo_root: Path) -> None:
    issue    = repo.get_issue(ISSUE_NUMBER)
    handbook = read_repo_file(repo_root, "CLAUDE.md")
    index    = read_repo_file(repo_root, "docs/INDEX.md")

    print(f"\nIssue #{ISSUE_NUMBER}: {issue.title}")
    issue.create_comment("🤖 **Claude Engineer** is on it. A PR will be opened shortly.")

    if not index:
        issue.create_comment(
            "❌ **Claude Engineer:** `docs/INDEX.md` not found. "
            "Push to `main` to generate docs first."
        )
        return

    context    = f"ENGINEERING HANDBOOK:\n{handbook}\n\n" if handbook else ""
    issue_text = f"**Title:** {issue.title}\n\n**Body:**\n{issue.body or '(no body)'}"

    # ── Pass 1: select files from INDEX.md ────────────────────────────────────
    print("\nPass 1: selecting files…")

    system1 = textwrap.dedent(f"""
        You are a senior engineer on `{REPO_FULL_NAME}`.
        {context}
        Given the issue and the codebase index, call select_files with:
        - `files`: paths you are confident need to be read or changed
        - `uncertain`: paths whose role is unclear from the index alone

        Include shared utilities, type definitions, and entry-point files.
        Better to include too many than too few.

        CODEBASE INDEX:
        {index}
    """).strip()

    confident: list[str] = []
    uncertain: list[str] = []

    def on_select(name, inp):
        nonlocal confident, uncertain
        if name == "select_files":
            confident[:] = inp.get("files", [])
            uncertain[:] = inp.get("uncertain", [])
            print(f"  confident={len(confident)}  uncertain={len(uncertain)}")
            return f"confident={len(confident)}, uncertain={len(uncertain)}", True
        return "unknown tool", False

    batch_loop(client, system1, issue_text, [TOOL_SELECT], on_select, MODEL, MAX_TOKENS)

    # ── Pass 1.5: resolve uncertain files via detailed docs ───────────────────
    selected = list(confident)
    if uncertain:
        print("\nPass 1.5: resolving uncertain files…")
        detailed = read_detailed_docs(repo_root, uncertain)

        system15 = textwrap.dedent(f"""
            You are a senior engineer on `{REPO_FULL_NAME}`.
            {context}
            Below are detailed docs for files you were uncertain about.
            Call select_files with only the ones actually needed for the issue.

            DETAILED DOCS:
            {detailed}
        """).strip()

        resolved: list[str] = []

        def on_resolve(name, inp):
            resolved[:] = inp.get("files", [])
            print(f"  resolved {len(resolved)} from uncertain list")
            return f"resolved={len(resolved)}", True

        batch_loop(client, system15, issue_text, [TOOL_SELECT], on_resolve, MODEL, MAX_TOKENS)
        selected += resolved

    if not selected:
        issue.create_comment("❌ **Claude Engineer:** could not determine which files to change.")
        return

    # ── Pass 2a: plan all changes ─────────────────────────────────────────────
    print(f"\nPass 2a: planning changes ({len(selected)} files)…")
    codebase = read_files(repo_root, selected)

    system2a = textwrap.dedent(f"""
        You are a senior engineer on `{REPO_FULL_NAME}`.
        {context}
        Analyse the issue and the provided files, then call plan_changes with:
        - every file that needs to be created or modified
        - a precise instruction per file describing exactly what to write
        - the branch name, PR title, and PR body

        Rules:
        - Match existing code style exactly.
        - Only change what the issue requires.
        - PR body must include "Closes #{ISSUE_NUMBER}".
        - Branch: lowercase hyphens e.g. feat/issue-{ISSUE_NUMBER}-slug.
        - Paths relative to repo root.

        FILES:
        {codebase}
    """).strip()

    plan: list[dict] = []
    pr_meta: dict    = {}

    def on_plan(name, inp):
        nonlocal plan, pr_meta
        if name == "plan_changes":
            plan    = inp.get("files", [])
            pr_meta = {
                "branch_name": inp["branch_name"],
                "pr_title":    inp["pr_title"],
                "pr_body":     inp["pr_body"],
            }
            print(f"  planned {len(plan)} file(s):")
            for f in plan:
                print(f"    - {f['path']}")
            return f"Plan accepted: {len(plan)} file(s)", True
        return "unknown tool", False

    batch_loop(client, system2a, issue_text, [TOOL_PLAN], on_plan, MODEL, MAX_TOKENS)

    if not plan:
        issue.create_comment("❌ **Claude Engineer:** planning step produced no files.")
        return

    # ── Pass 2b: write all files in parallel ──────────────────────────────────
    print("\nPass 2b: writing files in parallel…")
    write_files_parallel(client, plan, codebase, context, issue_text)

    # Open PR
    url = open_pull_request(
        repo, pr_meta["branch_name"],
        pr_meta["pr_title"], pr_meta["pr_body"], ISSUE_NUMBER,
    )
    print(f"  PR opened: {url}")


# ── PR fix mode ───────────────────────────────────────────────────────────────
def run_pr_fix(repo, client: anthropic.Anthropic, repo_root: Path) -> None:
    pr       = repo.get_pull(PR_NUMBER)
    branch   = pr.head.ref
    handbook = read_repo_file(repo_root, "CLAUDE.md")

    print(f"\nPR #{PR_NUMBER}: {pr.title} (branch: {branch})")
    pr.create_issue_comment("🤖 **Claude Engineer** reviewing feedback — fix coming shortly.")

    checkout_branch(repo_root, branch)

    context  = f"ENGINEERING HANDBOOK:\n{handbook}\n\n" if handbook else ""
    feedback = collect_pr_feedback(pr)
    touched  = [f.filename for f in pr.get_files()]
    codebase = read_files(repo_root, touched)

    # Plan which files to fix and how
    system_plan = textwrap.dedent(f"""
        You are a senior engineer on `{REPO_FULL_NAME}`.
        {context}
        Analyse the PR review feedback and call plan_changes with:
        - every file that needs to be fixed
        - a precise instruction per file describing exactly what to change
        - a short commit message as branch_name, pr_title left empty, pr_body left empty

        Rules:
        - Fix only what the feedback asks for.
        - Match existing code style exactly.
        - Paths relative to repo root.

        CURRENT FILES:
        {codebase}
    """).strip()

    user = f"**PR:** {pr.title}\n\n{feedback}"

    plan: list[dict] = {}
    commit_msg = f"fix: address review feedback on PR #{PR_NUMBER}"

    def on_plan(name, inp):
        nonlocal plan, commit_msg
        if name == "plan_changes":
            plan       = inp.get("files", [])
            commit_msg = inp.get("branch_name", commit_msg)  # reuse field for commit msg
            print(f"  planned {len(plan)} fix(es):")
            for f in plan:
                print(f"    - {f['path']}")
            return f"Plan accepted: {len(plan)} file(s)", True
        return "unknown tool", False

    batch_loop(client, system_plan, user, [TOOL_PLAN], on_plan, MODEL, MAX_TOKENS)

    if not plan:
        pr.create_issue_comment("❌ **Claude Engineer:** planning step produced no files.")
        return

    # Write all fixes in parallel
    print("\nWriting fixes in parallel…")
    write_files_parallel(client, plan, codebase, context, user)

    commit_staged(repo, branch, commit_msg)
    print(f"  fix pushed to {branch}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    clear_staged()
    gh        = Github(auth=Auth.Token(GITHUB_TOKEN))
    repo      = gh.get_repo(REPO_FULL_NAME)
    repo_root = Path(os.environ.get("GITHUB_WORKSPACE", "."))
    client    = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    trigger   = (TRIGGER_COMMENT or REVIEW_BODY).strip()
    is_pr_fix = PR_NUMBER and (
        "pull_request" in EVENT_NAME or trigger.startswith("/claude fix")
    )

    if is_pr_fix:
        print(f"Mode: PR fix (PR #{PR_NUMBER})")
        run_pr_fix(repo, client, repo_root)
    else:
        print(f"Mode: issue (Issue #{ISSUE_NUMBER})")
        run_issue(repo, client, repo_root)


if __name__ == "__main__":
    main()