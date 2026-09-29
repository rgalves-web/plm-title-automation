"""Coordenador (ARQUITETURA_AGENTICA_v1, etapa D) — o encanamento em volta.

O Coordenador é uma função como as outras (ficha `nucleo/coordenador.md`,
roda no worker genérico). Este módulo:

1. monta a ENTRADA dele (contrato em `docs/ARQUITETURA_AGENTICA_ETAPA_D.md`):
   parte vai integral, parte é contagem, e o resto se consulta pela
   ferramenta `ler_case_file` (declarada na ficha), paginada e com
   proveniência. A entrada leva um `manifesto` que diz exatamente o que é
   integral, o que é resumo, o que foi truncado e o que está em quarentena —
   não é "cópia integral" do Case File;
2. confere a PROPOSTA antes de gravá-la: forma do plano (orquestracao) +
   pendências citadas existem e não estão canceladas + toda pesquisa aberta
   do plano de investigação aprovado é citada por pelo menos uma tarefa.
   O código confere IDs e estados; se a tarefa resolve a pesquisa, quem
   julga é o operador;
3. guarda a saída válida como PROPOSTA (plan_proposals). Nenhuma tarefa
   nasce antes de `aprovar_proposta` por um humano; recusa preserva a
   proposta;
4. recusa unit com perfil de projeto (surface/Cibola): o grafo de tarefas
   levaria a coleta/exame/entrega que o perfil ainda bloqueia
   (`project_profile.require_supported`).
"""
from __future__ import annotations

import re
from typing import Any, Callable

from src.casefile import orquestracao as orq
from src.casefile import project_profile

LIMITE_TEXTO_DECISAO = 4000     # caracteres por pergunta/resposta de decisão
LIMITE_TRECHO_CLAIM = 400       # caracteres do trecho de claim na consulta
PAGINA_PADRAO, PAGINA_MAXIMA = 25, 100
ORIGENS_EM_QUARENTENA = frozenset({"entrega", "outro"})   # como acervo.py
_ATOR_HUMANO = re.compile(r"^human:[\w.-]+$")


class PropostaInvalida(ValueError):
    """Aprovação recusada: a proposta não passa mais na checagem mecânica."""


# --- guarda do perfil de projeto ----------------------------------------------

def _unit_por_id(repo: Any, unit_id: int) -> dict[str, Any]:
    unit = next((u for u in repo.listar_units() if u["id"] == unit_id), None)
    if unit is None:
        raise ValueError(f"unit {unit_id} inexistente")
    return unit


def exigir_etapa_suportada(repo: Any, unit: dict[str, Any] | int,
                           comando: str) -> None:
    """A orquestração agêntica não é o planejamento suportado do perfil
    surface; qualquer unit com perfil selecionado é recusada aqui."""
    if isinstance(unit, int):
        unit = _unit_por_id(repo, unit)
    project_profile.require_supported(repo, unit, comando)


# --- entrada ---------------------------------------------------------------------

def _corta(texto: Any, n: int) -> tuple[str, bool]:
    texto = str(texto or "")
    if len(texto) <= n:
        return texto, False
    return texto[:n] + f" […truncado: +{len(texto) - n} caracteres]", True


def plano_aprovado(repo: Any, unit_id: int) -> dict[str, Any] | None:
    ultimo = repo.plano(unit_id)
    if ultimo is None:
        return None
    for v in range(ultimo["version"], 0, -1):
        p = repo.plano(unit_id, v)
        if p is not None and p["status"] == "aprovado":
            return p
    return None


def alvos_do_plano(repo: Any, unit_id: int, versao: int | None = None
                   ) -> dict[str, Any]:
    """Pendências do plano de investigação APROVADO (ou da versão pedida):
    as pesquisas da sessão que o propôs. `alvos` = as ainda abertas."""
    plano = repo.plano(unit_id, versao) if versao is not None \
        else plano_aprovado(repo, unit_id)
    if plano is None:
        raise ValueError(f"sem_plano_aprovado: unit {unit_id}")
    do_plano = [r for r in repo.pesquisas(unit_id)
                if r.get("session_id") == plano["session_id"]]
    por = {st: [f"pesquisa:{r['id']}" for r in do_plano if r["status"] == st]
           for st in ("aberta", "cancelada", "executada")}
    return {"plano_versao": plano["version"], "plano_status": plano["status"],
            "alvos": por["aberta"], "canceladas": por["cancelada"],
            "executadas": por["executada"]}


def entrada_do_coordenador(repo: Any, unit: dict[str, Any], *,
                           teto: float,
                           reserva_coordenador: float = 0.0) -> dict[str, Any]:
    """`reserva_coordenador`: orçamento da tarefa do próprio Coordenador,
    que a checagem do plano conta como comprometido enquanto ele roda."""
    uid = unit["id"]
    gasto = repo.custo_acumulado(uid)
    tarefas = repo.tarefas(uid)
    em_aberto = sum(t["budget_usd"] for t in tarefas
                    if t["status"] in orq.EM_ABERTO)
    plano = plano_aprovado(repo, uid)
    alvos = alvos_do_plano(repo, uid) if plano else None
    truncadas = []
    decisoes = []
    for d in repo.decisoes_da_unit(uid):
        q, tq = _corta(d["question"], LIMITE_TEXTO_DECISAO)
        a, ta = _corta(d.get("answer") or "", LIMITE_TEXTO_DECISAO)
        if tq or ta:
            truncadas.append(f"decisao:{d['id']}")
        decisoes.append({"id": f"decisao:{d['id']}", "tipo": d["kind"],
                         "pergunta": q, "resposta": a})
    return {
        "manifesto": {
            "integral": ["pendencias_abertas (título, o que, onde, método)",
                         "estado de todas as pesquisas do plano aprovado",
                         "decisoes_do_operador (salvo as listadas em "
                         "`truncado`)", "tarefas_existentes",
                         "escalonamentos_abertos", "orcamento_usd"],
            "somente_contagem": ["censo (conteúdos/caminhos por origem)",
                                 "claims ativos por tipo"],
            "truncado": {"limite_caracteres_decisao": LIMITE_TEXTO_DECISAO,
                         "decisoes_truncadas": truncadas},
            "consultar_pela_ferramenta": (
                "ler_case_file(secao=claims|documentos|pesquisas|decisoes|"
                "tarefas, filtro, tipo, offset, limite): claims com "
                "documento/página/trecho; nomes do censo com sha256; textos "
                "integrais de pesquisas e decisões"),
            "quarentena": ("documentos vistos SÓ em origem de entrega ou "
                           "'outro' ficam fora de `documentos` (mesma regra "
                           "do acervo das sessões); "
                           "claims marcados benchmark_contamination seguem "
                           "com a marca"),
            "nao_incluido": ["conteúdo de documentos (não é tarefa do "
                             "Coordenador ler páginas)", "gabaritos"],
        },
        "unit": unit["canonical_name"],
        "estado": repo.estado_da_unit(uid),
        "orcamento_usd": {"teto": teto, "gasto": gasto,
                          "comprometido_em_tarefas_abertas": em_aberto,
                          "reservado_para_esta_tarefa_do_coordenador":
                              reserva_coordenador,
                          "saldo_para_novas_tarefas":
                              round(teto - gasto - em_aberto
                                    - reserva_coordenador, 4)},
        "censo": repo.contagem_censo(uid),
        "claims_ativos_por_tipo": repo.contagens_claims(uid),
        "plano_de_investigacao": (
            {"versao": plano["version"], "status": plano["status"],
             "resumo": plano.get("summary") or {},
             "pesquisas_abertas_a_cobrir": alvos["alvos"],
             "pesquisas_canceladas_nao_citar": alvos["canceladas"],
             "pesquisas_executadas": alvos["executadas"]}
            if plano else None),
        "pendencias_abertas": [
            {"id": f"pesquisa:{r['id']}", "titulo": r["title"],
             "o_que": r["what"], "onde": r["where_"], "metodo": r["method"]}
            for r in repo.pesquisas(uid, "aberta")],
        "decisoes_do_operador": decisoes,
        "tarefas_existentes": [
            {"ref": t["ref"], "role": t["role"], "status": t["status"],
             "pendencias": t.get("pendencias", [])} for t in tarefas],
        "escalonamentos_abertos": [
            {"motivo": e["motivo"], "pergunta": e["pergunta"]}
            for e in repo.escalonamentos(uid, abertos=True)],
    }


# --- consulta controlada: ler_case_file -------------------------------------------

LER_CASE_FILE = {
    "name": "ler_case_file",
    "description": (
        "Consulta paginada e somente leitura ao Case File desta unit. "
        "secao: claims (tipo = claim_type; filtro = trecho da entidade), "
        "documentos (filtro = trecho do nome; fora os só-da-entrega), "
        "pesquisas (texto integral, todos os estados), decisoes (texto "
        "integral), tarefas. Cada item traz seu id de proveniência."),
    "input_schema": {"type": "object", "properties": {
        "secao": {"type": "string", "enum": ["claims", "documentos",
                                             "pesquisas", "decisoes",
                                             "tarefas"]},
        "filtro": {"type": "string"}, "tipo": {"type": "string"},
        "offset": {"type": "integer", "minimum": 0},
        "limite": {"type": "integer", "minimum": 1,
                   "maximum": PAGINA_MAXIMA}},
        "required": ["secao"]},
}


def _pagina(itens: list[Any], offset: int, limite: int) -> dict[str, Any]:
    limite = max(1, min(int(limite or PAGINA_PADRAO), PAGINA_MAXIMA))
    offset = max(0, int(offset or 0))
    fatia = itens[offset:offset + limite]
    fim = offset + len(fatia)
    return {"total": len(itens), "offset": offset, "itens": fatia,
            "proximo_offset": fim if fim < len(itens) else None}


def ler_case_file(repo: Any, unit_id: int) -> Callable[..., dict[str, Any]]:
    def _ler(secao: str, filtro: str = "", tipo: str = "", offset: int = 0,
             limite: int = PAGINA_PADRAO) -> dict[str, Any]:
        f = (filtro or "").casefold()
        if secao == "claims":
            itens = []
            for c in repo.claims_da_unit(unit_id, tipo or None):
                if f and f not in str(c["entity"]).casefold():
                    continue
                trecho, _ = _corta(c["evidence"], LIMITE_TRECHO_CLAIM)
                itens.append({"id": f"claim:{c['id']}",
                              "tipo": c["claim_type"],
                              "entidade": c["entity"], "valor": c["value"],
                              "documento": f"sha256:{c['source_sha256']}",
                              "pagina": c["page"], "trecho": trecho,
                              "confianca": c["confidence"],
                              "materialidade": c["materiality"]})
        elif secao == "documentos":
            # mesma quarentena do acervo das sessões: nome visto SÓ em
            # origem de entrega/outro fica fora
            fora = {n for n, origens in repo.nomes_por_origem(unit_id).items()
                    if origens and origens <= ORIGENS_EM_QUARENTENA}
            itens = [{"nome": n, "sha256": hs}
                     for n, hs in sorted(repo.sha_por_nome(unit_id).items())
                     if n not in fora and (not f or f in n.casefold())]
        elif secao == "pesquisas":
            itens = [{"id": f"pesquisa:{r['id']}", "status": r["status"],
                      "titulo": r["title"], "o_que": r["what"],
                      "onde": r["where_"], "metodo": r["method"]}
                     for r in repo.pesquisas(unit_id)
                     if not f or f in f"{r['title']} {r['what']}".casefold()]
        elif secao == "decisoes":
            itens = [{"id": f"decisao:{d['id']}", "tipo": d["kind"],
                      "pergunta": d["question"],
                      "resposta": d.get("answer") or ""}
                     for d in repo.decisoes_da_unit(unit_id)
                     if not f or f in f"{d['question']} "
                                      f"{d.get('answer') or ''}".casefold()]
        elif secao == "tarefas":
            itens = [{"ref": t["ref"], "role": t["role"],
                      "status": t["status"], "budget_usd": t["budget_usd"],
                      "pendencias": t.get("pendencias", [])}
                     for t in repo.tarefas(unit_id)]
        else:
            raise ValueError(f"secao_desconhecida: {secao!r}")
        return {"secao": secao, **_pagina(itens, offset, limite)}
    return _ler


def ferramentas_do_coordenador(repo: Any, unit_id: int
                               ) -> dict[str, tuple[dict[str, Any], Callable]]:
    return {"ler_case_file": (LER_CASE_FILE, ler_case_file(repo, unit_id))}


# --- proposta: checar, registrar, decidir -------------------------------------

def cobertura(tarefas: list[dict[str, Any]], alvos: dict[str, Any],
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
    """IDs que uma tarefa pode citar: pesquisas não canceladas e decisões."""
    return {f"pesquisa:{r['id']}" for r in repo.pesquisas(unit_id)
            if r["status"] != "cancelada"} | \
        {f"decisao:{d['id']}" for d in repo.decisoes_da_unit(unit_id)}


def checar_proposta(repo: Any, unit_id: int, plano: Any, *, teto: float,
                    pacote: str = "", raiz: Any = None) -> list[str]:
    """Erros mecânicos de uma proposta do Coordenador (vazio = aceitável
    para o operador decidir): forma, referências, orçamento, pendências
    citadas e cobertura do plano de investigação aprovado."""
    erros = orq.checar_plano(repo, unit_id, plano, teto=teto, pacote=pacote,
                             raiz=raiz)
    if erros:
        return erros
    try:
        alvos = alvos_do_plano(repo, unit_id)
    except ValueError as exc:
        return [str(exc)]
    c = cobertura(plano["tarefas"], alvos, pendencias_validas(repo, unit_id))
    if c["citam_cancelada"]:
        erros.append(f"pendencia_cancelada citada: {c['citam_cancelada']}")
    inexistentes = [p for p in c["inexistentes"]
                    if p not in c["citam_cancelada"]]
    if inexistentes:
        erros.append(f"pendencia_inexistente citada: {inexistentes}")
    if c["faltando"]:
        erros.append(f"cobertura_incompleta: {len(c['faltando'])} de "
                     f"{c['alvos']} pesquisas abertas do plano v"
                     f"{alvos['plano_versao']} sem tarefa: {c['faltando']}")
    return erros


def registrar_proposta(repo: Any, task: dict[str, Any], plano: Any, *,
                       run_id: int | None) -> int:
    alvos = alvos_do_plano(repo, task["unit_id"])
    c = cobertura(plano["tarefas"], alvos,
                  pendencias_validas(repo, task["unit_id"]))
    return repo.registrar_proposta(task["unit_id"], task["id"], run_id,
                                   task.get("pack", ""), plano, alvos, c)


def _exigir_humano(ator: str, nota: str) -> None:
    if not _ATOR_HUMANO.match(ator or ""):
        raise orq.DecisaoInvalida(f"ator_invalido: {ator!r} (só human:<id>)")
    if not str(nota or "").strip():
        raise orq.DecisaoInvalida("nota_ausente: decisão sem motivo")


def _coordenador_aguardando(repo: Any, p: dict[str, Any]) -> dict[str, Any]:
    coord = repo.tarefa(p["task_id"])
    if coord is None or coord["status"] != "aguardando_operador":
        raise orq.TransicaoInvalida(
            f"tarefa do Coordenador {p['task_id']} não aguarda o operador "
            f"({coord and coord['status']!r})")
    return coord


def aprovar_proposta(repo: Any, proposal_id: int, *, ator: str, nota: str,
                     teto: float, raiz: Any = None) -> list[dict[str, Any]]:
    """Único caminho da saída do Coordenador para tarefas: humano, com nota,
    proposta rechecada contra o estado ATUAL. ATÔMICO de ponta a ponta:
    status da proposta, criação e liberação das tarefas e decisão da tarefa
    do Coordenador confirmam juntos ou revertem juntos."""
    _exigir_humano(ator, nota)
    p = repo.proposta(proposal_id)
    if p is None:
        raise orq.DecisaoInvalida(f"proposta {proposal_id} inexistente")
    exigir_etapa_suportada(repo, p["unit_id"], "aprovar_proposta")
    with repo.transacao():
        p = repo.proposta(proposal_id, travar=True)
        if p["status"] != "proposta":
            raise orq.TransicaoInvalida(
                f"proposta {proposal_id} está {p['status']!r}")
        coord = _coordenador_aguardando(repo, p)
        erros = checar_proposta(repo, p["unit_id"], p["plan"], teto=teto,
                                pacote=p["pack"], raiz=raiz)
        if erros:
            raise PropostaInvalida("; ".join(erros))
        linhas = orq.linhas_do_plano(repo, p["unit_id"], p["plan"],
                                     teto=teto, pacote=p["pack"], raiz=raiz)
        criadas = repo.aprovar_proposta(
            proposal_id, linhas, f"coordenador/tarefa:{p['task_id']}", ator,
            nota)
        repo.promover_prontas(p["unit_id"], orq.ATOR)
        orq.decidir(repo, coord["id"], aceitar=True, ator=ator,
                    nota=f"proposta {proposal_id} aprovada: {nota}")
    return [repo.tarefa(t["id"]) for t in criadas]


def recusar_proposta(repo: Any, proposal_id: int, *, ator: str,
                     nota: str) -> None:
    """Recusa ATÔMICA: proposta recusada (preservada) e tarefa do
    Coordenador recusada juntas, ou nada."""
    _exigir_humano(ator, nota)
    if repo.proposta(proposal_id) is None:
        raise orq.DecisaoInvalida(f"proposta {proposal_id} inexistente")
    with repo.transacao():
        p = repo.proposta(proposal_id, travar=True)
        if p["status"] != "proposta":
            raise orq.TransicaoInvalida(
                f"proposta {proposal_id} está {p['status']!r}")
        coord = _coordenador_aguardando(repo, p)
        repo.recusar_proposta(proposal_id, ator, nota)
        orq.decidir(repo, coord["id"], aceitar=False, ator=ator,
                    nota=f"proposta {proposal_id} recusada: {nota}")


# --- semeadura ----------------------------------------------------------------------

def semear_coordenador(repo: Any, unit: dict[str, Any], *, pacote: str,
                       teto: float, orcamento_usd: float,
                       criado_por: str, ref: str = "coordenador-1",
                       raiz: Any = None) -> dict[str, Any]:
    """Cria (sem modelo) a tarefa do Coordenador com a entrada montada.
    Exige plano de investigação aprovado e unit sem perfil surface."""
    exigir_etapa_suportada(repo, unit, "coordenar")
    if plano_aprovado(repo, unit["id"]) is None:
        raise ValueError(f"sem_plano_aprovado: {unit['canonical_name']}")
    entrada = entrada_do_coordenador(repo, unit, teto=teto,
                                     reserva_coordenador=orcamento_usd)
    plano = {"tarefas": [{
        "ref": ref, "role": "coordenador",
        "title": "Propor o grafo de tarefas da unit",
        "input_json": entrada,
        "acceptance": ("plano_tarefas válido; cada tarefa cita o gate do "
                       "pacote e as pendências que atende; toda pesquisa "
                       "aberta do plano aprovado coberta; orçamento dentro "
                       "do saldo; fica como PROPOSTA até o operador aprovar"),
        "depends_on": [], "budget_usd": orcamento_usd, "priority": 0,
        "gate": "0", "justificativa": "semeadura do Coordenador"}]}
    [tarefa] = orq.planejar(repo, unit["id"], plano, criado_por=criado_por,
                            teto=teto, pacote=pacote, raiz=raiz)
    return tarefa
