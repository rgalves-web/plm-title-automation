"""O exame dirigido do VS2 — as leituras que a aprovação exige, com gates.

O modelo lê EXATAMENTE o que o operador mandou ler (condições 1, 3, 5, 6),
julga os hits da busca negativa (condição 4), e transforma as pesquisas do
plano em itens estruturados de cartório (condição 2 executada pela caneta).
Do XREF ele recebe SOMENTE as linhas recuperadas pelo índice local — nunca
janelas. Toda afirmação nova é claim com documento, página e trecho; as
formas de valor exigidas pelos gates estão declaradas no task.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.casefile import ferramentas, ferramentas_vs2, sessao

SISTEMA_EXAME = """Voce e o landman desta unidade executando a COLETA SOB
CONDICOES aprovada pelo operador. Nesta sessao voce NAO monta plano nem
preenche DDR: executa as LEITURAS DIRIGIDAS que a aprovacao exige e registra
cada achado como claim com citacao literal (documento, pagina, trecho).

Regras desta sessao:
1. Leia por inteiro o que o task manda ler. Texto antes de imagem; pixels so
   quando indispensavel.
2. Cada leitura vira claims. Os gates do caso conferem FORMAS especificas de
   valor (declaradas no task) — sem elas a unit nao avanca.
3. Do XREF voce recebe as linhas ja recuperadas pelo indice local. NAO peca
   janelas de XREF; interprete o que foi recuperado.
4. Divergencia nova vira claim divergence. Ambiguidade que sobreviver as
   leituras vira pedir_intervencao — nunca escolha em silencio.
5. NENHUMA certificacao de WI/NRI nesta etapa.
6. Feche com propor_recomendacao — o proximo estado, fundamentado.

Branco declarado e melhor que numero plausivel."""


def executar(*, repo: Any, unit: dict[str, Any], pasta: Path, acervo: Any,
             kb_unidade: Any, kb_global: Any, client: Any = None,
             max_cost_usd: float) -> Any:
    session_ref: dict[str, Any] = {"id": None}
    base = ferramentas.montar_dispatch(
        acervo=acervo, repo=repo, unit=unit, pasta=pasta,
        kb_unidade=kb_unidade, kb_global=kb_global,
        ator=f"modelo:{sessao.modelo()}", session_ref=session_ref)
    dispatch = ferramentas_vs2.montar_dispatch_vs2(
        base=base, repo=repo, unit=unit, pasta=pasta,
        session_ref=session_ref)
    tools = (ferramentas.FERRAMENTAS_LEITURA + ferramentas.FERRAMENTAS_ESCRITA
             + ferramentas_vs2.FERRAMENTAS_VS2)
    task = _task(repo, unit, acervo)
    log, _sid = sessao.rodar(
        repo=repo, unit=unit, pasta=pasta, comando="coletar.exame",
        sistema=SISTEMA_EXAME, task=task, ferramentas=tools,
        dispatch=dispatch, modelo_sessao=sessao.modelo(),
        max_cost_usd=max_cost_usd, client=client, session_ref=session_ref)
    return log


def _nomes(acervo: Any, *pedacos: str) -> list[str]:
    baixo = [p.lower() for p in pedacos]
    return [n for n in acervo.names() if all(p in n for p in baixo)][:20]


def _task(repo: Any, unit: dict[str, Any], acervo: Any) -> str:
    uid = unit["id"]

    # As linhas recuperadas do XREF/Schedule — SOMENTE elas (condição 2).
    linhas = repo.xref_rows_da_unit(uid)
    compactas = []
    for r in linhas[:220]:
        v = r["row"]
        compactas.append(
            f"- [{r['sheet']}:{r['row_number']}] "
            f"{v.get('LEASE NO', '?')} | {v.get('LESSOR', '')[:34]} | "
            f"{v.get('RECORD TYPE', '')} | {v.get('PROPERTY STATUS', '')} | "
            f"EXP {v.get('EXP DATE', '')[:10]} | EXT "
            f"{v.get('EXT EXP DATE', '')[:10]} | "
            f"{v.get('WELL OR CONTRACT NB', '')} "
            f"{v.get('WELL OR CONTRACT NAME', '')[:26]} | chaves: "
            f"{','.join(r['matched_keys'][:2])}")

    buscas = repo.buscas(uid, "DOTO/DOI")
    bloco_busca = ""
    if buscas and buscas[-1]["result"] == "pendente_julgamento":
        b = buscas[-1]
        hits = "\n".join(f"  - [{h['escopo']}] {h['termo']} -> {h['onde']}"
                         for h in b["hits"][:60])
        bloco_busca = (
            f"BUSCA DOTO/DOI id={b['id']} — escopo: {b['scope']}\n"
            f"HITS PARA JULGAR (e ou nao um DOTO/DOI?):\n{hits}\n"
            f"Use `julgar_busca` (id {b['id']}). Se ENCONTRADO, registre "
            f"tambem claim document_present. Se NAO, a solicitacao ao "
            f"PM/seller ja vai por pesquisa (registrar_pesquisas, onde = "
            f"'PM/seller — Drive do projeto').")

    pesquisas = repo.pesquisas(uid, "aberta")
    lista_pesq = "\n".join(
        f"- [{p['id']}] {p['title']} — {p['what'][:90]} ({p['where_'][:40]})"
        for p in pesquisas)

    partes = [
        f"UNIDADE: {unit['canonical_name']} — estado COLETANDO, exame "
        f"dirigido da aprovacao de 02/09/2026.",

        "LINHAS RECUPERADAS PELO INDICE LOCAL (XREF + Schedule — so elas; "
        "nao peca janelas):\n" + ("\n".join(compactas) or "(nenhuma)"),

        bloco_busca,

        "LEITURAS OBRIGATORIAS E A FORMA DO CLAIM QUE CADA GATE CONFERE "
        "(tipo `fact`, com citacao literal):\n\n"
        "A) TO A-669 155 ACRES — leia INTEIRO. Candidatos no acervo: "
        + str(_nomes(acervo, "t-o", "155")) + "\n"
        "   claim fact: entidade contendo 'TO A-669 155', valor com chaves "
        "`certification_date` (a data de certificacao de ownership, ou "
        "'nao_consta' com a pagina que provaria) e `amarracao` (objeto "
        "tract->cobertura, trato a trato, com paginas).\n\n"
        "B) RELEASE DE MARLEE M STEWART — candidatos: "
        + str(_nomes(acervo, "release")) + "\n"
        "   claim fact: entidade contendo 'release Marlee', valor com "
        "`natureza` (o que o instrumento e) e `efeito_no_tract_1`.\n\n"
        "C) INSTRUMENTOS BRA-DE (leases 0220953-008/-009/-010/-011 e "
        "vizinhos; candidatos: " + str(_nomes(acervo, "0220953")[:12]) + ")\n"
        "   claim fact: entidade contendo 'BRA-DE', valor com "
        "`instrumentos` (lista: instrumento, data, vol/pg quando houver) e "
        "`classificacao` (ratificacao/assignment/lease nova — PELA LINGUAGEM "
        "do documento). Cadeia BRA-DE -> EOG reconstruida ate onde o acervo "
        "permite; o que faltar de cartorio vira item em "
        "emitir_itens_cartorio. So pedir_intervencao se seguir ambiguo.\n\n"
        "D) SERIE 0220936 (7 leases; candidatos: "
        + str(_nomes(acervo, "0220936")[:10]) + ")\n"
        "   Leia as legal descriptions dos instrumentos. claim fact: "
        "entidade contendo '0220936', valor com `abrange_a669_ou_a319` "
        "('sim'|'nao'|'parcial') e `por_lease` (lease -> survey/abstract "
        "citado). A DECISAO de excluir do denominador e do operador — voce "
        "so registra o que os documentos dizem.",

        "PESQUISAS ABERTAS DO PLANO (transforme as de CARTORIO em itens "
        "estruturados via emitir_itens_cartorio, um por instrumento, "
        "book/page/condado/arquivo_alvo book.page.pdf):\n" + lista_pesq,

        "Ao final: revise se algum claim novo muda populacoes ou "
        "divergencias (registre), e feche com propor_recomendacao.",
    ]
    return "\n\n".join(p for p in partes if p)
