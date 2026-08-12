"""`knowledge/` → OKF cards. A transcription, not an interpretation.

The old base is eleven YAML files a human wrote and a human maintained. The new
one is written by the model, so it has to be in a format built for that. What
this module does NOT do is decide which of the old knowledge is still true: it
carries every file across, marks where each card came from, and lets the model
read them, contradict them, or overwrite them.

The one structural rule it applies — a mapping of mappings becomes one card per
key, anything else becomes one card per file — is about SHAPE, not meaning. A
file listing fourteen reasons holds fourteen concepts, and a card per concept is
what makes `read_knowledge("captura de tela")` find anything at all.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.examinador.okf import KnowledgeBase

SOURCE = Path("knowledge")

# The old directory names map onto OKF's routing field. Directory → type is a
# fact about where the file sits, not a claim about what it says.
TYPE_BY_DIR = {
    "ontology": "entidade",
    "taxonomy": "regra",
    "rules": "regra",
    "project": "unidade",
    "templates": "layout",
    "fixtures": "regra",
}


def _render(value: Any, depth: int = 0) -> str:
    """YAML, as markdown a model reads comfortably. No content is dropped."""
    pad = "  " * depth
    if isinstance(value, dict):
        out = []
        for key, sub in value.items():
            if isinstance(sub, (dict, list)):
                out.append(f"{pad}- **{key}**:\n{_render(sub, depth + 1)}")
            else:
                out.append(f"{pad}- **{key}**: {sub}")
        return "\n".join(out)
    if isinstance(value, list):
        return "\n".join(f"{pad}- {_render(v, depth + 1).strip()}"
                         if isinstance(v, (dict, list)) else f"{pad}- {v}"
                         for v in value)
    return f"{pad}{value}"


def migrate(source: str | Path = SOURCE, kb: KnowledgeBase | None = None
            ) -> dict[str, Any]:
    kb = kb or KnowledgeBase()
    source = Path(source)
    written: list[str] = []
    for path in sorted(source.rglob("*.yaml")):
        rel = path.relative_to(source)
        kind = TYPE_BY_DIR.get(rel.parts[0], "regra")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        origin = f"knowledge/{rel.as_posix()}"

        # The name comes from the whole path, not the file stem: two folders
        # both holding a `fixture.yaml` are two concepts, and naming them after
        # the stem silently collapses one onto the other.
        stem = "/".join(rel.with_suffix("").parts[1:]) or path.stem
        blocks = _blocks(data, stem)
        for concept, body in blocks:
            kb.write(concept, body, type=kind, sources=[origin],
                     confidence="herdado da base escrita a mao")
            written.append(concept)
    return {"fichas_escritas": len(written), "conceitos": written}


def _blocks(data: Any, stem: str) -> list[tuple[str, str]]:
    """One card per concept where the file holds several; else one per file."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict) and all(
                    isinstance(v, dict) for v in value.values()) and value:
                return [(f"{stem}: {name}", _render(spec))
                        for name, spec in value.items()]
    return [(stem, _render(data))]


if __name__ == "__main__":                          # pragma: no cover
    import json
    print(json.dumps(migrate(), indent=2, ensure_ascii=False))
