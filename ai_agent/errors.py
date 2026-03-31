"""
errors.py
=========
Exception hierarchy for the agent pipeline.
Each step raises a specific error so modes can catch and report to GitHub.
"""


class AgentError(Exception):
    """Base for all agent errors."""


class SelectionFailed(AgentError):
    """File selection step returned no files or errored."""


class PlanningFailed(AgentError):
    """Planning step returned no file instructions or errored."""


class WriteFailed(AgentError):
    """One or more file writes failed in the parallel step."""


class BatchError(AgentError):
    """Batch API submission or polling failed."""