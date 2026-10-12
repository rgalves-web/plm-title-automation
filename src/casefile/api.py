"""Local PLM workbench: persisted Case File queries and explicit operator commands.

Start with python -m src.casefile.workbench serve for the four workers.
The older consultation endpoints remain read-only; commands use revision and ID.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from src.casefile import custo as custo_mod
from src.casefile import gates as gates_mod
from src.casefile import portal, simulacao

app = FastAPI(title="PLM — Esteira de agentes e Case File")
app.mount('/static', StaticFiles(directory=Path(__file__).parent/'static'), name='static')

_STATIC = Path(__file__).parent / "static" / "operations.html"


def get_repo() -> Any:
    from src.casefile.db import connect
    from src.casefile.repo import Repo
    conn = connect()
    try:
        yield Repo(conn)
    finally:
        conn.close()


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _linha(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _iso(v) for k, v in row.items()}


def _unit_ou_404(repo: Any, unit_id: int) -> dict[str, Any]:
    for u in repo.listar_units():
        if u["id"] == unit_id:
            return u
    raise HTTPException(404, f"unit {unit_id} nao existe")


def _modo(repo: Any, unit_id: int) -> str:
    return "SIMULATION" if simulacao.ativa(repo, unit_id) else "PRODUCTION"


def _ultima_atividade(repo: Any, unit_id: int) -> str | None:
    """Considera transições, sessões, claims, verificações, decisões,
    custos e entregáveis (veredito CTO, item 6)."""
    ts: list[Any] = []
    ts += [t["at"] for t in repo.transicoes(unit_id)]
    for s in repo.sessoes_da_unit(unit_id):
        ts.append(s.get("ended_at") or s.get("started_at"))
    ts += [c.get("created_at") for c in repo.claims_da_unit(unit_id)]
    ts += [v.get("at") for v in repo.verificacoes(unit_id)]
    ts += [d.get("decided_at") for d in repo.decisoes_da_unit(unit_id)]
    ts += [c.get("at") for c in repo.custos_da_unit(unit_id)]
    for kind in ("relatorio_coleta_vs2", "reconciliacao_recordings",
                 "chain_graph_vs3", "title_examination_vs3"):
        ts += [d.get("created_at") for d in repo.deliverables(unit_id, kind)]
    ts = [_iso(x) for x in ts if x is not None]
    return max(ts) if ts else None


def _verificacao_buckets(repo: Any,
                         claims: list[dict[str, Any]],
                         verifs: list[dict[str, Any]]) -> dict[str, int]:
    """Último veredito VÁLIDO por claim — tentativa não é concordância."""
    ultimo: dict[int, str] = {}
    for v in verifs:
        if v.get("status", "valida") == "valida":
            ultimo[v["claim_id"]] = v["verdict"]
    ids = {c["id"] for c in claims}
    meus = {cid: verd for cid, verd in ultimo.items() if cid in ids}
    return {"tentadas": len(meus),
            "concordantes": sum(1 for x in meus.values()
                                if x == "concordancia"),
            "divergentes": sum(1 for x in meus.values()
                               if x == "divergencia"),
            "insuficientes": sum(1 for x in meus.values()
                                 if x == "evidencia_insuficiente"),
            "nao_verificaveis": sum(1 for x in meus.values()
                                    if x == "nao_verificavel")}


_API_RE = re.compile(r"42-?337-?\d{5}")


def _blockers(repo: Any, unit_id: int) -> dict[str, Any]:
    itens = repo.collection_items(unit_id)
    return {
        "bloqueados_simulacao": [i["title"] for i in itens
                                 if i["status"] == "bloqueado_simulacao"],
        "requer_intervencao": [i["title"] for i in itens
                               if i["status"] == "requer_intervencao"],
        "perguntas_abertas": len(repo.perguntas_vs2_abertas(unit_id)),
        "gates_bloqueando": [g["condicao"] for g in
                             gates_mod.avaliar(repo,
                                               {"id": unit_id,
                                                "canonical_name": ""})
                             if g["status"] in gates_mod.BLOQUEIAM],
    }


def _progresso(repo: Any, unit_id: int) -> dict[str, Any]:
    """Progresso por POPULAÇÕES, nunca um percentual único (item C6)."""
    pops = repo.populacoes_contagens(unit_id)
    claims = repo.claims_da_unit(unit_id)
    verifs = repo.verificacoes(unit_id)
    com_verif = {v["claim_id"] for v in verifs}
    leases = repo.claims_da_unit(unit_id, "lease_in_unit")
    posicoes = repo.posicoes(unit_id)
    censo = repo.contagem_censo(unit_id)
    return {
        "documentos": {
            "no_censo_por_origem": {o: d["conteudos"]
                                    for o, d in censo.items()},
            "ausentes_declarados": pops.get(
                "documentos_ausentes_incompletos", 0),
            "bloqueados_simulacao": len(
                repo.collection_items(unit_id, "bloqueado_simulacao")),
        },
        "leases": {"exhibit_a": pops.get("dpu_exhibit_a", 0),
                   "potencialmente_contribuintes":
                       pops.get("dpu_exhibit_a", 0)
                       - pops.get("in_dpu_but_zero_unit_acres", 0),
                   "zero_unit_acres":
                       pops.get("in_dpu_but_zero_unit_acres", 0),
                   "com_claim": len(leases),
                   # tentativa != verificada: os baldes falam por si
                   "verificacao": _verificacao_buckets(repo, leases,
                                                       verifs)},
        # o claim da linha TOTAL do Exhibit C não é um tract
        "tracts": sum(1 for c in repo.claims_da_unit(unit_id, "tract")
                      if "total" not in str(
                          c["value"].get("tract_no", "")).lower()
                      and "total" not in c["entity"].lower()),
        # poços = APIs distintos citados (normalizados: com e sem hífen são
        # o MESMO poço), nunca contagem de claims
        "wells": len({m.group().replace("-", "") for c in claims
                      for m in [_API_RE.search(
                          c["entity"] + str(c["value"]))] if m}),
        "claims": {"ativos": len(claims),
                   "verificacao": _verificacao_buckets(repo, claims,
                                                       verifs),
                   "prontos_para_ddr": sum(1 for c in claims
                                           if c.get("ddr_candidates"))},
        "divergencias": len(repo.claims_da_unit(unit_id, "divergence")),
        "curativas": sum(1 for c in claims
                         if "curative" in c["entity"].lower()),
        "gates": {g["condicao"]: g["status"]
                  for g in gates_mod.avaliar(
                      repo, {"id": unit_id, "canonical_name": ""})},
        "posicoes_canonicas": len(posicoes),
        "prontidao_proxima_etapa": {
            "gates_bloqueando": sum(
                1 for g in gates_mod.avaliar(
                    repo, {"id": unit_id, "canonical_name": ""})
                if g["status"] in gates_mod.BLOQUEIAM),
            "aguarda_aprovacao_operador": True},
    }


# --- endpoints ---------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _STATIC.read_text(encoding="utf-8")


@app.get('/legacy', response_class=HTMLResponse)
def legacy_index():
    return (Path(__file__).parent/'static'/'index.html').read_text(encoding='utf-8')


@app.get("/api/units")
def units(repo: Any = Depends(get_repo)) -> list[dict[str, Any]]:
    out = []
    for u in repo.listar_units():
        custos = repo.custo_por_categoria(u["id"])
        bl = _blockers(repo, u["id"])
        sess_ativa = next((s for s in repo.sessoes_da_unit(u["id"])
                           if s.get("ended_at") is None), None)
        # Saúde reflete sessão interrompida e marco incompleto (item 6).
        sessoes_exame = [s for s in repo.sessoes_da_unit(u["id"])
                         if s["command"].startswith("exame.")]
        exame_interrompido = bool(
            sessoes_exame
            and "INTERROMPIDA" in (sessoes_exame[-1].get("stop_reason")
                                   or ""))
        marco_incompleto = (u["state"] == "EXAMINANDO"
                            and not repo.posicoes(u["id"]))
        atencao = (bool(bl["gates_bloqueando"])
                   or bool(bl["requer_intervencao"])
                   or exame_interrompido or marco_incompleto)
        out.append({
            "id": u["id"], "projeto": u.get("engagement", ""),
            "unit": u["canonical_name"], "estado": u["state"],
            "modo": _modo(repo, u["id"]),
            "ultima_atividade": _ultima_atividade(repo, u["id"]),
            "etapa_atual": u["state"],
            "agente_ativo": (f"{sess_ativa['command']} "
                             f"({sess_ativa['model']})"
                             if sess_ativa else None),
            "progresso": _progresso(repo, u["id"]),
            "blockers": (len(bl["bloqueados_simulacao"])
                         + len(bl["requer_intervencao"])
                         + len(bl["gates_bloqueando"])),
            "decisoes_aguardando": bl["perguntas_abertas"],
            "custo_ia": round(custos.get("modelo", 0.0)
                              + custos.get("verificacao", 0.0), 4),
            "custo_portal": custos.get("coleta", 0.0),
            "orcamento": custo_mod.teto_unit(),
            "prazo_sla": None,
            "saude": "atencao" if atencao else "ok",
            "saude_motivos": ([m for m, cond in (
                ("sessao de exame interrompida", exame_interrompido),
                ("marco VS3 incompleto (0 posicoes)", marco_incompleto),
                ("gates bloqueando", bool(bl["gates_bloqueando"])),
                ("itens requerem intervencao",
                 bool(bl["requer_intervencao"]))) if cond]),
        })
    return out


@app.get("/api/units/{unit_id}")
def unit_detalhe(unit_id: int, repo: Any = Depends(get_repo)
                 ) -> dict[str, Any]:
    u = _unit_ou_404(repo, unit_id)
    custos = repo.custo_por_categoria(unit_id)
    return {
        "unit": _linha(u), "modo": _modo(repo, unit_id),
        "gates": gates_mod.avaliar(repo, u),
        "populacoes": repo.populacoes_contagens(unit_id),
        "posicoes": [_linha(p) for p in repo.posicoes(unit_id)],
        "custos": {"por_categoria": custos,
                   "total": repo.custo_acumulado(unit_id),
                   "orcamento": custo_mod.teto_unit(),
                   "teto_coleta": portal.teto_coleta()},
        "progresso": _progresso(repo, unit_id),
        "training": unit_training(unit_id, repo),
        "deliverables": {
            kind: [_linha(d) for d in repo.deliverables(unit_id, kind)]
            for kind in ("relatorio_coleta_vs2", "reconciliacao_recordings",
                         "chain_graph_vs3", "title_examination_vs3",
                         "claims_ready_vs3", "unresolved_vs3",
                         "coverage_vs3", "cost_vs3")},
    }


@app.get("/api/units/{unit_id}/training")
def unit_training(unit_id: int, repo: Any = Depends(get_repo)) -> dict[str, Any]:
    from src.casefile.training_runtime import review_coverage
    _unit_ou_404(repo, unit_id)
    audit = repo.knowledge_audit(unit_id)
    return {**audit, 'review_coverage': review_coverage(audit)}


@app.get("/api/units/{unit_id}/claims")
def unit_claims(unit_id: int, tipo: str | None = None,
                repo: Any = Depends(get_repo)) -> list[dict[str, Any]]:
    _unit_ou_404(repo, unit_id)
    verifs = repo.verificacoes(unit_id)
    por_claim: dict[int, list[str]] = {}
    for v in verifs:
        por_claim.setdefault(v["claim_id"], []).append(v["verdict"])
    return [{
        "id": c["id"], "tipo": c["claim_type"], "entidade": c["entity"],
        "materialidade": c["materiality"], "confianca": c["confidence"],
        "benchmark_contamination":
            bool(c["value"].get("benchmark_contamination")),
        "verificacao": por_claim.get(c["id"], []),
        "ddr_candidatas": len(c.get("ddr_candidates") or []),
    } for c in repo.claims_da_unit(unit_id, tipo)]


@app.get("/api/claims/{claim_id}")
def claim_detalhe(claim_id: int, repo: Any = Depends(get_repo)
                  ) -> dict[str, Any]:
    c = repo.claim(claim_id)
    if c is None:
        raise HTTPException(404, f"claim {claim_id} nao existe")
    sessoes = {s["id"]: s for s in repo.sessoes_da_unit(c["unit_id"])}
    sess = sessoes.get(c["session_id"], {})
    nomes = [n for n, shas in repo.sha_por_nome(c["unit_id"]).items()
             if c["source_sha256"] in shas]
    return {
        "claim": _linha(c),
        "orientacoes": [e for e in repo.knowledge_audit(c['unit_id'])['events']
                         if e['kind'] == 'applied' and e['detail'].get('claim_id') == claim_id],
        "documento": {"sha256": c["source_sha256"], "nomes": nomes[:5],
                      "pagina": c["page"], "trecho": c["evidence"]},
        "examinador": {"modelo": sess.get("model", ""),
                       "comando_versao_prompt": sess.get("command", "")},
        "verificacoes": [_linha(v)
                         for v in repo.verificacoes_do_claim(claim_id)],
        "origem": c["value"].get("origem_evidencia", "corpus_autonomo"),
        "benchmark_contamination":
            bool(c["value"].get("benchmark_contamination")),
        "materialidade": c["materiality"],
        "limitacoes": c.get("limitations", ""),
        "celulas_candidatas_ddr": c.get("ddr_candidates", []),
    }


@app.get("/api/units/{unit_id}/documentos")
def unit_documentos(unit_id: int, repo: Any = Depends(get_repo)
                    ) -> dict[str, Any]:
    _unit_ou_404(repo, unit_id)
    return {
        "censo_por_origem": repo.contagem_censo(unit_id),
        "ausentes": [{"claim": c["id"], "entidade": c["entity"],
                      "esperado": c["value"].get("esperado", "")}
                     for c in repo.claims_da_unit(unit_id,
                                                  "document_missing")],
        "itens_coleta": [_linha(i)
                         for i in repo.collection_items(unit_id)],
        "buscas": [_linha(b) for b in repo.buscas(unit_id)],
    }


@app.get("/api/units/{unit_id}/timeline")
def unit_timeline(unit_id: int, repo: Any = Depends(get_repo)
                  ) -> list[dict[str, Any]]:
    _unit_ou_404(repo, unit_id)
    eventos: list[dict[str, Any]] = []
    for t in repo.transicoes(unit_id):
        eventos.append({"quando": _iso(t["at"]), "ator": t["actor"],
                        "acao": t["event"], "de": t["from_state"],
                        "para": t["to_state"], "motivo": t["note"],
                        "custo": None, "tipo": "transicao"})
    for s in repo.sessoes_da_unit(unit_id):
        eventos.append({"quando": _iso(s["started_at"]),
                        "ator": f"modelo:{s['model']}",
                        "acao": f"sessao {s['command']}",
                        "de": None, "para": None,
                        "motivo": s.get("stop_reason", ""),
                        "custo": float(s["cost_usd"] or 0),
                        "versao_prompt": s["command"],
                        "tipo": "sessao"})
    for d in repo.decisoes_da_unit(unit_id):
        eventos.append({"quando": _iso(d.get("decided_at")),
                        "ator": "operador", "acao": d["kind"],
                        "de": None, "para": None,
                        "motivo": (d["question"] + " " +
                                   (d.get("answer") or ""))[:300],
                        "custo": None, "tipo": "decisao"})
    return sorted(eventos, key=lambda e: e["quando"] or "")


@app.get("/api/units/{unit_id}/intervencoes")
def unit_intervencoes(unit_id: int, repo: Any = Depends(get_repo)
                      ) -> dict[str, Any]:
    """State/mode-aware (veredito CTO, itens 3 e 6): a FILA atual carrega
    somente decisões reais e acionáveis no modo presente; o que exigiria
    PM/seller ou coleta paga em SIMULATION vai para dependências de
    produção — visível, mas fora da fila."""
    _unit_ou_404(repo, unit_id)
    simulacao_ativa = simulacao.ativa(repo, unit_id)
    agora = datetime.now(timezone.utc)
    fila: list[dict[str, Any]] = []
    producao: list[dict[str, Any]] = []
    for q in repo.perguntas_vs2_abertas(unit_id):
        fila.append({"criticidade": "alta", "unit_id": unit_id,
                     "pergunta": q["question"],
                     "motivo": "ambiguidade que sobreviveu as leituras",
                     "impacto": "trava o gate da condicao correspondente",
                     "evidencias": f"claim {q.get('claim_id')}",
                     "acao_necessaria": "responder a pergunta",
                     "aguardando_desde": None, "id": q["id"]})
    for i in repo.collection_items(unit_id, "bloqueado_simulacao"):
        idade = None
        if i.get("at"):
            try:
                idade = round((agora - i["at"]).total_seconds() / 3600, 1)
            except TypeError:
                idade = None
        item = {"criticidade": "media", "unit_id": unit_id,
                "pergunta": f"Coleta em producao: {i['title']}",
                "motivo": i["note"][:160],
                "impacto": "conclusoes dependentes ficam impedidas",
                "evidencias": json.dumps(i["target"],
                                         ensure_ascii=False)[:160],
                "acao_necessaria": "coleta paga (somente em producao)",
                "aguardando_desde": _iso(i.get("at")),
                "horas_aguardando": idade, "id": f"coleta-{i['id']}"}
        (producao if simulacao_ativa else fila).append(item)
    for p in repo.pesquisas(unit_id, "aberta"):
        if "pm" in p["where_"].lower() or "seller" in p["where_"].lower():
            item = {"criticidade": "media", "unit_id": unit_id,
                    "pergunta": p["title"], "motivo": p["what"][:160],
                    "impacto": "campo do DDR fica em branco declarado",
                    "evidencias": p["where_"],
                    "acao_necessaria": "solicitacao externa "
                                       "(somente em producao)",
                    "aguardando_desde": None, "id": f"pesquisa-{p['id']}"}
            (producao if simulacao_ativa else fila).append(item)
    return {"fila": fila, "dependencias_producao": producao,
            "modo": "SIMULATION" if simulacao_ativa else "PRODUCTION"}


@app.get("/api/claims/{claim_id}/evidencia.png")
def claim_evidencia(claim_id: int, repo: Any = Depends(get_repo)
                    ) -> Response:
    """A página documental citada pelo claim, em pixels — renderização
    local, read-only (item 6: o drawer mostra a página, não só o trecho)."""
    c = repo.claim(claim_id)
    if c is None:
        raise HTTPException(404, f"claim {claim_id} nao existe")
    unit = _unit_ou_404(repo, c["unit_id"])
    from src.casefile.acervo import montar_acervo
    acervo = montar_acervo(Path(unit["folder_path"]), {},
                           incluir_entrega=True)
    nome = next((n for n, shas in
                 repo.sha_por_nome(c["unit_id"]).items()
                 if c["source_sha256"] in shas and acervo.index.exists(n)),
                None)
    if nome is None:
        raise HTTPException(404, "documento do claim fora do acervo")
    try:
        pagina = int(str(c["page"]).split("-")[0].split(",")[0].strip())
    except ValueError:
        pagina = 1
    got = acervo.read_page(nome, pagina, "imagem")
    if got.get("kind") != "image":
        raise HTTPException(404, "pagina nao renderizavel em pixels")
    return Response(content=got["png"], media_type="image/png")


@app.get("/api/units/{unit_id}/grafo")
def unit_grafo(unit_id: int, repo: Any = Depends(get_repo)
               ) -> dict[str, Any]:
    _unit_ou_404(repo, unit_id)
    delivs = repo.deliverables(unit_id, "chain_graph_vs3")
    if not delivs:
        return {"disponivel": False}
    path = Path(delivs[-1]["path"])
    if not path.exists():
        return {"disponivel": False}
    return {"disponivel": True,
            **json.loads(path.read_text(encoding="utf-8"))}


from src.casefile.operations_api import attach as _attach_operations
_attach_operations(app,get_repo)
