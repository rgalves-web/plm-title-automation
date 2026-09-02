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


def promover_staged(origem: Path, destino: Path,
                    sha256_esperado: str) -> Path:
    """A ÚNICA escrita permitida fora de _casefile/: promoção de um staged
    validado para FILES/, com round-trip de hash (condição 6 da aprovação;
    mesma disciplina do md5 round-trip do kit do minorh). Recusa origem fora
    de staging/, destino fora de FILES/, e destino existente com bytes
    diferentes — nunca sobrescreve em silêncio."""
    import hashlib
    origem, destino = Path(origem), Path(destino)
    if PASTA_CASEFILE not in origem.parts or "staging" not in origem.parts:
        raise EscritaForaDoCaseFile(
            f"promocao so parte de {PASTA_CASEFILE}/staging/ — recusado: "
            f"{origem}")
    if destino.parent.name.upper() != "FILES":
        raise EscritaForaDoCaseFile(
            f"promocao so entra em FILES/ — recusado: {destino}")
    dados = origem.read_bytes()
    sha = hashlib.sha256(dados).hexdigest()
    if sha != sha256_esperado:
        raise AssertionError(
            f"staged mudou de bytes: esperado {sha256_esperado[:12]}…, "
            f"lido {sha[:12]}…")
    if destino.exists():
        existente = hashlib.sha256(destino.read_bytes()).hexdigest()
        if existente != sha:
            raise AssertionError(
                f"{destino} ja existe com bytes DIFERENTES "
                f"({existente[:12]}… vs {sha[:12]}…) — nada e sobrescrito")
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(dados)
    relido = hashlib.sha256(destino.read_bytes()).hexdigest()
    if relido != sha:
        raise AssertionError(f"round-trip falhou em {destino}")
    return destino
