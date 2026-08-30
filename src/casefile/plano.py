"""O Unit Investigation Plan — versionado no banco, renderizado em _casefile/.

`propor` grava a versão nova (a proposta anterior vira 'substituido'), escreve
`PLANO_INVESTIGACAO_v<N>.md` e transiciona PLANEJANDO -> AGUARDANDO_RENATO na
primeira proposta da sessão. O console imprime as contagens DECLARADAS pelo
modelo LADO A LADO com as contagens do banco — divergência é exibida para o
operador decidir, nunca julgada aqui.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.casefile import caneta, estados


def propor(*, repo: Any, unit: dict[str, Any], pasta: Path, markdown: str,
           resumo: dict[str, Any], session_id: int, ator: str
           ) -> dict[str, Any]:
    if not str(markdown or "").strip():
        raise ValueError("plano_markdown vazio — um plano sem corpo nao e "
                         "proposta")
    got = repo.propor_plano(unit["id"], markdown, dict(resumo or {}),
                            session_id)
    path = caneta.escrever_texto(
        caneta.caminho(pasta) / f"PLANO_INVESTIGACAO_v{got['version']}.md",
        markdown)
    if repo.estado_da_unit(unit["id"]) == "PLANEJANDO":
        estados.transicionar(repo, unit, "plano_proposto", ator,
                             nota=f"plano v{got['version']}")
    return {"versao": got["version"], "caminho": str(path),
            "nota": "aguarda decisao do operador: `python -m src.casefile "
                    "aprovar` ou `rejeitar --motivo`"}


def contagens_lado_a_lado(repo: Any, unit: dict[str, Any],
                          resumo: dict[str, Any]) -> str:
    """Declarado x banco, uma linha por métrica — divergência exposta."""
    banco = repo.contagens_claims(unit["id"])
    mapa = {"leases": banco.get("lease_in_unit", 0),
            "tracts": banco.get("tract", 0),
            "tos": banco.get("title_opinion", 0),
            "sellers": banco.get("seller_interest", 0),
            "documentos_presentes": banco.get("document_present", 0),
            "documentos_ausentes": banco.get("document_missing", 0),
            "divergencias": banco.get("divergence", 0),
            "pesquisas": repo.contagem_pesquisas(unit["id"])}
    linhas = ["contagens (declarado pelo modelo x registrado no banco):"]
    chaves = sorted(set(mapa) | set(resumo or {}))
    for chave in chaves:
        declarado = (resumo or {}).get(chave, "?")
        registrado = mapa.get(chave, "?")
        marca = "" if str(declarado) == str(registrado) else "  <- DIVERGE"
        linhas.append(f"  {chave}: {declarado} x {registrado}{marca}")
    return "\n".join(linhas)
