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

SISTEMA_VS3 = """Voce e o examinador de titulo desta unidade, em MODO
SIMULACAO (golden replay): somente documentos locais autorizados, nenhum
acesso externo, nenhuma certificacao de WI/NRI, e nada do PLM Report/DDR
preenchido esta disponivel (bloqueado por plumbing).

Sua materia-prima principal sao os CLAIMS ja registrados (o digest esta no
task) — nao releia o que ja esta provado. Leituras novas so para o que o
task pede.

DISCIPLINA DE RESULTADO: todo claim novo carrega no valor a chave
`tipo_resultado` com um de: fato_documental, inferencia, conclusao_titulo,
divergencia, nao_verificavel, documento_ausente, impedido_pela_simulacao.
Inferencia plausivel NUNCA vira fato. Conclusao dependente dos documentos
indisponiveis na simulacao (Prior Lease 441/275, lease 514/412, DOTO/DOI,
Quitclaim Stewart) e `impedido_pela_simulacao` — nunca 'verificada'.

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
    posic = repo.populacoes_contagens(unit["id"])
    return "\n\n".join([
        f"UNIDADE: {unit['canonical_name']} — VS3, exame canonico sob "
        f"simulacao. Populacoes: {posic}. Documentos indisponiveis na "
        f"simulacao: 441.275 (Prior Lease BRA-DE), 514.412 (lease "
        f"0220953/005), DOTO/DOI, Quitclaim/Affidavit/Landman Statement "
        f"Stewart.",

        "DIGEST DOS CLAIMS ATIVOS (sua materia-prima; NAO releia o que ja "
        "esta aqui):\n" + _digest_claims(repo, unit),

        "DEVERES, nesta ordem:\n\n"
        "1. DATA DE CORTE: determine a data de corte do golden case por "
        "FONTE AUTORIZADA (spec BPM, workbooks de referencia datados, "
        "notas datadas, XREF 06-16-2026...). Registre claim fact entidade "
        "'data de corte do exame' com a data, a fonte e o trecho. NUNCA "
        "assuma a data atual de 2026 nem 'ate o presente'. Se "
        "indeterminavel, pedir_intervencao.\n\n"
        "2. GRAFO DE TITULO (`propor_grafo`): por tract, lease e "
        "interesse — baseline dos TOs com certification date, instrumentos "
        "posteriores, mineral owners, lessors/lessees, assignments, "
        "profundidades, top leases, ORRI/NPRI, direitos executivos/nao "
        "executivos, pooling consent, releases, gaps, curatives. Toda "
        "aresta com claim_id + documento.\n\n"
        "3. TO 155ac x UNIT TRACT 2: investigue a relacao entre o parent "
        "tract de 155 ac e o Tract 2 de 80,02 ac por legal descriptions e "
        "metes and bounds (Exhibit B da DPU cita adjoiners com acreagens; "
        "o TO p.1 lista 4 tratos: 119.62+33.72+0.38+1.28). COINCIDENCIA DE "
        "NOMES NAO PROVA amarracao. So registre "
        "`diferenca_gross_explicada` se DEMONSTRAR documentalmente; senao "
        "a amarracao PERMANECE parcial/confianca media (registre o que "
        "falta).\n\n"
        "4. BRA-DE: separe o que os documentos locais PROVAM (top leases "
        "2011, assignment K1401501, ORRI/piso 75%, depths do assignment de "
        "2008) do que fica `impedido_pela_simulacao` sem a Prior Lease "
        "441/275 (vigencia efetiva, termos da prior). \n\n"
        "5. STEWART: separe o que o release-of-suspense prova (em pay, "
        "curative recebido) do que NAO prova (registro); o Quitclaim/"
        "Affidavit/Landman Statement sao `documento_ausente`.\n\n"
        "6. SERIE 0220936: mantenha 67 no Exhibit A, 7 "
        "in_dpu_but_zero_unit_acres (A-811), 60 potencialmente "
        "contribuintes — nada some do Lease Review nem da trilha.\n\n"
        "7. POSICOES (`classificar_populacao`): TODA populacao material "
        "termina classificada — os 5 tracts, o poco, a cadeia BRA-DE, "
        "cada TO, o DOTO/DOI, o release Stewart, e as leases por GRUPO "
        "homogeneo (ex.: '60 leases contribuintes com instrumento no "
        "corpus', 'serie 0220936 (7)', '4 leases so na entrega'...) — "
        "grupos cobrindo as 67, sem excecao silenciosa.\n\n"
        "8. CLAIMS PRONTOS PARA DDR (`propor_claims_ddr`): para os claims "
        "que alimentarao o DDR, celulas/abas candidatas (fichas "
        "ddr-template-structure-* ajudam) e limitacoes. NAO escreva no "
        "workbook.\n\n"
        "Leituras novas: SOMENTE para a data de corte e o item 3 (e o "
        "estritamente necessario). O orcamento e curto e o cache e seu "
        "aliado. Ao final, resuma o que ficou aberto.",
    ])


# --- execução ---------------------------------------------------------------

def executar_sessao(*, repo: Any, unit: dict[str, Any], pasta: Path,
                    client: Any = None, max_cost_usd: float) -> Any:
    from src.examinador.cache import PageCache
    from src.examinador.okf import KnowledgeBase

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

    # 1) lote: transcrição independente do Exhibit A (p.3 e p.4 da DPU).
    leases = repo.claims_da_unit(unit["id"], "lease_in_unit")
    dpu_nome = next((n for n in acervo.names()
                     if "unit dec" in n and "rec" in n), None)
    ja = {v["claim_id"] for v in repo.verificacoes(unit["id"])}
    pendentes_lote = [c for c in leases if c["id"] not in ja]
    if dpu_nome and pendentes_lote:
        pngs = [p for p in (_png(dpu_nome, 3), _png(dpu_nome, 4)) if p]
        if pngs:
            resumo["lote_exhibit_a"] = verificador.verificar_lote_exhibit_a(
                repo=repo, unit=unit, claims_lease=pendentes_lote,
                pngs=pngs, chamar=chamar, custo=cust)

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
        if ev == "texto" and nome_ev:
            try:
                got = acervo.read_page(nome_ev, claim["page"].split(",")[0]
                                       .strip() or 1, "texto")
                texto_ev = got.get("text", "")
            except Exception:
                texto_ev = ""
        elif nome_ev:
            png_ev = _png(nome_ev, _pagina_int(claim["page"]))
        if not texto_ev and png_ev is None:
            repo.registrar_verificacao(
                claim["id"], pergunta, "nao_verificavel",
                verificador.modelo_b(), {},
                {"motivo": "evidencia nao renderizavel"}, 0.0, None)
            continue
        got = verificador.verificar_pergunta(
            repo=repo, claim=claim, pergunta=pergunta,
            campo_do_claim=campo, evidencia_texto=texto_ev,
            evidencia_png=png_ev, chamar=chamar, custo=cust)
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
