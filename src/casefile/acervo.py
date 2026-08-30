"""O acervo da unit — índice RECURSIVO read-in-place, com origem classificada.

src/knowledge/corpus_reader.py::CorpusIndex indexa só o nível raiz de FILES/;
uma pasta de unit real tem subárvores em 4 formatos de wrapper diferentes
("1. Landman Submitted", "SUBMISSION PLM/...", etc). Este índice varre a
árvore inteira (zips lidos por dentro, sem extrair) e classifica a ORIGEM de
cada entrada — o que permite deixar a entrega ("gabarito de fato") fora do
acervo da sessão por padrão, sem depender de nome de pasta fixo.

`Acervo` injeta o índice em src/examinador/corpus.py::Corpus e herda de graça
read_page (pdf/ocr/imagem/xlsx janelado), search e o PageCache global.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from src.examinador.cache import PageCache
from src.examinador.corpus import Corpus

# Pastas de estado de automação: nunca são corpus.
ESTADO_DIRS = {"_minorh", "_casefile", "_work", "_page_cache"}

# Entrega/quarentena de fato — origem 'entrega'/'outro', fora do acervo da
# sessão por padrão (invariante 11: o gabarito é quarentenado por identidade
# de origem, não por caminho fixo).
_ENTREGA_RE = re.compile(r"landman submitted|^submission", re.IGNORECASE)
_OUTRO_RE = re.compile(r"^_lixo$|fora do escopo", re.IGNORECASE)

ORIGENS_DA_SESSAO = ("unit_files", "unit_folder", "project_reference")


@dataclass
class Entrada:
    logical: str            # nome que o modelo usa (normalizado)
    container: Path         # arquivo no disco (zip ou solto)
    member: str             # membro dentro do zip; "" = arquivo solto
    origin: str


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", str(texto).replace("\\", "/")).strip().lower()


def _origem(rel: Path) -> str | None:
    """A origem pela posição na árvore; None = fora do corpus (estado)."""
    partes = [p.lower() for p in rel.parts]
    if any(p in ESTADO_DIRS for p in partes):
        return None
    if any(_OUTRO_RE.search(p) for p in partes):
        return "outro"
    if any(_ENTREGA_RE.search(p) for p in partes):
        return "entrega"
    if partes and partes[0] == "files":
        return "unit_files"
    return "unit_folder"


def indexar_unit(pasta: Path) -> list[Entrada]:
    """Toda a árvore da unit, zips enumerados por dentro, origem classificada."""
    out: list[Entrada] = []
    vistos: set[str] = set()
    for caminho in sorted(pasta.rglob("*")):
        if not caminho.is_file():
            continue
        rel = caminho.relative_to(pasta)
        origem = _origem(rel)
        if origem is None:
            continue
        rel_posix = rel.as_posix()
        if caminho.suffix.lower() == ".zip":
            pai = rel.parent.as_posix()
            prefixo = "" if pai == "." else pai + "/"
            try:
                with zipfile.ZipFile(caminho) as zf:
                    membros = [m for m in zf.namelist()
                               if not m.endswith("/")]
            except zipfile.BadZipFile:
                # Zip corrompido é fato do censo, não silêncio: entra como
                # arquivo solto para o hash e a contagem o registrarem.
                out.append(_solto(rel_posix, caminho, origem, vistos))
                continue
            for membro in membros:
                logical = _norm(prefixo + membro)
                if logical in vistos:
                    # Colisão entre zips: o caminho completo do zip
                    # desambigua, deterministicamente.
                    logical = _norm(f"{rel_posix}/{membro}")
                vistos.add(logical)
                out.append(Entrada(logical=logical, container=caminho,
                                   member=membro, origin=origem))
        else:
            out.append(_solto(rel_posix, caminho, origem, vistos))
    return out


def _solto(rel_posix: str, caminho: Path, origem: str,
           vistos: set[str]) -> Entrada:
    logical = _norm(rel_posix)
    if logical in vistos:
        logical = _norm(str(caminho))
    vistos.add(logical)
    return Entrada(logical=logical, container=caminho, member="",
                   origin=origem)


def entradas_de_referencias(referencias: dict[str, Path | None]
                            ) -> list[Entrada]:
    """As referências da raiz do projeto como entradas do acervo, sob o
    prefixo REFERENCIAS/ — lidas no lugar, nunca copiadas."""
    out = []
    for kind, path in sorted(referencias.items()):
        if path is None:
            continue
        out.append(Entrada(logical=_norm(f"REFERENCIAS/{path.name}"),
                           container=path, member="",
                           origin="project_reference"))
    return out


class AcervoIndex:
    """A mesma interface que Corpus espera de CorpusIndex, sobre entradas
    já classificadas (duck-typing: _members, resolve, exists, read_bytes)."""

    def __init__(self, entradas: list[Entrada]) -> None:
        self._members: dict[str, tuple[Path, str]] = {}
        self.entradas = entradas
        for e in entradas:
            self._members.setdefault(e.logical, (e.container, e.member))

    def __len__(self) -> int:
        return len(self._members)

    def resolve(self, logical: str | Path) -> tuple[Path, str] | None:
        return self._members.get(_norm(str(logical)))

    def exists(self, logical: str | Path) -> bool:
        return self.resolve(logical) is not None

    def read_bytes(self, logical: str | Path) -> bytes:
        hit = self.resolve(logical)
        if hit is None:
            raise FileNotFoundError(f"nao esta no acervo: {logical}")
        container, member = hit
        if not member:
            return container.read_bytes()
        with zipfile.ZipFile(container) as zf:
            return zf.read(member)


class Acervo(Corpus):
    """Corpus do examinador sobre o índice recursivo — herda read_page,
    search, list_documents e o cache global de páginas."""

    def __init__(self, index: AcervoIndex,
                 cache: PageCache | None = None) -> None:
        self.index = index
        self.cache = cache or PageCache()
        self._bytes: dict[str, bytes] = {}


def montar_acervo(pasta: Path, referencias: dict[str, Path | None],
                  incluir_entrega: bool = False,
                  cache: PageCache | None = None) -> Acervo:
    """O acervo da SESSÃO: unit + referências, entrega fora por padrão."""
    origens = set(ORIGENS_DA_SESSAO) | ({"entrega"} if incluir_entrega
                                        else set())
    entradas = [e for e in indexar_unit(pasta) if e.origin in origens]
    entradas += entradas_de_referencias(referencias)
    return Acervo(AcervoIndex(entradas), cache=cache)
