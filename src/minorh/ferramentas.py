"""As ferramentas das sessões minorh — as nove da Rodada 1 mais as da operação.

A diferença para a Rodada 1: o modelo não escreve célula durante o trabalho.
Escreve MEMÓRIA (`gravar_campo`, `declarar_branco`), declara o CENSO
(`declarar_censo`) e fala com o operador por arquivo (`pedir_documento`,
`perguntar`). Célula só existe no ship, que projeta a memória.

Como sempre: schemas são contrato de forma, nunca inspeção de valor.
"""
from __future__ import annotations

from typing import Any, Callable

from src.examinador.okf import Card

_CAMPO_REF = {
    "type": "object",
    "properties": {"entidade": {"type": "string"},
                   "campo": {"type": "string"}},
    "required": ["entidade", "campo"],
}

FERRAMENTAS: list[dict[str, Any]] = [
    {
        "name": "list_documents",
        "description": (
            "Inventario do corpus da unidade (FILES/). Sem argumento, tudo; "
            "com `contains`, so os caminhos com essa substring."),
        "input_schema": {"type": "object", "properties": {
            "contains": {"type": "string"}}},
    },
    {
        "name": "read_page",
        "description": (
            "Le UMA pagina de UM documento. Modos: `texto` (camada de texto ou "
            "arquivo de texto, o mais barato), `ocr` (digitalizacoes), "
            "`imagem` (pixels, ~4x o custo). Modo que nao produz nada devolve "
            "vazio e diz isso — nao escala sozinho. A escolha e sua."),
        "input_schema": {"type": "object", "properties": {
            "documento": {"type": "string"},
            "pagina": {"type": ["integer", "string"],
                       "description": "1-indexada. Planilhas (.xlsx): 0 lista "
                                      "as abas; N le a aba N; 'N:J' le a "
                                      "janela J (200 linhas) da aba N"},
            "modo": {"type": "string", "enum": ["texto", "ocr", "imagem"]}},
            "required": ["documento", "pagina", "modo"]},
    },
    {
        "name": "search_corpus",
        "description": (
            "Onde uma string aparece: nomes de arquivo e camada de texto. "
            "Arquivos sem camada de texto sao listados como NAO pesquisados."),
        "input_schema": {"type": "object",
                         "properties": {"termo": {"type": "string"}},
                         "required": ["termo"]},
    },
    {
        "name": "read_knowledge",
        "description": (
            "Consulta as fichas: primeiro as da unidade, depois as globais "
            "(herdadas + escritas por outras unidades). Nao encontrando, "
            "devolve os nomes proximos, nunca a ficha mais parecida como se "
            "fosse a resposta."),
        "input_schema": {"type": "object",
                         "properties": {"conceito": {"type": "string"}},
                         "required": ["conceito"]},
    },
    {
        "name": "write_knowledge",
        "description": (
            "Grava uma ficha OKF. `escopo` = `unidade` para fatos desta "
            "unidade (censo, entidades, achados locais); `global` para o que "
            "vale nas outras 299 (formularios, cadeias, layouts, precedentes)."),
        "input_schema": {"type": "object", "properties": {
            "conceito": {"type": "string"},
            "ficha": {"type": "string"},
            "tipo": {"type": "string",
                     "enum": ["cadeia", "formulario", "layout", "entidade",
                              "veredito", "regra", "regra-cliente", "unidade",
                              "custo"]},
            "escopo": {"type": "string", "enum": ["unidade", "global"]},
            "fontes": {"type": "array", "items": {"type": "string"}},
            "links": {"type": "array", "items": {"type": "string"}},
            "confianca": {"type": "string"}},
            "required": ["conceito", "ficha", "tipo", "escopo"]},
    },
    {
        "name": "get_precedent",
        "description": (
            "Vereditos ja dados pelo operador (fichas globais tipo "
            "`veredito`). Sem precedente, devolve vazio — nunca inventa."),
        "input_schema": {"type": "object",
                         "properties": {"campo": {"type": "string"}},
                         "required": ["campo"]},
    },
    {
        "name": "declarar_censo",
        "description": (
            "Declara o denominador da unidade: quantos campos o entregavel "
            "exige, derivado do que o registro declara (Exhibit A, Exhibit C, "
            "pocos) vezes os campos que cada aba do template pede por linha. "
            "PRIMEIRA coisa a fazer ao abrir a unidade, antes de qualquer "
            "campo. `resumo` e a ficha: a conta inteira, em markdown, com as "
            "fontes — ela sera gravada como ficha OKF da unidade. Declarar de "
            "novo substitui (o censo BAIXA quando um documento novo muda a "
            "conta)."),
        "input_schema": {"type": "object", "properties": {
            "exige": {"type": "integer",
                      "description": "total de campos que a unidade exige"},
            "resumo": {"type": "string",
                       "description": "a conta em markdown, com fontes"}},
            "required": ["exige", "resumo"]},
    },
    {
        "name": "gravar_campo",
        "description": (
            "Grava um campo na memoria da unidade: valor + citacao literal "
            "(documento, pagina, trecho) + confianca. E daqui que o DDR sera "
            "projetado no ship — um campo sem fonte nao e trabalho de title."),
        "input_schema": {"type": "object", "properties": {
            "entidade": {"type": "string",
                         "description": 'ex. "lease 0999001-001", "tract 1", '
                                        '"poco 42-999-00001", "parecer X"'},
            "campo": {"type": "string"},
            "valor": {"type": "string"},
            "documento": {"type": "string"},
            "pagina": {"type": "string"},
            "trecho": {"type": "string"},
            "confianca": {"type": "string", "enum": ["alta", "media", "baixa"]}},
            "required": ["entidade", "campo", "valor", "documento", "pagina",
                         "trecho", "confianca"]},
    },
    {
        "name": "declarar_branco",
        "description": (
            "Deixa um campo em branco COM motivo e dono. Branco declarado e "
            "melhor que numero plausivel; motivo sem dono e buraco com nome "
            "bonito."),
        "input_schema": {"type": "object", "properties": {
            "entidade": {"type": "string"},
            "campo": {"type": "string"},
            "motivo": {"type": "string"},
            "dono": {"type": "string"}},
            "required": ["entidade", "campo", "motivo", "dono"]},
    },
    {
        "name": "pedir_documento",
        "description": (
            "Emite um item de PEDIDOS.md: um documento que falta e os campos "
            "que ele destravaria. Um item por decisao, nao por campo. Os "
            "campos listados ficam PENDENTES ate o documento chegar."),
        "input_schema": {"type": "object", "properties": {
            "titulo": {"type": "string"},
            "o_que": {"type": "string",
                      "description": "o documento, identificado como o "
                                     "registro o identifica"},
            "onde": {"type": "string",
                     "description": "onde buscar (cartorio, seller, RRC...)"},
            "metodo": {"type": "string"},
            "campos": {"type": "array", "items": _CAMPO_REF}},
            "required": ["titulo", "o_que", "onde", "metodo", "campos"]},
    },
    {
        "name": "perguntar",
        "description": (
            "Emite uma pergunta em PERGUNTAS.md para o operador. Use quando o "
            "documento nao responde e adivinhar seria pior. Diga o que "
            "desempataria, para a resposta servir de precedente."),
        "input_schema": {"type": "object", "properties": {
            "pergunta": {"type": "string"},
            "candidatos": {"type": "array", "items": {"type": "string"}},
            "o_que_desempataria": {"type": "string"}},
            "required": ["pergunta", "o_que_desempataria"]},
    },
]


def montar_dispatch(corpus: Any, kb_unidade: Any, kb_global: Any,
                    memoria: Any, estado: Any) -> dict[str, Callable]:
    """nome -> chamável. Encanamento puro, mais dois registros de contabilidade:
    toda página lida marca o documento como lido (por hash), e todo pedido
    marca seus campos como pendentes."""

    def _read_page(documento: str, pagina: Any, modo: str) -> dict[str, Any]:
        # Crua: "2:3" é aba 2 janela 3 numa planilha; o corpus interpreta.
        got = corpus.read_page(documento, pagina, modo)
        try:
            estado.marcar_lido(documento,
                               estado.hash_de(corpus.read_bytes(documento)))
        except Exception:
            pass
        return got

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
        got = kb.write(conceito, ficha, type=tipo, sources=fontes, links=links,
                       confidence=confianca)
        return {"escopo": escopo, **got}

    def _precedent(campo: str) -> dict[str, Any]:
        needle = str(campo or "").lower()
        hits = []
        for path in sorted(kb_global.root.glob("*.md")):
            if path.name in ("index.md", "log.md"):
                continue
            card = Card.from_markdown(path.read_text(encoding="utf-8"))
            if card.type == "veredito" and (
                    needle in card.concept.lower()
                    or needle in card.body.lower()):
                hits.append(card.to_dict())
        return {"campo": campo, "precedentes": hits,
                "nota": "Sem precedente registrado." if not hits else ""}

    def _declarar_censo(exige: int, resumo: str) -> dict[str, Any]:
        estado.declarar_censo(exige, resumo)
        kb_unidade.write("censo da unidade", resumo, type="unidade",
                         sources=["derivado pelo Examinador nesta sessão"],
                         confidence=f"exige {exige} campos")
        return {"censo_declarado": exige}

    def _pedir(titulo: str, o_que: str, onde: str, metodo: str,
               campos: list[dict[str, str]]) -> dict[str, Any]:
        pid = estado.novo_pedido(titulo, o_que, onde, metodo, campos)
        for ref in campos:
            memoria.pendente(str(ref.get("entidade")), str(ref.get("campo")),
                             pid)
        return {"pedido": pid, "campos_pendentes": len(campos)}

    def _perguntar(pergunta: str, o_que_desempataria: str,
                   candidatos: list[str] | None = None) -> dict[str, Any]:
        qid = estado.nova_pergunta(pergunta, list(candidatos or []),
                                   o_que_desempataria)
        return {"pergunta": qid}

    return {
        "list_documents": lambda contains="": {
            "documentos": corpus.list_documents(contains)},
        "read_page": _read_page,
        "search_corpus": lambda termo: corpus.search(termo),
        "read_knowledge": _read_knowledge,
        "write_knowledge": _write_knowledge,
        "get_precedent": _precedent,
        "declarar_censo": _declarar_censo,
        "gravar_campo": lambda entidade, campo, valor, documento, pagina,
        trecho, confianca: memoria.gravar(entidade, campo, valor, documento,
                                          pagina, trecho, confianca),
        "declarar_branco": lambda entidade, campo, motivo, dono:
            memoria.branco(entidade, campo, motivo, dono),
        "pedir_documento": _pedir,
        "perguntar": _perguntar,
    }
