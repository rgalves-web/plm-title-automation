"""Versioned tool contracts extracted from the frozen workbench."""
from typing import Any
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
            "vazio e diz isso — nao escala sozinho. Pedindo `ocr`/`imagem` "
            "numa pagina com camada de texto legivel, o texto volta no lugar "
            "(mais barato); se os pixels forem indispensaveis, repita com "
            "`forcar: true`."),
        "input_schema": {"type": "object", "properties": {
            "documento": {"type": "string"},
            "pagina": {"type": ["integer", "string"],
                       "description": "1-indexada. Planilhas (.xlsx): 0 lista "
                                      "as abas; N le a aba N; 'N:J' le a "
                                      "janela J (200 linhas) da aba N"},
            "modo": {"type": "string", "enum": ["texto", "ocr", "imagem"]},
            "forcar": {"type": "boolean",
                       "description": "true = quero exatamente o modo pedido, "
                                      "mesmo havendo texto"}},
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
        "name": "gravar_campos",
        "description": (
            "Grava VARIOS campos na memoria numa chamada so — mesma semantica "
            "do gravar_campo, campo a campo, cada um com valor + citacao "
            "literal + confianca proprios. Use para descarregar uma leitura "
            "que provou N campos sem gastar um turno por campo."),
        "input_schema": {"type": "object", "properties": {
            "campos": {"type": "array", "items": {
                "type": "object", "properties": {
                    "entidade": {"type": "string"},
                    "campo": {"type": "string"},
                    "valor": {"type": "string"},
                    "documento": {"type": "string"},
                    "pagina": {"type": "string"},
                    "trecho": {"type": "string"},
                    "confianca": {"type": "string",
                                  "enum": ["alta", "media", "baixa"]}},
                "required": ["entidade", "campo", "valor", "documento",
                             "pagina", "trecho", "confianca"]}}},
            "required": ["campos"]},
    },
    {
        "name": "declarar_brancos",
        "description": (
            "Declara VARIOS campos em branco com o MESMO motivo e dono — para "
            "faixas de campos que o registro nao diz pela mesma razao. Mesma "
            "semantica do declarar_branco."),
        "input_schema": {"type": "object", "properties": {
            "campos": {"type": "array", "items": {
                "type": "object", "properties": {
                    "entidade": {"type": "string"},
                    "campo": {"type": "string"}},
                "required": ["entidade", "campo"]}},
            "motivo": {"type": "string"},
            "dono": {"type": "string"}},
            "required": ["campos", "motivo", "dono"]},
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
        "name": "declarar_escopo",
        "description": (
            "H1: escreve o ESCOPO.md da unidade — o que entra em cada aba "
            "segundo o spec de submissao, a data de certificacao de CADA "
            "title opinion, e a regra 'Runsheet = instrumentos protocolados "
            "APOS a ultima certificacao'. O operador aceita com `minorh "
            "escopo aceitar` ANTES de o ship comecar. Redeclarar substitui."),
        "input_schema": {"type": "object", "properties": {
            "escopo_markdown": {"type": "string",
                                "description": "o ESCOPO.md inteiro, com as "
                                               "fontes citadas"}},
            "required": ["escopo_markdown"]},
    },
    {
        "name": "emitir_pull_list",
        "description": (
            "H2.1: emite a PULL LIST da unidade (CSV) — um item por "
            "instrumento do runsheet sem arquivo no disco, com referencia "
            "deterministica. E a mesma lista que mede a completude de "
            "Title Documents/ no fim; `minorh coletar` a executa. Reemitir "
            "substitui a lista inteira."),
        "input_schema": {"type": "object", "properties": {
            "itens": {"type": "array", "items": {
                "type": "object", "properties": {
                    "book": {"type": "string"},
                    "page": {"type": "string"},
                    "data": {"type": "string",
                             "description": "data do instrumento (a que o "
                                            "qualifica pos-certificacao)"},
                    "instrumento": {"type": "string"},
                    "grantor": {"type": "string"},
                    "arquivo_alvo": {"type": "string",
                                     "description": "ex. 1822.310.pdf"},
                    "condado": {"type": "string"}},
                "required": ["book", "page", "data", "instrumento",
                             "grantor", "arquivo_alvo", "condado"]}}},
            "required": ["itens"]},
    },
    {
        "name": "emitir_missing_files",
        "description": (
            "H4: emite as linhas do Missing Files (CSV staged para o Project "
            "Log do time). SO documento faltante; rotulo canonico primeiro "
            "(Entire Lease Folder, No Lease Folder, Not covered by Title "
            "Opinion, Title Opinion(s), Folder exists but missing lease "
            "agreement, Full Lease (Have Memo Only), Unit Designation); "
            "descricao livre so quando nenhum serve, curta e sem induzir "
            "erro. O operador cola no Project Log — append-only, nunca em "
            "linha alheia."),
        "input_schema": {"type": "object", "properties": {
            "linhas": {"type": "array", "items": {
                "type": "object", "properties": {
                    "lease": {"type": "string"},
                    "rotulo": {"type": "string"},
                    "descricao": {"type": "string"}},
                "required": ["lease", "rotulo"]}}},
            "required": ["linhas"]},
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
