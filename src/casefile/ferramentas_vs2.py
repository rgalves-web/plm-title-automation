"""Ferramentas adicionais da sessão de exame dirigido (VS2).

Além das de leitura/claims do VS1: julgar a busca negativa (veredito do
modelo sobre hits), pedir intervenção do operador (só para o que as
pesquisas autorizadas não resolvem), e emitir os itens estruturados de
coleta do cartório (o modelo decide O QUE buscar; a caneta executa).
"""
from __future__ import annotations

from typing import Any, Callable

FERRAMENTAS_VS2: list[dict[str, Any]] = [
    {
        "name": "julgar_busca",
        "description": (
            "Veredito sobre uma busca registrada (os hits estao no task): "
            "`nao_encontrado` quando nenhum hit e o documento procurado, "
            "`encontrado` quando um hit E o documento (registre tambem o "
            "claim document_present correspondente). Justificativa de UMA "
            "frase por decisao."),
        "input_schema": {"type": "object", "properties": {
            "busca_id": {"type": "integer"},
            "veredito": {"type": "string",
                         "enum": ["nao_encontrado", "encontrado"]},
            "justificativa": {"type": "string"}},
            "required": ["busca_id", "veredito", "justificativa"]},
    },
    {
        "name": "pedir_intervencao",
        "description": (
            "Encaminha ao operador SOMENTE o que permanece ambiguo depois "
            "das leituras e pesquisas autorizadas, ou o que exige compra "
            "acima do teto/autenticacao. Vira pergunta aberta que TRAVA o "
            "gate da condicao correspondente ate resposta."),
        "input_schema": {"type": "object", "properties": {
            "assunto": {"type": "string",
                        "description": "ex. 'bra-de', 'serie 0220936'"},
            "pergunta": {"type": "string"},
            "claim_id": {"type": "integer"}},
            "required": ["assunto", "pergunta"]},
    },
    {
        "name": "emitir_itens_cartorio",
        "description": (
            "Emite os itens de coleta do cartorio (CourthouseDirect), um por "
            "instrumento, com referencia deterministica. `arquivo_alvo` no "
            "padrao book.page.pdf. Reemitir um titulo existente nao duplica."),
        "input_schema": {"type": "object", "properties": {
            "itens": {"type": "array", "items": {
                "type": "object", "properties": {
                    "book": {"type": "string"},
                    "page": {"type": "string"},
                    "condado": {"type": "string"},
                    "instrumento": {"type": "string"},
                    "grantor": {"type": "string"},
                    "arquivo_alvo": {"type": "string"},
                    "motivo": {"type": "string"},
                    "research_item_id": {"type": "integer"}},
                "required": ["book", "page", "condado", "instrumento",
                             "arquivo_alvo", "motivo"]}}},
            "required": ["itens"]},
    },
    {
        "name": "propor_recomendacao",
        "description": (
            "Fecha o exame dirigido com a recomendacao fundamentada para o "
            "proximo estado da unit (ex.: seguir para EXAMINANDO; aguardar "
            "PM/seller; nova rodada de coleta) — sera embutida no "
            "RELATORIO_COLETA_VS2_v1.md. Nenhuma certificacao de WI/NRI."),
        "input_schema": {"type": "object", "properties": {
            "recomendacao_markdown": {"type": "string"}},
            "required": ["recomendacao_markdown"]},
    },
]


def montar_dispatch_vs2(*, base: dict[str, Callable], repo: Any,
                        unit: dict[str, Any], pasta: Any,
                        session_ref: dict[str, Any]) -> dict[str, Callable]:
    from src.casefile import caneta

    def _julgar_busca(busca_id: int, veredito: str,
                      justificativa: str) -> dict[str, Any]:
        minhas = {b["id"] for b in repo.buscas(unit["id"])}
        if busca_id not in minhas:
            raise ValueError(f"busca {busca_id} nao e desta unit")
        repo.julgar_busca(busca_id, veredito, justificativa,
                          session_ref["id"])
        return {"busca": busca_id, "resultado": veredito}

    def _pedir_intervencao(assunto: str, pergunta: str,
                           claim_id: int | None = None) -> dict[str, Any]:
        if claim_id is not None and \
                not repo.claim_existe(unit["id"], claim_id):
            raise ValueError(f"claim {claim_id} nao e desta unit")
        pid = repo.registrar_pergunta_vs2(
            unit["id"], f"[{assunto}] {pergunta}", claim_id)
        return {"pergunta": pid,
                "nota": "gate da condicao correspondente fica pendente ate "
                        "o operador responder"}

    def _emitir_itens(itens: list[dict[str, Any]]) -> dict[str, Any]:
        aceitos, rejeitados = [], []
        for i, item in enumerate(itens):
            vazios = [c for c in ("book", "page", "condado", "instrumento",
                                  "arquivo_alvo", "motivo")
                      if not str(item.get(c) or "").strip()]
            if vazios:
                rejeitados.append({"indice": i,
                                   "erro": f"campos vazios: {vazios}"})
                continue
            cid = repo.criar_collection_item(
                unit["id"],
                title=str(item["arquivo_alvo"]).strip(),
                method="courthousedirect",
                target={k: str(item.get(k, "")).strip()
                        for k in ("book", "page", "condado", "instrumento",
                                  "grantor", "arquivo_alvo", "motivo")},
                research_item_id=item.get("research_item_id"))
            aceitos.append(cid)
        return {"aceitos": len(aceitos), "ids": aceitos,
                "rejeitados": rejeitados}

    def _propor_recomendacao(recomendacao_markdown: str) -> dict[str, Any]:
        if not recomendacao_markdown.strip():
            raise ValueError("recomendacao vazia")
        path = caneta.escrever_texto(
            caneta.caminho(pasta) / "RECOMENDACAO_VS2.md",
            recomendacao_markdown)
        return {"gravada_em": str(path)}

    got = dict(base)
    got.update({"julgar_busca": _julgar_busca,
                "pedir_intervencao": _pedir_intervencao,
                "emitir_itens_cartorio": _emitir_itens,
                "propor_recomendacao": _propor_recomendacao})
    return got
