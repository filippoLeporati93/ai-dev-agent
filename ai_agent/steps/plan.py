"""
steps/plan.py
=============
Pass 2a — plan all changes.

Issue mode  → returns Plan (with PR metadata)
PR fix mode → returns FixPlan (with commit message)
"""

import anthropic

from ai_agent.config import MODEL_ENGINEER, MAX_TOKENS_PLAN
from ai_agent.models import Plan, FixPlan
from ai_agent.errors import PlanningFailed
from ai_agent.batch import batch_single
from ai_agent.prompts import plan as plan_prompt
from ai_agent.prompts import plan_fix as plan_fix_prompt


def run_issue(
    client: anthropic.Anthropic,
    repo_name: str,
    handbook: str,
    issue_number: int,
    issue_text: str,
    file_docs: str,
) -> Plan:
    """Plan changes for an issue. Raises PlanningFailed if empty."""
    print("\nPass 2a: planning changes…")
    system = plan_prompt.system(repo_name, handbook, issue_number, file_docs)
    raw = batch_single(client, system, issue_text, MODEL_ENGINEER, MAX_TOKENS_PLAN)
    plan = Plan.from_json(raw)

    print(f"  planned {len(plan.files)} file(s):")
    for f in plan.files:
        print(f"    - {f.path}")

    if not plan.files:
        raise PlanningFailed("Planning step produced no files.")
    return plan


def run_fix(
    client: anthropic.Anthropic,
    repo_name: str,
    handbook: str,
    pr_number: int,
    feedback_text: str,
    file_docs: str,
) -> FixPlan:
    """Plan fixes for PR feedback. Raises PlanningFailed if empty."""
    print("\nPlanning fixes…")
    system = plan_fix_prompt.system(repo_name, handbook, file_docs)
    raw = batch_single(client, system, feedback_text, MODEL_ENGINEER, MAX_TOKENS_PLAN)
    fix_plan = FixPlan.from_json(raw)

    if not fix_plan.commit_message:
        fix_plan.commit_message = f"fix: address review feedback on PR #{pr_number}"

    print(f"  planned {len(fix_plan.files)} fix(es):")
    for f in fix_plan.files:
        print(f"    - {f.path}")

    if not fix_plan.files:
        raise PlanningFailed("Planning step produced no files.")
    return fix_plan