"""A máquina de estados da unit — nomes do documento CTO, fielmente.

    INDICADA -> PLANEJANDO -> COLETANDO -> EXAMINANDO -> VERIFICANDO
      -> PREENCHENDO -> AUDITANDO -> AGUARDANDO_RENATO -> LIBERADA
    + BLOQUEADA (teto/erro, de qualquer estado, com retorno registrado)

AGUARDANDO_RENATO é o estado genérico de fila de intervenção; no VS1 ele
recebe o plano proposto (`plano_proposto`) e o gate `aprovar_plano` /
`rejeitar_plano`. Validar transição de PROCESSO é encanamento, não julgamento
de title — nenhum evento aqui decide conteúdo (padrão de desenho de
src/flow/unit_state.py, sem reuso de código). Toda transição grava linha em
`unit_state_transitions`; regressão é permitida e registrada, nunca silenciosa.
"""
from __future__ import annotations

from typing import Any

ESTADOS = ("INDICADA", "PLANEJANDO", "COLETANDO",
           "COLETA_SIMULADA_CONCLUIDA", "EXAMINANDO", "VERIFICANDO",
           "PREENCHENDO", "AUDITANDO", "AGUARDANDO_RENATO", "LIBERADA",
           "BLOQUEADA")

# evento -> (estado exigido, estado resultante)
TRANSICOES: dict[str, tuple[str, str]] = {
    "planejar":                ("INDICADA", "PLANEJANDO"),
    "plano_proposto":          ("PLANEJANDO", "AGUARDANDO_RENATO"),
    "aprovar_plano":           ("AGUARDANDO_RENATO", "COLETANDO"),
    "rejeitar_plano":          ("AGUARDANDO_RENATO", "PLANEJANDO"),
    "coleta_concluida":        ("COLETANDO", "EXAMINANDO"),
    # Simulação (política de 02/09): a coleta termina SEM compra e o exame
    # prossegue com as limitações registradas na transição.
    "coleta_simulada_concluida": ("COLETANDO", "COLETA_SIMULADA_CONCLUIDA"),
    "seguir_exame_simulacao":  ("COLETA_SIMULADA_CONCLUIDA", "EXAMINANDO"),
    "exame_concluido":         ("EXAMINANDO", "VERIFICANDO"),
    "verificacao_concluida":   ("VERIFICANDO", "PREENCHENDO"),
    "preenchimento_concluido": ("PREENCHENDO", "AUDITANDO"),
    "auditoria_concluida":     ("AUDITANDO", "AGUARDANDO_RENATO"),
    "liberar":                 ("AGUARDANDO_RENATO", "LIBERADA"),
}


class TransicaoInvalida(ValueError):
    """O evento não vale a partir do estado atual da unit."""


def transicionar(repo: Any, unit: dict[str, Any], evento: str, ator: str,
                 nota: str = "") -> str:
    """Aplica um evento nomeado; devolve o estado resultante."""
    atual = repo.estado_da_unit(unit["id"])
    if evento == "bloquear":
        repo.transicionar(unit["id"], atual, "BLOQUEADA", evento, ator, nota)
        return "BLOQUEADA"
    if evento == "desbloquear":
        if atual != "BLOQUEADA":
            raise TransicaoInvalida(
                f"desbloquear exige BLOQUEADA; a unit esta em {atual}")
        anterior = _estado_antes_do_bloqueio(repo, unit["id"])
        repo.transicionar(unit["id"], atual, anterior, evento, ator, nota)
        return anterior
    if evento not in TRANSICOES:
        raise TransicaoInvalida(
            f"evento desconhecido {evento!r}; eventos: "
            f"{sorted(TRANSICOES) + ['bloquear', 'desbloquear']}")
    exigido, resultante = TRANSICOES[evento]
    if atual != exigido:
        raise TransicaoInvalida(
            f"evento {evento!r} exige estado {exigido}; "
            f"{unit['canonical_name']} esta em {atual}")
    repo.transicionar(unit["id"], atual, resultante, evento, ator, nota)
    return resultante


def _estado_antes_do_bloqueio(repo: Any, unit_id: int) -> str:
    for t in reversed(repo.transicoes(unit_id)):
        if t["to_state"] == "BLOQUEADA":
            return t["from_state"]
    return "INDICADA"
