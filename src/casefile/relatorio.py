"""RELATORIO_COLETA_VS2 — montado do banco, seção a seção, com custos
separados (portal × IA), deltas de censo e o status verificável das seis
condições. A recomendação de próximo estado é a do modelo
(RECOMENDACAO_VS2.md, escrita na sessão de exame); tudo o mais é contagem.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.casefile import caneta, gates


def gerar(repo: Any, unit: dict[str, Any], pasta: Path,
          resumo_fases: dict[str, Any]) -> Path:
    uid = unit["id"]
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    versao = 1 + len(repo.deliverables(uid, "relatorio_coleta_vs2"))

    md: list[str] = [
        f"# RELATORIO DE COLETA VS2 — {unit['canonical_name']} (v{versao})",
        f"_gerado em {agora} · estado da unit: "
        f"{repo.estado_da_unit(uid)}_", ""]

    # 1. pesquisas realizadas -------------------------------------------------
    md.append("## 1. Pesquisas realizadas")
    lookups = repo.xref_lookups(uid)
    com = sum(1 for x in lookups if x["rows_found"] > 0)
    md.append(f"- **Indice local XREF/Schedule**: {len(lookups)} chaves "
              f"pesquisadas ({com} com linhas, {len(lookups) - com} sem), "
              f"{len(repo.xref_rows_da_unit(uid))} linhas recuperadas — "
              f"nenhuma janela enviada ao modelo.")
    for b in repo.buscas(uid):
        md.append(f"- **Busca {b['target']}** (id {b['id']}): "
                  f"{b['result']} — {b['scope'][:180]}")
    md.append("")

    # 2. resultados negativos com auditoria ----------------------------------
    md.append("## 2. Resultados negativos auditáveis")
    negativos = [b for b in repo.buscas(uid) if b["result"] ==
                 "nao_encontrado"]
    if negativos:
        for b in negativos:
            md.append(f"- {b['target']}: termos {b['terms']}; "
                      f"{b['names_scanned']} nomes varridos; veredito: "
                      f"{b['evidence'] or 'zero hits em todos os escopos'}")
    else:
        md.append("- (nenhum)")
    chaves_sem = sorted(f"{x['key_kind']}:{x['key_value']}"
                        for x in lookups if x["rows_found"] == 0)
    if chaves_sem:
        md.append(f"- Chaves sem linha no indice ({len(chaves_sem)}): "
                  + ", ".join(chaves_sem[:12])
                  + (" …" if len(chaves_sem) > 12 else ""))
    md.append("")

    # 3. documentos adquiridos ------------------------------------------------
    md.append("## 3. Documentos adquiridos")
    itens = repo.collection_items(uid)
    por_status: dict[str, list[str]] = {}
    for i in itens:
        por_status.setdefault(i["status"], []).append(i["title"])
    if itens:
        for status in ("promovido", "validado", "staged", "falhou",
                       "requer_intervencao", "pendente"):
            if status in por_status:
                md.append(f"- {status}: {len(por_status[status])} — "
                          + ", ".join(por_status[status][:10]))
    else:
        md.append("- (nenhum item de coleta criado)")
    md.append("")

    # 4. custos ---------------------------------------------------------------
    custos = repo.custo_por_categoria(uid)
    md.append("## 4. Custos")
    md.append(f"- Portal (aberturas/coleta): "
              f"${custos.get('coleta', 0.0):.2f}")
    md.append(f"- IA (modelo): ${custos.get('modelo', 0.0):.2f}")
    md.append(f"- Total da unit: ${repo.custo_acumulado(uid):.2f}")
    md.append("")

    # 5. populações e alterações no censo ------------------------------------
    md.append("## 5. Populações (denominador preservado)")
    for pop, n in sorted(repo.populacoes_contagens(uid).items()):
        md.append(f"- {pop}: {n}")
    deltas = resumo_fases.get("populacoes", {})
    if deltas.get("dpu_sem_linha_no_xref"):
        md.append(f"- DPU sem linha no XREF "
                  f"({len(deltas['dpu_sem_linha_no_xref'])}): "
                  + ", ".join(deltas["dpu_sem_linha_no_xref"]))
    if deltas.get("xref_fora_da_dpu"):
        md.append(f"- XREF fora da DPU ({len(deltas['xref_fora_da_dpu'])}): "
                  + ", ".join(deltas["xref_fora_da_dpu"]))
    md.append("")

    # 6. divergências ---------------------------------------------------------
    md.append("## 6. Divergências")
    divergencias = repo.claims_da_unit(uid, "divergence")
    facts = repo.claims_da_unit(uid, "fact")
    md.append(f"- Remanescentes (claims divergence ativos): "
              f"{len(divergencias)}")
    md.append(f"- Fatos de leitura registrados nesta fase (claims fact): "
              f"{len(facts)}")
    for c in facts:
        md.append(f"  - [{c['id']}] {c['entity'][:90]}")
    md.append("")

    # 7. status das seis condições -------------------------------------------
    md.append("## 7. Status das seis condições (gates verificáveis)")
    todas = gates.avaliar(repo, unit)
    for g in todas:
        md.append(f"- **{g['condicao']}**: {gates.ROTULOS[g['status']]} — "
                  f"{g['detalhe']}")
    md.append("")

    # 8. dependentes de PM/seller e intervenções ------------------------------
    md.append("## 8. Dependentes de PM/seller e intervenções")
    pendencias = False
    for p in repo.pesquisas(uid, "aberta"):
        if "pm" in p["where_"].lower() or "seller" in p["where_"].lower():
            md.append(f"- pesquisa [{p['id']}] {p['title']}")
            pendencias = True
    for i in itens:
        if i["status"] == "requer_intervencao":
            md.append(f"- coleta [{i['id']}] {i['title']}: {i['note'][:140]}")
            pendencias = True
    for q in repo.perguntas_vs2_abertas(uid):
        md.append(f"- pergunta [{q['id']}] {q['question'][:140]}")
        pendencias = True
    if not pendencias:
        md.append("- (nenhuma)")
    md.append("")

    # 9. recomendação do modelo ----------------------------------------------
    md.append("## 9. Recomendação para o próximo estado")
    rec = caneta.caminho(pasta) / "RECOMENDACAO_VS2.md"
    if rec.exists():
        md.append(rec.read_text(encoding="utf-8").strip())
    else:
        md.append("(a sessão de exame ainda não propôs recomendação)")
    md.append("")
    md.append("_Nenhuma certificação de WI/NRI foi feita nesta etapa._")

    texto = "\n".join(md) + "\n"
    path = caneta.escrever_texto(
        caneta.caminho(pasta) / f"RELATORIO_COLETA_VS2_v{versao}.md", texto)
    sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    repo.registrar_deliverable(uid, "relatorio_coleta_vs2", versao,
                               str(path), sha)
    return path
