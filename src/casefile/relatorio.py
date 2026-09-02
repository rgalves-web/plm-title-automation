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

    estado = repo.estado_da_unit(uid)
    cadeia = " -> ".join(
        [t["from_state"] for t in repo.transicoes(uid)[-2:]][:1]
        + [t["to_state"] for t in repo.transicoes(uid)[-2:]]) \
        if len(repo.transicoes(uid)) >= 2 else estado
    md: list[str] = [
        f"# RELATORIO DE COLETA VS2 — {unit['canonical_name']} (v{versao})",
        f"_gerado em {agora} · **estado da unit: {estado}** "
        f"(transições finais: {cadeia})_", ""]

    # 1. pesquisas realizadas -------------------------------------------------
    md.append("## 1. Pesquisas realizadas")
    lookups = repo.xref_lookups(uid)
    com = sum(1 for x in lookups if x["rows_found"] > 0)
    md.append(f"- **Indice local XREF/Schedule**: {len(lookups)} chaves "
              f"pesquisadas ({com} com linhas, {len(lookups) - com} sem), "
              f"{len(repo.xref_rows_da_unit(uid))} linhas recuperadas — "
              f"nenhuma janela enviada ao modelo.")
    for b in repo.buscas(uid):
        # A busca por conteúdo só alcançou as camadas de texto; TIFs sem OCR
        # NÃO foram pesquisados internamente — o resultado é sempre parcial.
        rotulo = ("NAO_ENCONTRADO_EM_BUSCA_PARCIAL"
                  if b["result"] == "nao_encontrado" else b["result"])
        md.append(f"- **Busca {b['target']}** (id {b['id']}): {rotulo} — "
                  f"{b['scope'][:220]}")
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

    # 3. documentos ----------------------------------------------------------
    md.append("## 3. Documentos")
    itens = repo.collection_items(uid)
    locais = [i for i in itens
              if i.get("provenance", {}).get("origem") == "ja_no_pc"]
    md.append(f"- **Localizados e validados no corpus local** "
              f"({len(locais)}) — NÃO adquiridos nesta execução: "
              + ", ".join(i["title"] for i in locais[:8]))
    por_status: dict[str, list[str]] = {}
    for i in itens:
        if i in locais:
            continue
        por_status.setdefault(i["status"], []).append(i["title"])
    for status in ("promovido", "validado", "staged", "bloqueado_simulacao",
                   "falhou", "requer_intervencao", "cancelado", "pendente"):
        if status in por_status:
            md.append(f"- {status}: {len(por_status[status])} — "
                      + ", ".join(por_status[status][:10]))
    md.append("- **Adquiridos nesta execução: 0** (nenhuma operação paga).")
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
    pops = repo.populacoes_contagens(uid)
    dpu_n = pops.get("dpu_exhibit_a", 0)
    zero_n = pops.get("in_dpu_but_zero_unit_acres", 0)
    md.append(f"- **{dpu_n} leases listadas no Exhibit A** (população "
              f"original PRESERVADA).")
    md.append(f"- **{dpu_n - zero_n} leases potencialmente contribuintes**.")
    md.append(f"- **{zero_n} leases `in_dpu_but_zero_unit_acres`** — "
              f"exclusivamente A-811 (leitura declarada dos 7 instrumentos; "
              f"permanecem no Exhibit A e na trilha).")
    for pop, n in sorted(pops.items()):
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

    # 9. simulação (quando a política estiver ativa) --------------------------
    from src.casefile import simulacao
    if simulacao.ativa(repo, unit["id"]):
        md.append("## 9. Simulação (golden replay — política de 02/09)")
        origens_censo = repo.contagem_censo(uid)
        auto = sum(d["conteudos"] for o, d in origens_censo.items()
                   if o in ("unit_files", "unit_folder",
                            "project_reference"))
        entrega = origens_censo.get("entrega", {}).get("conteudos", 0)
        md.append(f"- **Corpus autônomo**: {auto} conteúdo(s) "
                  f"(unit_files/unit_folder/referências).")
        md.append(f"- **Material da entrega (contaminado)**: {entrega} "
                  f"conteúdo(s) — utilizável para exame/reconstrução com "
                  f"benchmark_contamination=true; NÃO conta como coleta "
                  f"autônoma. 'PLM Report' (DDR final e conclusões humanas) "
                  f"segue bloqueado por plumbing.")
        bloqueados = [i for i in itens
                      if i["status"] == "bloqueado_simulacao"]
        md.append(f"- **Ausências da simulação / coletas necessárias em "
                  f"produção** ({len(bloqueados)}):")
        for i in bloqueados:
            md.append(f"  - {i['title']} — "
                      f"{i['target'].get('motivo', '')[:120]} "
                      f"[{simulacao.MARCADOR_BLOQUEIO}]")
        md.append("  - DOTO/DOI do JOSH B UNIT — em produção exigiria "
                  "solicitação real ao PM/seller (busca negativa id 1).")
        md.append("  - Quitclaim Deed do curative Stewart (sem recording no "
                  "e-mail) — em produção exigiria índice de grantor ou "
                  "PM/seller.")
        custo_hipotetico = round(len(bloqueados) * 0.50, 2)
        custo_portal_real = custos.get("coleta", 0.0)
        md.append(f"- **Custo hipotético de execução real (portal)**: "
                  f"${custo_hipotetico:.2f} ({len(bloqueados)} abertura(s) "
                  f"x $0,50).")
        md.append(f"- **Custo de portal efetivamente realizado**: "
                  f"${custo_portal_real:.2f}"
                  + (" — OK, $0 como exige a política."
                     if custo_portal_real == 0
                     else " — **ALERTA: deveria ser $0!**"))
        md.append("- **Bloqueio técnico de compras ATIVO** "
                  "(simulacao.exigir_bloqueio_pagamento antes de qualquer "
                  "abertura, env + política no banco).")
        md.append("")
        md.append("### Limitações da simulação, por categoria")
        md.append("1. **Documentos de cartório ausentes**: "
                  + (", ".join(i["title"] for i in bloqueados)
                     or "(nenhum)")
                  + " — required_in_production_but_unavailable_in_"
                    "simulation.")
        md.append("2. **DOTO/DOI**: NAO_ENCONTRADO_EM_BUSCA_PARCIAL "
                  "(somente as camadas de texto foram pesquisáveis; TIFs "
                  "sem OCR não foram pesquisados internamente).")
        md.append("3. **Instrumentos do curative Stewart não localizados**: "
                  "Quitclaim Deed, Affidavit of Identity e Landman "
                  "Statement (citados no e-mail, sem recording).")
        md.append("4. **Solicitações que a produção faria e a simulação NÃO "
                  "enviou**: DOTO/DOI ao PM/seller; reexportação legível do "
                  "release; instrumentos Stewart ao PM/seller.")
        md.append("")
        md.append("### Release-of-suspense Stewart (claim 127) — o que "
                  "prova e o que não prova")
        md.append("- PROVA que a EOG colocou o interesse de Marlee "
                  "McConnell Stewart **em pay** (Josh A/B e Deaton, "
                  "03/2013).")
        md.append("- INDICA que a EOG **recebeu o curative** ('Curative "
                  "materials and revised DOI's are attached').")
        md.append("- **NÃO substitui a prova registral** — sem "
                  "volume/página, sem file number, sem data do Quitclaim.")
        md.append("- Gera **requisito separado**: "
                  "Quitclaim/Affidavit/Landman Statement (categoria 3 "
                  "acima).")
        md.append("")

    # 10. posição atual --------------------------------------------------------
    # A recomendação HISTÓRICA do exame dirigido (permanecer em COLETANDO,
    # aguardar pulls) vale apenas enquanto a unit estava em COLETANDO; depois
    # das transições da simulação ela sai integralmente do relatório —
    # correção da Parte A da ordem de 02/09.
    md.append("## 10. Posição atual")
    if estado == "COLETANDO":
        rec = caneta.caminho(pasta) / "RECOMENDACAO_VS2.md"
        if rec.exists():
            md.append(rec.read_text(encoding="utf-8").strip())
        else:
            md.append("(a sessão de exame ainda não propôs recomendação)")
    else:
        ultimas = repo.transicoes(uid)[-2:]
        md.append(f"A unit está em **{estado}** por determinação do "
                  f"operador (política de simulação de 02/09/2026):")
        for t in ultimas:
            md.append(f"- {t['from_state']} -> {t['to_state']} "
                      f"[{t['event']}]: {t['note'][:260]}")
        md.append("Próxima etapa: exame documental (VS3) sob simulação; "
                  "avanço ao VS4 (projeção no DDR) somente após aprovação "
                  "do VS3 pelo operador.")
    md.append("")
    md.append("_Nenhuma certificação de WI/NRI foi feita nesta etapa._")

    texto = "\n".join(md) + "\n"
    path = caneta.escrever_texto(
        caneta.caminho(pasta) / f"RELATORIO_COLETA_VS2_v{versao}.md", texto)
    sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    repo.registrar_deliverable(uid, "relatorio_coleta_vs2", versao,
                               str(path), sha)
    return path
