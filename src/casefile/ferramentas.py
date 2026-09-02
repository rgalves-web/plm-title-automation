"""As ferramentas das sessões do casefile — leitura herdada, escrita nova.

Leitura: os schemas de `list_documents`/`read_page`/`search_corpus`/
`read_knowledge`/`write_knowledge` vêm por import de src/minorh/ferramentas.py
(leitura de lista, sem tocar o minorh), e o dispatch replica a semântica
texto-antes-de-imagem — propriedade de custo da caneta, não julgamento.

Escrita (o VS1): `registrar_claims` (validação estrutural item a item, lote
nunca derruba lote — lição G1), `registrar_pesquisas` e `propor_plano`.
Schemas são contrato de forma, nunca inspeção de valor.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from src.casefile import plano as plano_mod
from src.casefile import validacao
from src.minorh.ferramentas import FERRAMENTAS as _FERRAMENTAS_MINORH

_LEITURA = ("list_documents", "read_page", "search_corpus",
            "read_knowledge", "write_knowledge")

FERRAMENTAS_LEITURA: list[dict[str, Any]] = [
    t for t in _FERRAMENTAS_MINORH if t["name"] in _LEITURA]

FERRAMENTAS_ESCRITA: list[dict[str, Any]] = [
    {
        "name": "registrar_claims",
        "description": (
            "Registra afirmacoes estruturadas no Case File, em LOTE. Cada "
            "claim: tipo (do vocabulario ativo), entidade, valor (objeto com "
            "as chaves que o tipo exige), documento (nome logico do acervo "
            "OU sha256:<64hex>), pagina (ex. '12' ou 'aba 2, janela 41'), "
            "trecho LITERAL da evidencia, confianca, materialidade. Item "
            "invalido volta com erro nomeado sem derrubar o lote — corrija e "
            "reenvie so os rejeitados."),
        "input_schema": {"type": "object", "properties": {
            "claims": {"type": "array", "items": {
                "type": "object", "properties": {
                    "tipo": {"type": "string"},
                    "entidade": {"type": "string"},
                    "valor": {"type": "object"},
                    "documento": {"type": "string"},
                    "pagina": {"type": "string"},
                    "trecho": {"type": "string"},
                    "confianca": {"type": "string",
                                  "enum": ["alta", "media", "baixa"]},
                    "materialidade": {"type": "string",
                                      "enum": ["alta", "media", "baixa"]}},
                "required": ["tipo", "entidade", "valor", "documento",
                             "pagina", "trecho", "confianca"]}}},
            "required": ["claims"]},
    },
    {
        "name": "registrar_pesquisas",
        "description": (
            "Registra o que ainda precisa ser pesquisado — um item por "
            "decisao de busca, com onde e metodo. `claims_relacionados` liga "
            "cada pesquisa as afirmacoes que a motivam (ids devolvidos por "
            "registrar_claims). Itens do mesmo lugar recebem o MESMO texto "
            "em `onde` (sentadas de busca)."),
        "input_schema": {"type": "object", "properties": {
            "itens": {"type": "array", "items": {
                "type": "object", "properties": {
                    "titulo": {"type": "string"},
                    "o_que": {"type": "string"},
                    "onde": {"type": "string"},
                    "metodo": {"type": "string"},
                    "claims_relacionados": {"type": "array",
                                            "items": {"type": "integer"}}},
                "required": ["titulo", "o_que", "onde", "metodo"]}}},
            "required": ["itens"]},
    },
    {
        "name": "propor_plano",
        "description": (
            "Fecha o Unit Investigation Plan: o markdown completo (XREFs, "
            "TOs, tracts, sellers, documentos presentes/ausentes, pesquisas, "
            "divergencias — tudo citando claims e fontes) e o resumo com as "
            "contagens DECLARADAS. O plano vira versao nova no banco e "
            "aguarda aprovacao do operador. Redeclarar substitui a proposta "
            "anterior."),
        "input_schema": {"type": "object", "properties": {
            "plano_markdown": {"type": "string"},
            "resumo": {"type": "object", "description":
                       "contagens declaradas: leases, tracts, tos, sellers, "
                       "documentos_presentes, documentos_ausentes, "
                       "pesquisas, divergencias"}},
            "required": ["plano_markdown", "resumo"]},
    },
]


def montar_dispatch(*, acervo: Any, repo: Any, unit: dict[str, Any],
                    pasta: Path, kb_unidade: Any, kb_global: Any,
                    ator: str, session_ref: dict[str, Any]
                    ) -> dict[str, Callable]:
    """nome -> chamável. Encanamento puro; validação é de forma e identidade."""
    tipos = repo.tipos_de_claim()
    sha_por_nome = repo.sha_por_nome(unit["id"])

    def _resolver_nome(nome: str) -> list[str]:
        from src.casefile.acervo import _norm
        return sha_por_nome.get(_norm(nome), [])

    def _read_page(documento: str, pagina: Any, modo: str,
                   forcar: bool = False) -> dict[str, Any]:
        # Texto antes de imagem (semântica de src/minorh/ferramentas.py):
        # pixels custam ~4x; página com camada de texto legível volta como
        # texto, com nota, e `forcar` preserva a escolha final do modelo.
        if modo in ("ocr", "imagem") and not forcar \
                and str(documento).lower().endswith(".pdf"):
            texto = acervo.read_page(documento, pagina, "texto")
            if len(texto.get("text") or "") >= 200:
                texto["nota"] = (
                    "pagina tem camada de texto legivel — devolvido `texto` "
                    f"no lugar de `{modo}` (mais barato). Se os pixels forem "
                    "indispensaveis, repita com forcar=true.")
                return texto
        return acervo.read_page(documento, pagina, modo)

    def _read_knowledge(conceito: str) -> dict[str, Any]:
        local = kb_unidade.read(conceito)
        if local.get("encontrado"):
            return {"origem": "unidade", **local}
        alheio = kb_global.read(conceito)
        if alheio.get("encontrado"):
            return {"origem": "global", **alheio}
        return {"origem": "nenhuma", "encontrado": False,
                "conceito": conceito,
                "parecidas_na_unidade": local.get("fichas_parecidas", []),
                "parecidas_globais": alheio.get("fichas_parecidas", []),
                "todas_da_unidade": local.get("todas_as_fichas", []),
                "todas_globais": alheio.get("todas_as_fichas", [])}

    def _write_knowledge(conceito: str, ficha: str, tipo: str, escopo: str,
                         fontes: list[str] | None = None,
                         links: list[str] | None = None,
                         confianca: str = "") -> dict[str, Any]:
        kb = kb_unidade if escopo == "unidade" else kb_global
        got = kb.write(conceito, ficha, type=tipo, sources=fontes,
                       links=links, confidence=confianca)
        return {"escopo": escopo, **got}

    def _registrar_claims(claims: list[dict[str, Any]]) -> dict[str, Any]:
        aceitos: list[int] = []
        rejeitados: list[dict[str, Any]] = []
        for i, item in enumerate(claims):
            try:
                ok = validacao.validar_claim(item, tipos, _resolver_nome,
                                             repo.sha_existe)
            except validacao.ClaimInvalido as exc:
                rejeitados.append({"indice": i, "erro": str(exc)})
                continue
            # Determinação 1 do operador (02/09): evidência que existe SÓ na
            # entrega carrega a marca de contaminação de benchmark — pode
            # completar o caso, nunca contar como descoberta autônoma.
            origens = repo.origens_do_sha(ok["source_sha256"])
            if origens and origens <= {"entrega"}:
                ok["value"] = dict(ok["value"], benchmark_contamination=True,
                                   origem_evidencia="entrega")
            cid = repo.inserir_claim(
                unit_id=unit["id"], session_id=session_ref["id"], **ok)
            aceitos.append(cid)
        return {"aceitos": len(aceitos), "ids": aceitos,
                "rejeitados": rejeitados}

    def _registrar_pesquisas(itens: list[dict[str, Any]]) -> dict[str, Any]:
        aceitos: list[int] = []
        rejeitados: list[dict[str, Any]] = []
        for i, item in enumerate(itens):
            faltando = [c for c in ("titulo", "o_que", "onde", "metodo")
                        if not str(item.get(c) or "").strip()]
            if faltando:
                rejeitados.append({"indice": i,
                                   "erro": f"campos vazios: {faltando}"})
                continue
            claim_ids = [int(c) for c in item.get("claims_relacionados") or []]
            ruins = [c for c in claim_ids
                     if not repo.claim_existe(unit["id"], c)]
            if ruins:
                rejeitados.append({"indice": i,
                                   "erro": f"claims inexistentes nesta unit: "
                                           f"{ruins}"})
                continue
            rid = repo.inserir_pesquisa(
                unit["id"], item["titulo"], item["o_que"], item["onde"],
                item["metodo"], session_ref["id"], claim_ids)
            aceitos.append(rid)
        return {"aceitos": len(aceitos), "ids": aceitos,
                "rejeitados": rejeitados}

    def _propor_plano(plano_markdown: str, resumo: dict[str, Any]
                      ) -> dict[str, Any]:
        return plano_mod.propor(repo=repo, unit=unit, pasta=pasta,
                                markdown=plano_markdown, resumo=resumo,
                                session_id=session_ref["id"], ator=ator)

    return {
        "list_documents": lambda contains="": {
            "documentos": acervo.list_documents(contains)},
        "read_page": _read_page,
        "search_corpus": lambda termo: acervo.search(termo),
        "read_knowledge": _read_knowledge,
        "write_knowledge": _write_knowledge,
        "registrar_claims": _registrar_claims,
        "registrar_pesquisas": _registrar_pesquisas,
        "propor_plano": _propor_plano,
    }
