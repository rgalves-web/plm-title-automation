"""Staging → validação → promoção — nenhum byte entra em FILES/ direto.

Condição 6 da aprovação: todo documento coletado nasce em
`_casefile/staging/`, recebe sha256 e procedência, é validado (carimbo pela
família B quando aplicável) e só então é PROMOVIDO ao corpus (`FILES/`), com
round-trip de hash. A promoção é a única escrita permitida fora de
`_casefile/` e passa pela caneta (`caneta.promover_staged`). Custos de portal
entram em `cost_entries` categoria 'coleta', separados dos de IA.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from src.casefile import caneta


def dir_staging(pasta_unit: Path) -> Path:
    got = caneta.caminho(pasta_unit) / "staging"
    got.mkdir(parents=True, exist_ok=True)
    return got


def _sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def stage_bytes(repo: Any, unit: dict[str, Any], pasta_unit: Path,
                item_id: int, nome_alvo: str, dados: bytes,
                provenance: dict[str, Any]) -> tuple[Path, str]:
    destino = dir_staging(pasta_unit) / nome_alvo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(dados)
    sha = _sha256(dados)
    repo.atualizar_collection_item(
        item_id, status="staged", staged_path=str(destino), sha256=sha,
        provenance=dict(provenance, bytes=len(dados)))
    return destino, sha


def marcar_validado(repo: Any, item_id: int, nota: str) -> None:
    repo.atualizar_collection_item(item_id, status="validado", note=nota)


def marcar_falha(repo: Any, item_id: int, nota: str) -> None:
    repo.atualizar_collection_item(item_id, status="falhou", note=nota[:400])


def promover(repo: Any, unit: dict[str, Any], pasta_unit: Path,
             item: dict[str, Any]) -> Path:
    """Staged validado → FILES/, com round-trip de hash e censo atualizado."""
    if item["status"] != "validado":
        raise AssertionError(
            f"item {item['id']} esta {item['status']!r} — so item VALIDADO "
            f"e promovido")
    origem = Path(item["staged_path"])
    destino = pasta_unit / "FILES" / origem.name
    final = caneta.promover_staged(origem, destino,
                                   sha256_esperado=item["sha256"])
    # O conteúdo promovido entra no censo na hora — identidade primeiro.
    sid = repo.registrar_source_file(item["sha256"],
                                     final.stat().st_size)
    repo.registrar_sighting(
        source_file_id=sid, unit_id=unit["id"], container_path=str(final),
        zip_member="", logical_name=f"files/{final.name}".lower(),
        origin="unit_files")
    repo.atualizar_collection_item(item["id"], status="promovido",
                                   promoted_path=str(final))
    return final
