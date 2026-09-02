"""Busca recursiva e por conteúdo — negativa auditável antes de "ausente".

Condição 4 da aprovação: DOTO/DOI só é declarado ausente depois de busca
recursiva por NOME (árvore inteira do projeto) e por CONTEÚDO (camadas de
texto do acervo), com termos, escopo, contagens e limitações REGISTRADOS. O
que a busca não alcança (TIFs sem OCR) é declarado como não-pesquisável —
ausência aqui nunca vira prova de ausência no corpus (invariante 12).

O veredito sobre os hits (é ou não um DOTO/DOI?) é do MODELO na sessão de
exame dirigido, via `julgar_busca`. Zero hits em todos os escopos permite o
resultado automático 'nao_encontrado' — contagem, não julgamento.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

TERMOS_NOME = ("doto", "division order", "division of interest", "d.o.i")
TERMOS_TEXTO = ("division order", "doto", "division of interest",
                "4233734773", "42-337-34773", "k1402139")
MAX_HITS_POR_TERMO = 40


def busca_doto_doi(repo: Any, unit: dict[str, Any], raiz_projeto: Path,
                   acervo: Any) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []

    # Escopo 1 — nomes, árvore INTEIRA do projeto (todas as units + raiz).
    nomes_varridos = 0
    for caminho in raiz_projeto.rglob("*"):
        if not caminho.is_file():
            continue
        nomes_varridos += 1
        nome = caminho.name.lower()
        for termo in TERMOS_NOME:
            if termo in nome:
                hits.append({"escopo": "nome", "termo": termo,
                             "onde": str(caminho.relative_to(raiz_projeto))})
                break

    # Escopo 2 — conteúdo das camadas de texto do acervo da unit (sem
    # memoização de bytes: leitura descartável, documento a documento).
    nao_pesquisaveis = 0
    textos_varridos = 0
    for nome_logico in acervo.names():
        suffix = Path(nome_logico).suffix.lower()
        if suffix not in (".pdf", ".txt", ".csv", ".html", ".htm", ".md"):
            nao_pesquisaveis += 1
            continue
        try:
            dados = acervo.index.read_bytes(nome_logico)
            corpo = _texto_de(dados, suffix)
        except Exception:
            nao_pesquisaveis += 1
            continue
        if not corpo.strip():
            nao_pesquisaveis += 1
            continue
        textos_varridos += 1
        baixo = corpo.lower()
        for termo in TERMOS_TEXTO:
            if termo in baixo:
                ja = sum(1 for h in hits if h.get("termo") == termo)
                if ja < MAX_HITS_POR_TERMO:
                    hits.append({"escopo": "texto", "termo": termo,
                                 "onde": nome_logico})

    escopo = (f"nomes: arvore inteira de {raiz_projeto.name} "
              f"({nomes_varridos} arquivos); conteudo: camadas de texto do "
              f"acervo da unit ({textos_varridos} pesquisaveis, "
              f"{nao_pesquisaveis} NAO pesquisaveis sem OCR — ausencia nao "
              f"provada para estes)")
    resultado = "nao_encontrado" if not hits else "pendente_julgamento"
    busca_id = repo.registrar_busca(
        unit["id"], "DOTO/DOI", list(TERMOS_NOME + TERMOS_TEXTO), escopo,
        nomes_varridos, hits, result=resultado)
    return {"busca_id": busca_id, "hits": len(hits),
            "nomes_varridos": nomes_varridos,
            "textos_varridos": textos_varridos,
            "nao_pesquisaveis": nao_pesquisaveis, "resultado": resultado}


def _texto_de(dados: bytes, suffix: str) -> str:
    if suffix != ".pdf":
        return dados.decode("utf-8", errors="replace")
    import fitz
    partes = []
    with fitz.open(stream=dados, filetype="pdf") as doc:
        for pagina in doc:
            partes.append(pagina.get_text())
    return "\n".join(partes)
