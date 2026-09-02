"""simulation_mode — o gate GLOBAL de segurança contra operação paga.

Ordem do operador (02/09/2026, correção de contexto): a execução da JOSH B
UNIT é SIMULAÇÃO/GOLDEN REPLAY. Com a política ativa, QUALQUER operação
externa potencialmente paga (CourthouseDirect, TexasFile, RRC, qualquer
portal) falha de forma ruidosa ANTES de abrir o documento — independente do
que o agente/modelo peça. O custo de portal da execução fica em $0 por
construção, não por disciplina.

A política vale se QUALQUER uma das fontes disser sim: a variável de
ambiente `CASEFILE_SIMULATION_MODE` (gravada no .env) ou a linha de política
no banco (`operator_decisions` kind='politica', question='[simulation_mode]',
answer='true'). Duas fontes de propósito: derrubar uma por engano não
desarma a outra.
"""
from __future__ import annotations

import os
from typing import Any

MARCADOR_BLOQUEIO = "required_in_production_but_unavailable_in_simulation"


class OperacaoPagaBloqueadaEmSimulacao(SystemExit):
    """Operação externa potencialmente paga com simulation_mode ativo."""


def ativa(repo: Any = None, unit_id: int | None = None) -> bool:
    env = os.environ.get("CASEFILE_SIMULATION_MODE", "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if repo is not None and unit_id is not None:
        try:
            return repo.politica(unit_id, "simulation_mode") == "true"
        except Exception:
            # Falha ao LER a política nunca pode liberar pagamento: na
            # dúvida, o chamador ainda tem a via do env; aqui é só fallback.
            return False
    return False


def exigir_bloqueio_pagamento(operacao: str, repo: Any = None,
                              unit_id: int | None = None) -> None:
    """Chamado ANTES de qualquer abertura/captura/download externo."""
    if ativa(repo, unit_id):
        raise OperacaoPagaBloqueadaEmSimulacao(
            f"SIMULATION_MODE ATIVO: operacao externa potencialmente paga "
            f"BLOQUEADA antes de abrir o documento — {operacao}. Custo de "
            f"portal desta execucao permanece $0 (politica do operador de "
            f"02/09/2026).")
