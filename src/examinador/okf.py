"""The knowledge base, in Open Knowledge Format — written BY the model.

OKF (Google Cloud, June 2026) is a file format and nothing else: a tree of
markdown files with YAML frontmatter, one card per concept, `index.md` and
`log.md` reserved, cross-links between cards, and a `type` field that routes.
No service, no registry, no required tooling — text files in the repo.

That is exactly why it fits here. The old `knowledge/` was YAML a human wrote
and a human maintained; a base the model writes into needs a format designed for
agents to enrich, and this one was. `write_knowledge` is how the model deposits
what it learned so the next unit consults instead of re-reading.

This module stores and retrieves. It does not judge whether a card is true, does
not merge conflicting cards, does not rank search results.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ROOT = Path("knowledge_okf")
RESERVED = ("index.md", "log.md")

# The routing field. A card's type decides who reads it, not what it means.
TYPES = ("cadeia", "formulario", "layout", "entidade", "veredito", "regra",
         "unidade", "custo")


def slug(concept: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(concept or "").lower()).strip("-")
    return text or "sem-nome"


@dataclass
class Card:
    concept: str
    type: str
    body: str
    sources: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    unit: str = ""
    confidence: str = ""

    def to_markdown(self) -> str:
        front = {"concept": self.concept, "type": self.type,
                 "sources": self.sources, "links": self.links,
                 "unit": self.unit, "confidence": self.confidence}
        head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{head}\n---\n\n{self.body.strip()}\n"

    @classmethod
    def from_markdown(cls, text: str) -> "Card":
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
        if not m:
            return cls(concept="", type="", body=text)
        front = yaml.safe_load(m.group(1)) or {}
        return cls(concept=str(front.get("concept") or ""),
                   type=str(front.get("type") or ""),
                   body=m.group(2).strip(),
                   sources=list(front.get("sources") or []),
                   links=list(front.get("links") or []),
                   unit=str(front.get("unit") or ""),
                   confidence=str(front.get("confidence") or ""))

    def to_dict(self) -> dict[str, Any]:
        return {"conceito": self.concept, "tipo": self.type, "corpo": self.body,
                "fontes": self.sources, "links": self.links,
                "unidade": self.unit, "confianca": self.confidence}


class KnowledgeBase:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.reads = 0
        self.writes = 0

    def _path(self, concept: str) -> Path:
        return self.root / f"{slug(concept)}.md"

    def read(self, concept: str) -> dict[str, Any]:
        """The card, or the nearest names if there is none.

        A miss returns candidates so the model can ask again with a better name
        — it does not return the "closest" card as if it were the answer."""
        self.reads += 1
        path = self._path(concept)
        if path.exists():
            return {"encontrado": True,
                    **Card.from_markdown(path.read_text(encoding="utf-8")).to_dict()}
        needle = slug(concept)
        nearby = [p.stem for p in sorted(self.root.glob("*.md"))
                  if p.name not in RESERVED
                  and (needle in p.stem or p.stem in needle)]
        return {"encontrado": False, "conceito": concept,
                "fichas_parecidas": nearby,
                "todas_as_fichas": [p.stem for p in sorted(self.root.glob("*.md"))
                                    if p.name not in RESERVED][:200]}

    def write(self, concept: str, body: str, *, type: str = "regra",
              sources: list[str] | None = None, links: list[str] | None = None,
              unit: str = "", confidence: str = "") -> dict[str, Any]:
        self.writes += 1
        card = Card(concept=concept, type=type, body=body,
                    sources=list(sources or []), links=list(links or []),
                    unit=unit, confidence=confidence)
        path = self._path(concept)
        existed = path.exists()
        path.write_text(card.to_markdown(), encoding="utf-8")
        self._append_log(f"{'atualizou' if existed else 'criou'} `{path.stem}` "
                         f"({type}){f' — {unit}' if unit else ''}")
        self._rebuild_index()
        return {"gravado": path.stem, "substituiu": existed}

    def _append_log(self, line: str) -> None:
        log = self.root / "log.md"
        if not log.exists():
            log.write_text("# log\n\nUma linha por escrita. Quem escreveu foi o "
                           "modelo; este arquivo e o rastro.\n\n",
                           encoding="utf-8")
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"- {line}\n")

    def _rebuild_index(self) -> None:
        rows = []
        for path in sorted(self.root.glob("*.md")):
            if path.name in RESERVED:
                continue
            card = Card.from_markdown(path.read_text(encoding="utf-8"))
            first = (card.body.strip().splitlines() or [""])[0][:110]
            rows.append(f"- [{card.concept or path.stem}]({path.name}) "
                        f"`{card.type}` — {first}")
        (self.root / "index.md").write_text(
            "# index\n\nUma ficha por conceito. Lida uma vez, consultada "
            "sempre.\n\n" + "\n".join(rows) + "\n", encoding="utf-8")

    def stats(self) -> dict[str, int]:
        return {"leituras": self.reads, "escritas": self.writes,
                "fichas": len([p for p in self.root.glob("*.md")
                               if p.name not in RESERVED])}
