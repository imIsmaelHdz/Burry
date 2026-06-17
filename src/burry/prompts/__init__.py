"""Prompt registry — every agent prompt lives as a Markdown file in this folder.

Why .md files instead of inline strings:
  - prompts are versioned, diffed, and reviewed like any other artifact
  - non-engineers can tune wording without touching Python
  - each prompt carries its own config via YAML-style frontmatter

File format (frontmatter is optional):

    ---
    role: technical
    temperature: 0.2
    ---
    You are a technical analyst...

Usage:
    from .prompts import load_prompt
    p = load_prompt("technical_research")
    p.text          # the prompt body
    p.temperature   # 0.2  (from frontmatter, or None)
    p.render(ticker="AAPL")   # body.format(**kwargs)
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str
    meta: dict[str, str]

    @property
    def role(self) -> str:
        return self.meta.get("role", self.name)

    @property
    def temperature(self) -> float | None:
        t = self.meta.get("temperature")
        return float(t) if t is not None else None

    def render(self, **kwargs) -> str:
        """Substitute {placeholders} in the body. No-op when no kwargs given."""
        return self.text.format(**kwargs) if kwargs else self.text


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Split optional `--- ... ---` frontmatter from the body. No yaml dep."""
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            header, body = raw[3:end], raw[end + 4 :]
            meta: dict[str, str] = {}
            for line in header.strip().splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip()
            return meta, body.lstrip("\n")
    return {}, raw


@lru_cache
def load_prompt(name: str) -> Prompt:
    path = _PROMPT_DIR / f"{name}.md"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in _PROMPT_DIR.glob("*.md")))
        raise FileNotFoundError(
            f"No prompt '{name}.md' in {_PROMPT_DIR}. Available: {available}"
        )
    meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
    return Prompt(name=name, text=body.strip(), meta=meta)
