"""VS3 — exame canônico sob simulação: grafo, posições, verificação cega.

Uma sessão de Examinador (Opus) transforma o que o Case File já sabe em
posição canônica: data de corte com evidência, grafo de título com toda
ligação apontando claim+documento, classificação por item de população e
células candidatas de DDR (sem tocar o workbook). Depois, o laço de
verificação CEGA (família B) confere as afirmações materiais — transcrição
independente do Exhibit A em lote e perguntas dirigidas —, e a reconciliação
determinística fecha os entregáveis. Nenhuma inferência vira fato: o tipo de
resultado é declarado no claim e conferido nos relatórios.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.casefile import caneta, custo, ferramentas, sessao, verificador
from src.casefile.acervo import montar_acervo

TIPOS_RESULTADO = ("fato_documental", "inferencia", "conclusao_titulo",
                   "divergencia", "nao_verificavel", "documento_ausente",
                   "impedido_pela_simulacao")
CLASSIFICACOES = ("comprovada", "comprovada_com_ressalva", "divergente",
                  "nao_verificavel_na_simulacao", "fora_da_area_da_unit")

SISTEMA_VS3 = """Voce e o examinador de titulo desta unidade. Respeite o modo
de operacao e as decisoes explicitas fornecidas na tarefa. Somente documentos
locais autorizados; nenhum acesso externo por esta sessao. Em simulacao,
nenhuma certificacao de WI/NRI. O PLM Report/DDR preenchido permanece bloqueado.

Sua materia-prima principal sao os CLAIMS ja registrados (o digest esta no
task) — nao releia o que ja esta provado. Leituras novas so para o que o
task pede.

DISCIPLINA DE RESULTADO: todo claim novo carrega no valor a chave
`tipo_resultado` com um de: fato_documental, inferencia, conclusao_titulo,
divergencia, nao_verificavel, documento_ausente, impedido_pela_simulacao.
Inferencia plausivel NUNCA vira fato. Conclusao dependente de documentos indisponiveis e declarada com a lacuna,
sem inventar evidencia ou verificacao.

Branco declarado e melhor que numero plausivel."""


# --- ferramentas específicas do VS3 -----------------------------------------

FERRAMENTAS_VS3: list[dict[str, Any]] = [
    {
        "name": "propor_grafo",
        "description": (
            "O grafo de titulo da unit. Nos: tracts, leases, interesses, "
            "partes, instrumentos, TOs. Arestas: baseline de TO, "
            "assignment, top lease, ORRI/NPRI, release, gap, curative, "
            "pooling-consent etc. CADA aresta cita claim_id e documento "
            "(nome logico ou sha256:) — aresta sem evidencia e recusada. "
            "Repropor substitui."),
        "input_schema": {"type": "object", "properties": {
            "nodes": {"type": "array", "items": {"type": "object",
                      "properties": {"id": {"type": "string"},
                                     "tipo": {"type": "string"},
                                     "rotulo": {"type": "string"}},
                      "required": ["id", "tipo", "rotulo"]}},
            "edges": {"type": "array", "items": {"type": "object",
                      "properties": {"de": {"type": "string"},
                                     "para": {"type": "string"},
                                     "tipo": {"type": "string"},
                                     "claim_id": {"type": "integer"},
                                     "documento": {"type": "string"},
                                     "pagina": {"type": "string"},
                                     "nota": {"type": "string"}},
                      "required": ["de", "para", "tipo", "claim_id",
                                   "documento"]}}},
            "required": ["nodes", "edges"]},
    },
    {
        "name": "classificar_populacao",
        "description": (
            "Posicao canonica por item material (tract N, lease X, cadeia "
            "bra-de, TO Y, well, doto/doi...). Classificacoes: comprovada, "
            "comprovada_com_ressalva, divergente, "
            "nao_verificavel_na_simulacao, fora_da_area_da_unit. Cada item "
            "cita os claim_ids que o sustentam."),
        "input_schema": {"type": "object", "properties": {
            "itens": {"type": "array", "items": {"type": "object",
                      "properties": {
                          "item": {"type": "string"},
                          "classificacao": {"type": "string",
                                            "enum": list(CLASSIFICACOES)},
                          "claim_ids": {"type": "array",
                                        "items": {"type": "integer"}},
                          "nota": {"type": "string"}},
                      "required": ["item", "classificacao", "claim_ids"]}}},
            "required": ["itens"]},
    },
    {
        "name": "propor_claims_ddr",
        "description": (
            "Marca claims prontos para o DDR: celulas/abas CANDIDATAS "
            "(nada e escrito no workbook agora) e limitacoes. So claims "
            "desta unit."),
        "input_schema": {"type": "object", "properties": {
            "itens": {"type": "array", "items": {"type": "object",
                      "properties": {
                          "claim_id": {"type": "integer"},
                          "celulas_candidatas": {"type": "array",
                                                 "items": {"type":
                                                           "string"}},
                          "limitacoes": {"type": "string"}},
                      "required": ["claim_id", "celulas_candidatas"]}}},
            "required": ["itens"]},
    },
]


def montar_dispatch_vs3(*, base: dict[str, Any], repo: Any,
                        unit: dict[str, Any], pasta: Path,
                        session_ref: dict[str, Any]) -> dict[str, Any]:
    sha_por_nome = repo.sha_por_nome(unit["id"])

    def _doc_ok(documento: str) -> bool:
        from src.casefile.acervo import _norm
        d = str(documento or "")
        if d.lower().startswith("sha256:"):
            return repo.sha_existe(d[7:].lower())
        return bool(sha_por_nome.get(_norm(d)))

    def _propor_grafo(nodes: list[dict[str, Any]],
                      edges: list[dict[str, Any]]) -> dict[str, Any]:
        ids = {n["id"] for n in nodes}
        rejeitadas = []
        boas = []
        for i, e in enumerate(edges):
            erros = []
            if e["de"] not in ids or e["para"] not in ids:
                erros.append("no inexistente")
            if not repo.claim_existe(unit["id"], int(e["claim_id"])):
                erros.append(f"claim {e['claim_id']} nao e desta unit")
            if not _doc_ok(e["documento"]):
                erros.append(f"documento {e['documento']!r} fora do censo")
            if erros:
                rejeitadas.append({"indice": i, "erros": erros})
            else:
                boas.append(e)
        if rejeitadas and not boas:
            return {"aceito": False, "rejeitadas": rejeitadas}
        grafo = {"unit": unit["canonical_name"],
                 "gerado_em": datetime.now(timezone.utc).isoformat(
                     timespec="seconds"),
                 "nodes": nodes, "edges": boas,
                 "edges_rejeitadas": rejeitadas}
        path = caneta.escrever_texto(
            caneta.caminho(pasta) / "CHAIN_GRAPH_VS3.json",
            json.dumps(grafo, ensure_ascii=False, indent=1))
        versao = 1 + len(repo.deliverables(unit["id"], "chain_graph_vs3"))
        import hashlib
        repo.registrar_deliverable(
            unit["id"], "chain_graph_vs3", versao, str(path),
            hashlib.sha256(path.read_bytes()).hexdigest())
        return {"aceito": True, "nodes": len(nodes), "edges": len(boas),
                "rejeitadas": rejeitadas}

    def _classificar(itens: list[dict[str, Any]]) -> dict[str, Any]:
        aceitos, rejeitados = 0, []
        for i, item in enumerate(itens):
            ruins = [c for c in item["claim_ids"]
                     if not repo.claim_existe(unit["id"], int(c))]
            if ruins:
                rejeitados.append({"indice": i,
                                   "erro": f"claims {ruins} nao sao desta "
                                           f"unit"})
                continue
            repo.gravar_posicao(
                unit["id"], item["item"], item["classificacao"],
                [int(c) for c in item["claim_ids"]],
                item.get("nota", ""), session_ref["id"])
            aceitos += 1
        return {"aceitos": aceitos, "rejeitados": rejeitados}

    def _claims_ddr(itens: list[dict[str, Any]]) -> dict[str, Any]:
        aceitos, rejeitados = 0, []
        for i, item in enumerate(itens):
            try:
                repo.atualizar_claim_ddr(
                    unit["id"], int(item["claim_id"]),
                    list(item["celulas_candidatas"]),
                    item.get("limitacoes", ""))
                aceitos += 1
            except ValueError as exc:
                rejeitados.append({"indice": i, "erro": str(exc)})
        return {"aceitos": aceitos, "rejeitados": rejeitados}

    got = dict(base)
    got.update({"propor_grafo": _propor_grafo,
                "classificar_populacao": _classificar,
                "propor_claims_ddr": _claims_ddr})
    return got


# --- task da sessão ----------------------------------------------------------

def _digest_claims(repo: Any, unit: dict[str, Any]) -> str:
    linhas = []
    for c in repo.claims_da_unit(unit["id"]):
        chaves = {k: v for k, v in c["value"].items()
                  if k in ("lease_no", "lessor", "vol", "page", "tract_no",
                           "to_id", "certification_date", "classificacao",
                           "abrange_a669_ou_a319", "party", "fontes",
                           "esperado", "natureza")}
        linhas.append(f"[{c['id']}|{c['claim_type']}] {c['entity'][:56]}"
                      + (f" {json.dumps(chaves, ensure_ascii=False)[:110]}"
                         if chaves else ""))
    return "\n".join(linhas)


def _task(repo: Any, unit: dict[str, Any]) -> str:
    if repo.politica(unit["id"], "examination_profile") == "josh_b_golden":
        if unit['canonical_name'].strip().upper() != 'JOSH B UNIT':
            raise ValueError('josh_profile_outside_fixture_unit')
        from src.casefile.profile_josh_b import task_josh_b
        return task_josh_b(repo, unit)
    from src.casefile.simulacao import ativa
    populations = {name: [f"{name}::{m['member']}" for m in repo.populacao(unit['id'], name)]
                   for name in repo.populacoes_contagens(unit['id'])}
    return (f"UNIDADE: {unit['canonical_name']}\n"
            + f"SIMULATION_MODE: {ativa(repo, unit['id'])}\n"
            + "Examine somente o escopo, populacoes e decisoes desta unit. "
            + "Determine certification e data de corte com evidencia; se desconhecidas, peca intervencao. "
            + "Proponha grafo com evidencia, classifique cada membro pelo identificador exato population::member, "
            + "declare dependencias, ressalvas e celulas candidatas sem escrever workbook.\n"
            + json.dumps(populations, ensure_ascii=False) + "\n"
            + json.dumps(repo.decisoes_da_unit(unit['id']), ensure_ascii=False, default=str) + "\n"
            + _digest_claims(repo, unit))


# --- execução ---------------------------------------------------------------

def executar_sessao(*, repo: Any, unit: dict[str, Any], pasta: Path,
                    client: Any = None, max_cost_usd: float) -> Any:
    from src.infra.cache import PageCache
    from src.infra.okf import KnowledgeBase

    acervo = montar_acervo(pasta, {}, incluir_entrega=True,
                           cache=PageCache())
    session_ref: dict[str, Any] = {"id": None}
    base = ferramentas.montar_dispatch(
        acervo=acervo, repo=repo, unit=unit, pasta=pasta,
        kb_unidade=KnowledgeBase(pasta / "_casefile" / "fichas"),
        kb_global=KnowledgeBase(),
        ator=f"modelo:{sessao.modelo()}", session_ref=session_ref)
    from src.casefile import ferramentas_vs2
    base = ferramentas_vs2.montar_dispatch_vs2(
        base=base, repo=repo, unit=unit, pasta=pasta,
        session_ref=session_ref)
    dispatch = montar_dispatch_vs3(base=base, repo=repo, unit=unit,
                                   pasta=pasta, session_ref=session_ref)
    tools = (ferramentas.FERRAMENTAS_LEITURA + ferramentas.FERRAMENTAS_ESCRITA
             + [t for t in ferramentas_vs2.FERRAMENTAS_VS2
                if t["name"] == "pedir_intervencao"]
             + FERRAMENTAS_VS3)
    log, _sid = sessao.rodar(
        repo=repo, unit=unit, pasta=pasta, comando="exame.vs3",
        sistema=SISTEMA_VS3, task=_task(repo, unit), ferramentas=tools,
        dispatch=dispatch, modelo_sessao=sessao.modelo(),
        max_cost_usd=max_cost_usd, client=client, max_turns=80,
        session_ref=session_ref)
    return log


def executar_verificacao(*, repo: Any, unit: dict[str, Any], pasta: Path,
                         chamar: Any = None) -> dict[str, Any]:
    """Verificação cega das afirmações materiais — família B + comparação
    determinística. Para no teto próprio; o não-verificado fica declarado."""
    acervo = montar_acervo(pasta, {}, incluir_entrega=True)
    sha_nomes: dict[str, str] = {}
    for nome, shas in repo.sha_por_nome(unit["id"]).items():
        for sha in shas:
            sha_nomes.setdefault(sha, nome)
    cust = verificador._CustoB()
    resumo = {"lote_exhibit_a": None, "dirigidas": [], "puladas_teto": 0}

    def _png(nome: str, pagina: Any) -> bytes | None:
        try:
            got = acervo.read_page(nome, pagina, "imagem")
            return got.get("png") if got.get("kind") == "image" else None
        except Exception:
            return None

    def _sha_doc(nome: str) -> str | None:
        import hashlib
        try:
            return hashlib.sha256(acervo.index.read_bytes(nome)).hexdigest()
        except Exception:
            return None

    # 1) lote: transcrição independente do Exhibit A (p.3 e p.4 da DPU).
    leases = repo.claims_da_unit(unit["id"], "lease_in_unit")
    # O unit dec CERTO: pastas de lease carregam designations de OUTRAS
    # units (0126714-* tem A-730) — o nome tem que carregar os tokens desta.
    from src.casefile.referencia import unit_identity_tokens
    tokens = {t.lower() for t in
              unit_identity_tokens(unit["canonical_name"])}
    dpu_nome = next((n for n in acervo.names()
                     if "unit dec" in n and "rec" in n
                     and all(t in n for t in tokens)), None)
    # Só verificação VÁLIDA conta como feita — invalidada refaz.
    ja = {v["claim_id"] for v in repo.verificacoes(unit["id"])
          if v.get("status", "valida") == "valida"}
    pendentes_lote = [c for c in leases if c["id"] not in ja]
    if dpu_nome and pendentes_lote:
        pngs = [p for p in (_png(dpu_nome, 3), _png(dpu_nome, 4)) if p]
        if pngs:
            resumo["lote_exhibit_a"] = verificador.verificar_lote_exhibit_a(
                repo=repo, unit=unit, claims_lease=pendentes_lote,
                pngs=pngs, sha_doc=_sha_doc(dpu_nome), chamar=chamar,
                custo=cust)

    # 2) dirigidas: perguntas por claim material (tabela determinística).
    for claim, pergunta, campo, ev in _perguntas_materiais(repo, unit,
                                                           sha_nomes):
        if claim["id"] in ja:
            continue
        if cust.total >= verificador.teto_verificacao():
            resumo["puladas_teto"] += 1
            continue
        texto_ev, png_ev = "", None
        nome_ev = sha_nomes.get(claim["source_sha256"])
        pagina_ev = _pagina_int(claim["page"])
        if ev == "texto" and nome_ev:
            try:
                got = acervo.read_page(nome_ev, pagina_ev, "texto")
                texto_ev = got.get("text", "")
            except Exception:
                texto_ev = ""
        elif nome_ev:
            png_ev = _png(nome_ev, pagina_ev)
        if not texto_ev and png_ev is None:
            repo.registrar_verificacao(
                claim["id"], pergunta, "nao_verificavel",
                verificador.modelo_b(), {},
                {"motivo": "evidencia nao renderizavel"}, 0.0, None,
                rastreio={"source_sha256": claim["source_sha256"],
                          "page": str(pagina_ev)})
            continue
        got = verificador.verificar_pergunta(
            repo=repo, claim=claim, pergunta=pergunta,
            campo_do_claim=campo, evidencia_texto=texto_ev,
            evidencia_png=png_ev,
            sha_doc_renderizado=_sha_doc(nome_ev) if nome_ev else None,
            pagina_renderizada=pagina_ev, chamar=chamar, custo=cust)
        resumo["dirigidas"].append(got)

    repo.registrar_custo(unit["id"], "verificacao", cust.total,
                         {"modelo_b": verificador.modelo_b(),
                          "chamadas": len(resumo["dirigidas"]) + 2})
    resumo["custo_usd"] = cust.total
    return resumo


def _pagina_int(page: str) -> int:
    try:
        return int(str(page).split("-")[0].split(",")[0].strip())
    except ValueError:
        return 1


def _perguntas_materiais(repo: Any, unit: dict[str, Any],
                         sha_nomes: dict[str, str]):
    """(claim, pergunta, campo esperado, modo de evidência) — seleção
    DETERMINÍSTICA por tipo/chaves; nada de amostragem silenciosa."""
    for c in repo.claims_da_unit(unit["id"]):
        v = c["value"]
        if c["claim_type"] == "tract" and v.get("tract_no") and \
                v.get("acres"):
            yield (c, f"Na tabela MINERAL OWNER/ACREAGE do plat, quantos "
                      f"ACRES tem o tract {v['tract_no']}?",
                   v["acres"], "imagem")
        elif c["claim_type"] == "unit_identity" and "recording" not in \
                c["entity"].lower() and v.get("fonte_autoridade"):
            continue
        elif "certification_date" in v:
            yield (c, "Qual a data 'as of' da certificacao de titularidade "
                      "declarada nesta pagina? (formato AAAA-MM-DD)",
                   v["certification_date"], "texto")
        elif "abrange_a669_ou_a319" in v and v.get("leitura_completa"):
            yield (c, "Em qual survey/abstract ficam as terras descritas "
                      "neste instrumento?",
                   "a-811" if v["abrange_a669_ou_a319"] == "nao"
                   else "a-669", "imagem")
        elif c["claim_type"] == "fact" and \
                "classificacao" in v and "top lease" in \
                str(v.get("classificacao", "")).lower():
            yield (c, "Segundo este memorando, o prazo desta lease comeca "
                      "(a) na data do instrumento, (b) quando a Prior "
                      "Lease terminar, ou (c) outro? Responda a, b ou c.",
                   "b", "imagem")
        elif c["id"] and "release of suspense" in c["entity"].lower() \
                or (c["claim_type"] == "fact"
                    and "leitura do pdf autorizado" in c["entity"].lower()):
            yield (c, "Este documento contem volume/pagina ou file number "
                      "de registro do Quitclaim Deed? Responda 'sim: "
                      "<referencia>' ou 'nao'.",
                   "nao", "texto")
