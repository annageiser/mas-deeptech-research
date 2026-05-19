"""SKILL.md discovery and loading (agentskills.io format).

Each skill lives at `<skills_dir>/<skill-name>/SKILL.md` with YAML
frontmatter (name, description, version, metadata.hermes.tags) followed by a
markdown body. The format mirrors what Hermes Agent and MASFactory both
consume so the same skill files can in theory be reused across systems.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable

import yaml


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass
class Skill:
    name: str
    description: str
    version: str
    body: str
    tags: list[str]
    path: str

    def to_prompt_block(self) -> str:
        return (
            f"## Skill: {self.name} (v{self.version})\n"
            f"_{self.description}_\n\n"
            f"{self.body.strip()}\n"
        )


class SkillsLoader:
    def __init__(self, skills_dir: str):
        self.skills_dir = skills_dir

    def discover(self) -> list[Skill]:
        if not os.path.isdir(self.skills_dir):
            return []
        skills: list[Skill] = []
        for entry in sorted(os.listdir(self.skills_dir)):
            skill_path = os.path.join(self.skills_dir, entry, "SKILL.md")
            if os.path.isfile(skill_path):
                try:
                    skills.append(self._load_skill(skill_path))
                except Exception:
                    # A malformed skill should not break the whole agent;
                    # the run-time audit folder will record the offender.
                    continue
        return skills

    @staticmethod
    def _load_skill(path: str) -> Skill:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        match = _FRONTMATTER_RE.match(raw)
        if not match:
            raise ValueError(f"missing YAML frontmatter in {path}")
        frontmatter = yaml.safe_load(match.group(1)) or {}
        body = match.group(2)
        meta = frontmatter.get("metadata", {}) or {}
        hermes_meta = meta.get("hermes", {}) or {}
        return Skill(
            name=frontmatter.get("name", os.path.basename(os.path.dirname(path))),
            description=frontmatter.get("description", ""),
            version=str(frontmatter.get("version", "0.0.0")),
            body=body,
            tags=list(hermes_meta.get("tags", []) or []),
            path=path,
        )

    def selected_for(self, requested_names: Iterable[str]) -> list[Skill]:
        requested = set(requested_names)
        return [s for s in self.discover() if s.name in requested]
