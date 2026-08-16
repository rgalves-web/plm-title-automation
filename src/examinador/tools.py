"""The nine tools, exactly as the order names them.

Schemas are contracts, not judgements: `write_cell` requires a value, a citation
(document, page, excerpt) and a confidence because a cell without a source is
not a deliverable — that is the shape of the work, and the API enforces it
before the model's text ever reaches the ledger. What the schema never does is
inspect the value.

`ask_second_opinion` is listed in the architecture as a tool the model calls
when it judges a field worth a second head. It arrives in round 2 with the
Conferente; exposing it now with nothing behind it would let the model believe
it had checked something.
"""
from __future__ import annotations

from typing import Any, Callable

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_documents",
        "description": (
            "Inventario do corpus da unidade. Sem argumento, lista tudo; com "
            "`contains`, lista os documentos cujo caminho contem essa "
            "substring. Nao ordena por relevancia — a escolha e sua."),
        "input_schema": {
            "type": "object",
            "properties": {
                "contains": {"type": "string",
                             "description": "substring do caminho, opcional"},
            },
        },
    },
    {
        "name": "read_page",
        "description": (
            "Le UMA pagina de UM documento. Modos: `texto` (camada de texto do "
            "PDF, o mais barato), `ocr` (tesseract sobre a pagina renderizada, "
            "para digitalizacoes) e `imagem` (a pagina em pixels, para os seus "
            "proprios olhos, ~4x o custo do texto). Um modo que nao produz nada "
            "devolve vazio e diz isso; nao cai sozinho para um modo mais caro. "
            "A escolha do modo e sua."),
        "input_schema": {
            "type": "object",
            "properties": {
                "documento": {"type": "string",
                              "description": "caminho como veio de list_documents"},
                "pagina": {"type": ["integer", "string"],
                           "description": "1-indexada. Planilhas (.xlsx): 0 "
                                          "lista as abas; N le a aba N; "
                                          "'N:J' le a janela J (200 linhas) "
                                          "da aba N"},
                "modo": {"type": "string", "enum": ["texto", "ocr", "imagem"]},
            },
            "required": ["documento", "pagina", "modo"],
        },
    },
    {
        "name": "search_corpus",
        "description": (
            "Onde uma string aparece: em nomes de arquivo e na camada de texto "
            "dos PDFs. Arquivos sem camada de texto sao listados como NAO "
            "pesquisados — ausencia ali nao e prova de ausencia."),
        "input_schema": {
            "type": "object",
            "properties": {"termo": {"type": "string"}},
            "required": ["termo"],
        },
    },
    {
        "name": "read_knowledge",
        "description": (
            "Consulta a base de conhecimento OKF por conceito. Serve para nao "
            "reler o que outra unidade ja leu: cadeias de cessao, formularios de "
            "lease, layouts de escritorio de parecer, vereditos do operador. "
            "Nao encontrando, devolve os nomes proximos — nunca a ficha mais "
            "parecida como se fosse a resposta."),
        "input_schema": {
            "type": "object",
            "properties": {"conceito": {"type": "string"}},
            "required": ["conceito"],
        },
    },
    {
        "name": "write_knowledge",
        "description": (
            "Grava uma ficha na base OKF para as proximas unidades. Escreva o "
            "que vale alem desta unidade — um formulario, uma cadeia de "
            "cessao, o layout de um escritorio — e nao o que so vale aqui. "
            "Cite as fontes que sustentam a ficha."),
        "input_schema": {
            "type": "object",
            "properties": {
                "conceito": {"type": "string"},
                "ficha": {"type": "string",
                          "description": "o corpo em markdown"},
                "tipo": {"type": "string",
                         "enum": ["cadeia", "formulario", "layout", "entidade",
                                  "veredito", "regra", "unidade", "custo"]},
                "fontes": {"type": "array", "items": {"type": "string"}},
                "links": {"type": "array", "items": {"type": "string"},
                          "description": "conceitos relacionados"},
                "confianca": {"type": "string"},
            },
            "required": ["conceito", "ficha", "tipo"],
        },
    },
    {
        "name": "get_precedent",
        "description": (
            "Vereditos ja dados pelo operador, como jurisprudencia. Um campo "
            "respondido uma vez serve as proximas unidades. Sem precedente, "
            "devolve vazio — nunca inventa um."),
        "input_schema": {
            "type": "object",
            "properties": {"campo": {"type": "string"}},
            "required": ["campo"],
        },
    },
    {
        "name": "write_cell",
        "description": (
            "Escreve uma celula do DDR. Exige valor, citacao (documento, "
            "pagina, trecho literal) e confianca. Nao ha verificacao automatica "
            "do valor: o que voce escrever e o que vai ao cliente."),
        "input_schema": {
            "type": "object",
            "properties": {
                "aba": {"type": "string"},
                "celula": {"type": "string", "description": 'ex. "C12"'},
                "valor": {"type": "string"},
                "documento": {"type": "string"},
                "pagina": {"type": "string"},
                "trecho": {"type": "string",
                           "description": "palavras literais da pagina"},
                "confianca": {"type": "string",
                              "enum": ["alta", "media", "baixa"]},
            },
            "required": ["aba", "celula", "valor", "documento", "pagina",
                         "trecho", "confianca"],
        },
    },
    {
        "name": "record_blank",
        "description": (
            "Deixa uma celula em branco COM motivo e dono. O dono responde "
            "'isto gera trabalho para quem?' — um motivo sem dono e um buraco "
            "com nome bonito. Branco com motivo e melhor que numero plausivel."),
        "input_schema": {
            "type": "object",
            "properties": {
                "aba": {"type": "string"},
                "celula": {"type": "string"},
                "motivo": {"type": "string"},
                "dono": {"type": "string"},
            },
            "required": ["aba", "celula", "motivo", "dono"],
        },
    },
    {
        "name": "flag_for_human",
        "description": (
            "Pergunta ao operador. Use quando o documento nao responde e "
            "adivinhar seria pior que perguntar. Diga o que desempataria — "
            "qual documento, qual fato — para a resposta servir de precedente."),
        "input_schema": {
            "type": "object",
            "properties": {
                "pergunta": {"type": "string"},
                "candidatos": {"type": "array", "items": {"type": "string"}},
                "o_que_desempataria": {"type": "string"},
            },
            "required": ["pergunta", "o_que_desempataria"],
        },
    },
]


def build_dispatch(corpus: Any, kb: Any, ledger: Any) -> dict[str, Callable]:
    """name -> callable. Pure plumbing: unpack arguments, call, hand back."""

    def _precedent(campo: str) -> dict[str, Any]:
        # Verdicts are OKF cards of type `veredito`. A miss is a miss.
        needle = str(campo or "").lower()
        hits = []
        for path in sorted(kb.root.glob("*.md")):
            if path.name in ("index.md", "log.md"):
                continue
            from src.examinador.okf import Card
            card = Card.from_markdown(path.read_text(encoding="utf-8"))
            if card.type == "veredito" and (
                    needle in card.concept.lower() or needle in card.body.lower()):
                hits.append(card.to_dict())
        return {"campo": campo, "precedentes": hits,
                "nota": ("Sem precedente registrado."
                         if not hits else "")}

    return {
        "list_documents": lambda contains="": {
            "documentos": corpus.list_documents(contains),
        },
        # A página vai crua: "2:3" é aba 2 janela 3 numa planilha, e quem sabe
        # interpretar é o corpus — um int() aqui quebraria a convenção.
        "read_page": lambda documento, pagina, modo: corpus.read_page(
            documento, pagina, modo),
        "search_corpus": lambda termo: corpus.search(termo),
        "read_knowledge": lambda conceito: kb.read(conceito),
        "write_knowledge": lambda conceito, ficha, tipo, fontes=None,
        links=None, confianca="": kb.write(
            conceito, ficha, type=tipo, sources=fontes, links=links,
            confidence=confianca),
        "get_precedent": _precedent,
        "write_cell": lambda aba, celula, valor, documento, pagina, trecho,
        confianca: ledger.write_cell(aba, celula, valor, documento, pagina,
                                     trecho, confianca),
        "record_blank": lambda aba, celula, motivo, dono: ledger.record_blank(
            aba, celula, motivo, dono),
        "flag_for_human": lambda pergunta, o_que_desempataria, candidatos=None:
            ledger.flag_for_human(pergunta, candidatos, o_que_desempataria),
    }
