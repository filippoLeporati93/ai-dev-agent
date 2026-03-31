"""
models.py
=========
Typed data containers passed between pipeline steps.
Each model has a from_json() for parsing Claude's JSON responses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


def parse_json(raw: str) -> dict:
    """Parse JSON from Claude's response, stripping accidental markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\n?|```$", "", raw.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)


@dataclass
class SelectResult:
    """Output of the file selection step."""
    confident: list[str] = field(default_factory=list)
    uncertain: list[str] = field(default_factory=list)

    @property
    def all_files(self) -> list[str]:
        return self.confident + self.uncertain

    @classmethod
    def from_json(cls, raw: str) -> SelectResult:
        data = parse_json(raw)
        return cls(
            confident=data.get("files", []),
            uncertain=data.get("uncertain", []),
        )


@dataclass
class FileInstruction:
    """One file to create or modify, with a precise instruction."""
    path: str
    instruction: str


@dataclass
class Plan:
    """Output of the planning step (issue mode)."""
    files: list[FileInstruction] = field(default_factory=list)
    branch_name: str = ""
    pr_title: str = ""
    pr_body: str = ""

    @classmethod
    def from_json(cls, raw: str) -> Plan:
        data = parse_json(raw)
        return cls(
            files=[
                FileInstruction(path=f["path"], instruction=f["instruction"])
                for f in data.get("files", [])
            ],
            branch_name=data.get("branch_name", ""),
            pr_title=data.get("pr_title", ""),
            pr_body=data.get("pr_body", ""),
        )


@dataclass
class FixPlan:
    """Output of the planning step (PR fix mode)."""
    files: list[FileInstruction] = field(default_factory=list)
    commit_message: str = ""

    @classmethod
    def from_json(cls, raw: str) -> FixPlan:
        data = parse_json(raw)
        return cls(
            files=[
                FileInstruction(path=f["path"], instruction=f["instruction"])
                for f in data.get("files", [])
            ],
            commit_message=data.get("commit_message", ""),
        )


@dataclass
class Changeset:
    """
    Accumulates file changes before committing.
    Explicit state object — no module-level globals.
    """
    _files: dict[str, str] = field(default_factory=dict)

    def stage(self, path: str, content: str) -> None:
        self._files[path] = content

    @property
    def staged_paths(self) -> list[str]:
        return list(self._files.keys())

    @property
    def is_empty(self) -> bool:
        return len(self._files) == 0

    def items(self):
        return self._files.items()

    def clear(self) -> None:
        self._files.clear()

@dataclass
class Doc:
    summary: str
    exports: list[str]
    depends_on: list[str]
    keywords: list[str]

    @classmethod
    def from_json(cls, raw: str) -> FixPlan:
        data = parse_json(raw)
        return cls(
            summary = data.get("summary", ""),
            exports = [e for e in data.get("exports", [])],
            depends_on = [d for d in data.get("depends_on", [])],
            keywords = [k for k in data.get("keywords", [])],
        )