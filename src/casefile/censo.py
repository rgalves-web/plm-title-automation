"""O censo determinístico — identidade por bytes, observações por caminho.

Varre a árvore da unit (índice recursivo do acervo) mais as referências da
raiz do projeto, calcula o sha256 COMPLETO de cada conteúdo e popula
`source_files` (identidade) e `file_sightings` (observação). É encanamento
puro: nenhuma linha decide o que um documento É — isso é da triagem e do
Examinador. O que o censo expõe de graça:

- o mesmo conteúdo em N caminhos (TO copiado em 6 tracts) = 1 source_file;
- o mesmo NOME com bytes diferentes (XREF homônimo da Webb B) = 2 source_files
  — fato nomeado no relatório, nunca resolvido em silêncio;
- zips "NO DOCUMENTS" de ~440 bytes: o tamanho é fato registrado.
"""
from __future__ import annotations

import hashlib
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.casefile.acervo import Entrada, entradas_de_referencias, indexar_unit


def _sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def executar(repo: Any, unit: dict[str, Any], pasta: Path,
             referencias: dict[str, Path | None]) -> dict[str, Any]:
    """Indexa, hasheia e registra tudo; devolve o resumo para o console."""
    entradas = indexar_unit(pasta) + entradas_de_referencias(referencias)
    # Homônimo = mesmo NOME DE ARQUIVO com bytes diferentes (o XREF dentro da
    # Webb B difere do master da raiz) — agrupado pelo basename, porque os
    # logicals carregam o caminho e nunca colidem entre si.
    por_nome: dict[str, set[str]] = {}
    # Agrupado por container: um zip de 98 membros abre uma vez, não 98.
    por_container: dict[Path, list[Entrada]] = {}
    for e in entradas:
        por_container.setdefault(e.container, []).append(e)

    sightings = 0
    for container, grupo in por_container.items():
        mtime = _mtime(container)
        zf = None
        try:
            if any(g.member for g in grupo):
                zf = zipfile.ZipFile(container)
            for e in grupo:
                dados = zf.read(e.member) if e.member else \
                    container.read_bytes()
                sha = _sha256(dados)
                sid = repo.registrar_source_file(sha, len(dados))
                repo.registrar_sighting(
                    source_file_id=sid,
                    unit_id=(None if e.origin == "project_reference"
                             else unit["id"]),
                    container_path=str(container), zip_member=e.member,
                    logical_name=e.logical, origin=e.origin, mtime=mtime)
                base = e.logical.rsplit("/", 1)[-1]
                por_nome.setdefault(base, set()).add(sha)
                sightings += 1
        finally:
            if zf is not None:
                zf.close()

    homonimos = {nome: sorted(shas) for nome, shas in por_nome.items()
                 if len(shas) > 1}
    return {"sightings": sightings,
            "conteudos": len({s for shas in por_nome.values() for s in shas}),
            "por_origem": repo.contagem_censo(unit["id"]),
            "homonimos": homonimos}
