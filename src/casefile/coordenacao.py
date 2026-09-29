"""Coordenador (ARQUITETURA_AGENTICA_v1, etapa D) — o encanamento em volta.

O Coordenador é uma função como as outras (ficha `nucleo/coordenador.md`,
roda no worker genérico). Este módulo só:
- monta a ENTRADA dele a partir do Case File (censo, claims, pendências
  abertas, decisões do operador, tarefas existentes, orçamento) — cópia
  determinística, sem resumo nem seleção por relevância;
- semeia a tarefa do Coordenador na unit;
- confere a COBERTURA de um plano contra as pendências de um plano de
  investigação aprovado, pelo campo `pendencias` que o próprio Coordenador
  declara em cada tarefa. O código conta referências; se a tarefa de fato
  atende a pendência que cita, quem julga é o operador.
"""
from __future__ import annotations

from typing import Any

from src.casefile import orquestracao as orq

TRUNCA = 1200


def _corta(texto: Any, n: int = TRUNCA) -> str:
    texto = str(texto or "")
    return texto if len(texto) <= n else texto[:n] + f"… [+{len(texto) - n}]"


def entrada_do_coordenador(repo: Any, unit: dict[str, Any], *,
                           teto: float) -> dict[str, Any]:
    uid = unit["id"]
    gasto = repo.custo_acumulado(uid)
    tarefas = repo.tarefas(uid)
    em_aberto = sum(t["budget_usd"] for t in tarefas
                    if t["status"] in orq.EM_ABERTO)
    plano = repo.plano(uid)
    return {
        "unit": unit["canonical_name"],
        "estado": repo.estado_da_unit(uid),
        "orcamento_usd": {"teto": teto, "gasto": gasto,
                          "comprometido_em_tarefas_abertas": em_aberto,
                          "saldo_para_novas_tarefas":
                              round(teto - gasto - em_aberto, 4)},
        "censo": repo.contagem_censo(uid),
        "claims_ativos_por_tipo": repo.contagens_claims(uid),
        "plano_de_investigacao": (
            {"versao": plano["version"], "status": plano["status"],
             "resumo": plano.get("summary") or {}} if plano else None),
        "pendencias_abertas": [
            {"id": f"pesquisa:{r['id']}", "titulo": r["title"],
             "o_que": _corta(r["what"]), "onde": _corta(r["where_"], 400),
             "metodo": _corta(r["method"], 400)}
            for r in repo.pesquisas(uid, "aberta")],
        "decisoes_do_operador": [
            {"id": f"decisao:{d['id']}", "tipo": d["kind"],
             "pergunta": _corta(d["question"]),
             "resposta": _corta(d.get("answer") or "")}
            for d in repo.decisoes_da_unit(uid)],
        "tarefas_existentes": [
            {"ref": t["ref"], "role": t["role"], "status": t["status"],
             "pendencias": t.get("pendencias", [])} for t in tarefas],
        "escalonamentos_abertos": [
            {"motivo": e["motivo"], "pergunta": _corta(e["pergunta"], 400)}
            for e in repo.escalonamentos(uid, abertos=True)],
    }


def semear_coordenador(repo: Any, unit: dict[str, Any], *, pacote: str,
                       teto: float, orcamento_usd: float,
                       criado_por: str, ref: str = "coordenador-1",
                       raiz: Any = None) -> dict[str, Any]:
    """Cria (sem modelo) a tarefa do Coordenador com a entrada montada."""
    entrada = entrada_do_coordenador(repo, unit, teto=teto)
    plano = {"tarefas": [{
        "ref": ref, "role": "coordenador",
        "title": "Montar o grafo de tarefas da unit",
        "input_json": entrada,
        "acceptance": ("plano_tarefas válido; cada tarefa cita o gate do "
                       "pacote e as pendências que atende; orçamento dentro "
                       "do saldo"),
        "depends_on": [], "budget_usd": orcamento_usd, "priority": 0,
        "gate": "0", "justificativa": "semeadura do Coordenador"}]}
    [tarefa] = orq.planejar(repo, unit["id"], plano, criado_por=criado_por,
                            teto=teto, pacote=pacote, raiz=raiz)
    return tarefa


def alvos_do_plano(repo: Any, unit_id: int, versao: int | None = None
                   ) -> dict[str, list[str]]:
    """Pendências de um plano de investigação (as pesquisas da sessão que o
    propôs): `alvos` são as ainda abertas; `canceladas` ficam de fora."""
    plano = repo.plano(unit_id, versao)
    if plano is None:
        raise ValueError(f"unit {unit_id} sem plano de investigação")
    do_plano = [r for r in repo.pesquisas(unit_id)
                if r.get("session_id") == plano["session_id"]]
    return {"alvos": [f"pesquisa:{r['id']}" for r in do_plano
                      if r["status"] == "aberta"],
            "canceladas": [f"pesquisa:{r['id']}" for r in do_plano
                           if r["status"] == "cancelada"],
            "executadas": [f"pesquisa:{r['id']}" for r in do_plano
                           if r["status"] == "executada"]}


def cobertura(tarefas: list[dict[str, Any]], alvos: dict[str, list[str]],
              pendencias_validas: set[str]) -> dict[str, Any]:
    """Conta referências. `tarefas`: dicts com `ref` e `pendencias`."""
    citadas: dict[str, list[str]] = {}
    for t in tarefas:
        for p in t.get("pendencias") or []:
            citadas.setdefault(p, []).append(t["ref"])
    faltando = [a for a in alvos["alvos"] if a not in citadas]
    return {
        "alvos": len(alvos["alvos"]),
        "cobertos": {a: citadas[a] for a in alvos["alvos"] if a in citadas},
        "faltando": faltando,
        "inexistentes": sorted(p for p in citadas
                               if p not in pendencias_validas),
        "citam_cancelada": sorted(p for p in citadas
                                  if p in alvos["canceladas"]),
        "tarefas_sem_pendencia": [t["ref"] for t in tarefas
                                  if not t.get("pendencias")],
        "completa": not faltando,
    }


def pendencias_validas(repo: Any, unit_id: int) -> set[str]:
    return {f"pesquisa:{r['id']}" for r in repo.pesquisas(unit_id)} | \
        {f"decisao:{d['id']}" for d in repo.decisoes_da_unit(unit_id)}
