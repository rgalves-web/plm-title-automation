"""O write-root do casefile: arquivos só dentro de `<unit>/_casefile/`.

FILES/, SUBMISSION PLM/ e os `_minorh/` existentes são intocáveis — o replay
Webb B armado depende disso. A regra é a mesma dos write-roots do repo
(src/knowledge/write_roots.py): escrever fora do root declarado é exceção
nomeada, não warning. O banco é o outro destino legítimo e passa pelo repo.
"""
from __future__ import annotations

from pathlib import Path

PASTA_CASEFILE = "_casefile"


class EscritaForaDoCaseFile(AssertionError):
    """Uma escrita de arquivo do casefile fora de `<unit>/_casefile/`."""


def caminho(pasta_unit: Path) -> Path:
    got = Path(pasta_unit) / PASTA_CASEFILE
    got.mkdir(parents=True, exist_ok=True)
    return got


def escrever_texto(path: Path, texto: str) -> Path:
    path = Path(path)
    if PASTA_CASEFILE not in path.parts:
        raise EscritaForaDoCaseFile(
            f"o casefile so escreve arquivos sob {PASTA_CASEFILE}/ — "
            f"recusado: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(texto, encoding="utf-8")
    return path
