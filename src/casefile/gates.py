"""Os gates das seis condições da aprovação — verificáveis, nunca julgamento.

Cada gate confere a EXISTÊNCIA do artefato que a condição exige (populações
persistidas, lookups cobrindo as chaves, claims de leitura com as chaves de
valor combinadas, busca negativa julgada, solicitação emitida) — jamais se o
conteúdo está certo. `avancar` (evento coleta_concluida) recusa enquanto
houver gate pendente.

Semântica corrigida pelo operador em 02/09 (determinação 2): tentativa
executada NÃO é evidência. Um claim de leitura só fecha o gate quando declara
`leitura_completa: true`; leitura declarada impossível é `pendente_evidencia`
(bloqueia). `ok_parcial` marca gate satisfeito com ressalva declarada (não
bloqueia, mas aparece): a amarração do TO 155ac fica parcial enquanto a
diferença 155 gross × 80,02 unit acres não estiver explicada
(`diferenca_gross_explicada`), e a população fica parcial enquanto a decisão
da série 0220936 aguarda a /006 e o operador.
"""
from __future__ import annotations

from typing import Any

from src.casefile.xref_local import normalizar_lease

OK = "ok"
OK_PARCIAL = "ok_parcial"
PENDENTE = "pendente"
PENDENTE_OPERADOR = "pendente_operador"
PENDENTE_EVIDENCIA = "pendente_evidencia"

BLOQUEIAM = (PENDENTE, PENDENTE_OPERADOR, PENDENTE_EVIDENCIA)

ROTULOS = {OK: "OK", OK_PARCIAL: "OK-PARCIAL", PENDENTE: "PENDENTE",
           PENDENTE_OPERADOR: "PENDENTE(operador)",
           PENDENTE_EVIDENCIA: "PENDENTE(evidencia)"}


def avaliar(repo: Any, unit: dict[str, Any]) -> list[dict[str, str]]:
    uid = unit["id"]
    facts = repo.claims_da_unit(uid, "fact")
    return [
        _g1_populacao(repo, uid, facts),
        _g2_xref(repo, uid),
        _g3_bra_de(repo, uid, facts),
        _g4_doto_doi(repo, uid),
        _g5_to_155(repo, uid, facts),
        _g6_release(repo, uid, facts),
    ]


def pendentes(repo: Any, unit: dict[str, Any]) -> list[dict[str, str]]:
    return [g for g in avaliar(repo, unit) if g["status"] in BLOQUEIAM]


def _gate(slug: str, status: str, detalhe: str) -> dict[str, str]:
    return {"condicao": slug, "status": status, "detalhe": detalhe}


def _facts_de(facts: list[dict[str, Any]], no_entity: str,
              chaves_valor: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    alvo = no_entity.lower()
    return [c for c in facts
            if alvo in c["entity"].lower()
            and all(k in c["value"] for k in chaves_valor)]


def _tem_fact(facts: list[dict[str, Any]], no_entity: str,
              chaves_valor: tuple[str, ...] = ()) -> dict[str, Any] | None:
    # Vários facts podem casar (uma leitura falhada e uma completa): o que
    # decide o gate é o MELHOR qualificado, nunca o primeiro da lista.
    candidatos = _facts_de(facts, no_entity, chaves_valor)
    if not candidatos:
        return None
    completos = [c for c in candidatos
                 if c["value"].get("leitura_completa")]
    return (completos or candidatos)[-1]


def _pergunta_aberta(repo: Any, uid: int, assunto: str) -> bool:
    return bool(repo.perguntas_vs2_abertas(uid, assunto))


def _g1_populacao(repo: Any, uid: int,
                  facts: list[dict[str, Any]]) -> dict[str, str]:
    n = repo.populacoes_contagens(uid)
    dpu = n.get("dpu_exhibit_a", 0)
    oper = n.get("operacional", 0)
    ooc = n.get("candidate_out_of_scope", 0)
    if dpu == 0:
        return _gate("populacao-exhibit-a", PENDENTE,
                     "populacoes ainda nao persistidas")
    if oper != dpu:
        return _gate("populacao-exhibit-a", PENDENTE_OPERADOR,
                     f"operacional ({oper}) difere da DPU ({dpu}) sem "
                     f"decisao do operador registrada")
    zero = n.get("in_dpu_but_zero_unit_acres", 0)
    if zero:
        return _gate("populacao-exhibit-a", OK,
                     f"DPU={dpu} intacta; {zero} lease(s) classificadas "
                     f"in_dpu_but_zero_unit_acres por leitura declarada "
                     f"(determinacao 5) — presenca no Exhibit A preservada")
    leitura = _tem_fact(facts, "0220936")
    if leitura is None:
        return _gate("populacao-exhibit-a", PENDENTE,
                     f"DPU={dpu}, out_of_scope={ooc}; falta a LEITURA das "
                     f"legal descriptions da serie 0220936 (claim fact)")
    if _pergunta_aberta(repo, uid, "0220936") or \
            not leitura["value"].get("leitura_completa"):
        return _gate("populacao-exhibit-a", OK_PARCIAL,
                     f"DPU={dpu} intacta; out_of_scope={ooc}; serie 0220936 "
                     f"segue candidata ate a leitura da /006 e a decisao do "
                     f"operador (claim {leitura['id']})")
    return _gate("populacao-exhibit-a", OK,
                 f"DPU={dpu} intacta; out_of_scope={ooc}; leitura da serie "
                 f"registrada (claim {leitura['id']})")


def _g2_xref(repo: Any, uid: int) -> dict[str, str]:
    lookups = repo.xref_lookups(uid)
    if not lookups:
        return _gate("xref-indexacao-local", PENDENTE,
                     "nenhum lookup registrado")
    kinds = {}
    for lk in lookups:
        kinds.setdefault(lk["key_kind"], set()).add(lk["key_value"])
    dpu = {m["member"] for m in repo.populacao(uid, "dpu_exhibit_a")}
    leases_ok = {normalizar_lease(v) for v in kinds.get("lease_no", set())}
    faltam = sorted(dpu - leases_ok)
    problemas = []
    if "contract" not in kinds:
        problemas.append("sem lookup do contrato K…")
    if "unit_name" not in kinds:
        problemas.append("sem lookup por nome da unit")
    if faltam:
        problemas.append(f"{len(faltam)} lease(s) da DPU sem lookup: "
                         f"{faltam[:4]}…")
    if "recording" not in kinds:
        problemas.append("sem lookups de recording (Schedule)")
    if problemas:
        return _gate("xref-indexacao-local", PENDENTE, "; ".join(problemas))
    total_linhas = len(repo.xref_rows_da_unit(uid))
    return _gate("xref-indexacao-local", OK,
                 f"{len(lookups)} chaves pesquisadas, {total_linhas} linhas "
                 f"recuperadas (so elas vao ao modelo)")


def _g3_bra_de(repo: Any, uid: int,
               facts: list[dict[str, Any]]) -> dict[str, str]:
    leitura = _tem_fact(facts, "bra-de")
    if leitura is not None:
        return _gate("cadeia-bra-de", OK,
                     f"classificacao por leitura registrada "
                     f"(claim {leitura['id']})")
    if _pergunta_aberta(repo, uid, "bra-de"):
        return _gate("cadeia-bra-de", PENDENTE_OPERADOR,
                     "ambiguidade encaminhada — aguarda resposta do operador")
    return _gate("cadeia-bra-de", PENDENTE,
                 "instrumentos BRA-DE ainda nao lidos/classificados")


def _g4_doto_doi(repo: Any, uid: int) -> dict[str, str]:
    buscas = repo.buscas(uid, "DOTO/DOI")
    if not buscas:
        return _gate("doto-doi-busca-negativa", PENDENTE,
                     "busca ainda nao executada")
    ultima = buscas[-1]
    if ultima["result"] == "pendente_julgamento":
        return _gate("doto-doi-busca-negativa", PENDENTE,
                     f"busca {ultima['id']} com hits aguardando julgamento "
                     f"do modelo (julgar_busca)")
    if ultima["result"] == "encontrado":
        achado = repo.claims_da_unit(uid, "document_present")
        tem = any("doto" in c["entity"].lower() or
                  "doi" in c["entity"].lower() for c in achado)
        return _gate("doto-doi-busca-negativa", OK if tem else PENDENTE,
                     "DOTO/DOI ENCONTRADO" +
                     ("" if tem else " — falta claim document_present"))
    solicitacoes = [p for p in repo.pesquisas(uid)
                    if "doto" in (p["title"] + p["what"]).lower()
                    or "doi" in (p["title"] + p["what"]).lower()]
    if not solicitacoes:
        return _gate("doto-doi-busca-negativa", PENDENTE,
                     "busca negativa registrada, mas falta a solicitacao ao "
                     "PM/seller (research_item)")
    return _gate("doto-doi-busca-negativa", OK,
                 f"busca negativa {ultima['id']} auditavel + solicitacao ao "
                 f"PM/seller (pesquisa {solicitacoes[0]['id']}); WI/NRI "
                 f"segue NAO verificado")


def _g5_to_155(repo: Any, uid: int,
               facts: list[dict[str, Any]]) -> dict[str, str]:
    c = _tem_fact(facts, "155", ("certification_date",))
    if c is None:
        return _gate("to-155ac-certificacao-e-amarracao", PENDENTE,
                     "leitura integral do TO A-669 155ac nao registrada "
                     "(fact com chave certification_date)")
    if "amarracao" not in c["value"] and \
            _tem_fact(facts, "amarracao") is None:
        return _gate("to-155ac-certificacao-e-amarracao", PENDENTE,
                     f"cert date registrada (claim {c['id']}), falta a "
                     f"amarracao trato-a-trato")
    explicada = c["value"].get("diferenca_gross_explicada") or \
        (_tem_fact(facts, "155", ("diferenca_gross_explicada",)) or {}
         ).get("value", {}).get("diferenca_gross_explicada")
    if not explicada:
        return _gate("to-155ac-certificacao-e-amarracao", OK_PARCIAL,
                     f"cert date registrada (claim {c['id']}); amarracao "
                     f"PARCIAL/confianca media — 155 ac gross x 80,02 ac do "
                     f"Tract 2 sem explicacao (determinacao 2 do operador)")
    return _gate("to-155ac-certificacao-e-amarracao", OK,
                 f"cert date + amarracao registradas e diferenca de acreagem "
                 f"explicada (claim {c['id']})")


def _g6_release(repo: Any, uid: int,
                facts: list[dict[str, Any]]) -> dict[str, str]:
    c = _tem_fact(facts, "release", ("natureza", "efeito_no_tract_1"))
    if c is None:
        return _gate("release-marlee-stewart", PENDENTE,
                     "release de Marlee M. Stewart ainda nao lido (fact com "
                     "chaves natureza e efeito_no_tract_1)")
    # Determinação 2: tentativa nao e evidencia — leitura declarada
    # impossivel bloqueia ate o documento legivel ser lido e interpretado.
    if not c["value"].get("leitura_completa"):
        return _gate("release-marlee-stewart", PENDENTE_EVIDENCIA,
                     f"claim {c['id']} declara leitura impossivel/incompleta"
                     f" — pendente ate a leitura do PDF autorizado "
                     f"('Stewart curative - EOG release of suspense') com "
                     f"leitura_completa=true")
    return _gate("release-marlee-stewart", OK,
                 f"leitura completa registrada (claim {c['id']})")
