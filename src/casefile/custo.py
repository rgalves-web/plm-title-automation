"""O teto duro por unit — recusa limpa ANTES de gastar (espelho de
src/minorh/cli.py::_orcamento, com o acumulado vindo do banco).

Propriedade da caneta, não julgamento: quanto o operador aceita gastar, nunca
o que a resposta deve ser. Ao bater, o comando para, reporta e diz como
autorizar exceção — nunca estoura em silêncio (doc governante §3).
"""
from __future__ import annotations

import os
from typing import Any


def teto_unit() -> float:
    got = os.environ.get("CASEFILE_TETO_UNIT_USD",
                         os.environ.get("MINORH_TETO_UNIT_USD", "25"))
    return float(got)


def orcamento(repo: Any, unit: dict[str, Any], teto_comando: float) -> float:
    """min(teto do comando, teto da unit − acumulado); teto batido = SystemExit."""
    teto = teto_unit()
    gasto = repo.custo_acumulado(unit["id"])
    if gasto < teto:
        return min(teto_comando, round(teto - gasto, 4))
    contagens = repo.contagens_claims(unit["id"])
    raise SystemExit(
        f"TETO DA UNIDADE ATINGIDO: ${gasto} acumulado >= teto de ${teto} "
        f"(CASEFILE_TETO_UNIT_USD).\n"
        f"Claims ativos: {sum(contagens.values())} · pesquisas abertas: "
        f"{repo.contagem_pesquisas(unit['id'])}.\n"
        f"Nada foi gasto nesta execucao. Para autorizar excecao, o operador "
        f"roda: CASEFILE_TETO_UNIT_USD=<novo teto> python -m src.casefile "
        f"<comando>")
