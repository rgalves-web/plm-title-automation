"""Entregáveis e reconciliação do VS3 — montados do banco, sem julgamento.

O critério de aceite (item 12 da ordem): o VS3 não termina porque a sessão
acabou; termina quando a reconciliação fecha — população esperada ×
examinada × claims × verificações × gaps × dependências ausentes — e toda
população material tem posição. O que não fechar aparece NOMEADO em
UNRESOLVED_ISSUES, nunca some.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.casefile import caneta, gates


def _grava(repo: Any, unit: dict[str, Any], pasta: Path, kind: str,
           nome: str, texto: str) -> Path:
    path = caneta.escrever_texto(caneta.caminho(pasta) / nome, texto)
    versao = 1 + len(repo.deliverables(unit["id"], kind))
    repo.registrar_deliverable(
        unit["id"], kind, versao, str(path),
        hashlib.sha256(texto.encode("utf-8")).hexdigest())
    return path


def reconciliar(repo: Any, unit: dict[str, Any]) -> dict[str, Any]:
    uid = unit["id"]
    claims = repo.claims_da_unit(uid)
    verifs = repo.verificacoes(uid)
    por_claim: dict[int, list[dict[str, Any]]] = {}
    for v in verifs:
        por_claim.setdefault(v["claim_id"], []).append(v)
    vereditos = {k: 0 for k in ("concordancia", "divergencia",
                                "evidencia_insuficiente",
                                "nao_verificavel")}
    for v in verifs:
        vereditos[v["verdict"]] += 1
    tipos = {}
    for c in claims:
        t = c["value"].get("tipo_resultado") or {
            "fact": "fato_documental", "divergence": "divergencia",
            "document_missing": "documento_ausente"}.get(
                c["claim_type"], "fato_documental")
        tipos[t] = tipos.get(t, 0) + 1
    posicoes = repo.posicoes(uid)
    pops = repo.populacoes_contagens(uid)
    dpu = {m["member"] for m in repo.populacao(uid, "dpu_exhibit_a")}
    leases_verificadas = {
        c["id"] for c in repo.claims_da_unit(uid, "lease_in_unit")
        if c["id"] in por_claim}
    return {
        "claims_ativos": len(claims),
        "claims_com_verificacao": len(por_claim),
        "vereditos": vereditos,
        "tipos_resultado": tipos,
        "posicoes": len(posicoes),
        "posicoes_por_classe": _conta(posicoes, "classification"),
        "populacoes": pops,
        "leases_dpu": len(dpu),
        "leases_verificadas": len(leases_verificadas),
        "claims_ddr_prontos": sum(1 for c in claims
                                  if c.get("ddr_candidates")),
        "perguntas_abertas": len(repo.perguntas_vs2_abertas(uid)),
        "bloqueados_simulacao": [
            i["title"] for i in repo.collection_items(uid)
            if i["status"] == "bloqueado_simulacao"],
    }


def _conta(rows: list[dict[str, Any]], chave: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[chave]] = out.get(r[chave], 0) + 1
    return out


def gerar_todos(repo: Any, unit: dict[str, Any], pasta: Path
                ) -> dict[str, Path]:
    uid = unit["id"]
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec = reconciliar(repo, unit)
    posicoes = repo.posicoes(uid)
    claims = {c["id"]: c for c in repo.claims_da_unit(uid)}
    verifs = repo.verificacoes(uid)
    por_claim: dict[int, list[dict[str, Any]]] = {}
    for v in verifs:
        por_claim.setdefault(v["claim_id"], []).append(v)
    corte = next((c for c in claims.values()
                  if "data de corte" in c["entity"].lower()), None)
    out: dict[str, Path] = {}

    # --- TITLE_EXAMINATION ---------------------------------------------------
    md = [f"# TITLE EXAMINATION VS3 — {unit['canonical_name']} (v1)",
          f"_gerado em {agora} · simulação (golden replay) · nenhuma "
          f"certificação de WI/NRI_", "",
          "## Data de corte"]
    if corte:
        md.append(f"- {corte['value'].get('data', '?')} — fonte: "
                  f"{corte['value'].get('fonte', '?')} (claim "
                  f"{corte['id']}; trecho: {corte['evidence'][:140]})")
    else:
        md.append("- **NAO DETERMINADA** — a sessão de exame foi "
                  "interrompida antes deste dever (créditos da API); "
                  "pendente na retomada. Nenhum exame de supplemental usa "
                  "'até o presente'.")
    md += ["", "## Posições canônicas por população"]
    for p in posicoes:
        md.append(f"- **{p['population_item']}**: {p['classification']} — "
                  f"claims {p['claim_ids']}"
                  + (f" · {p['note'][:160]}" if p["note"] else ""))
    md += ["", "## Tipos de resultado (disciplina fato × inferência)"]
    for t, n in sorted(rec["tipos_resultado"].items()):
        md.append(f"- {t}: {n}")
    md += ["", "## Verificação cega (família B, comparação determinística)"]
    for k, n in rec["vereditos"].items():
        md.append(f"- {k}: {n}")
    md += ["", "## Reconciliação (critério de aceite)"]
    for k in ("claims_ativos", "claims_com_verificacao", "leases_dpu",
              "leases_verificadas", "posicoes", "claims_ddr_prontos",
              "perguntas_abertas"):
        md.append(f"- {k}: {rec[k]}")
    md.append(f"- populações: {rec['populacoes']}")
    md.append(f"- posições por classe: {rec['posicoes_por_classe']}")
    out["title_examination"] = _grava(
        repo, unit, pasta, "title_examination_vs3",
        "TITLE_EXAMINATION_VS3_v1.md", "\n".join(md) + "\n")

    # --- CLAIMS_READY_FOR_DDR ------------------------------------------------
    sessoes = {s["id"]: s for s in repo.sessoes_da_unit(uid)}
    prontos = []
    for c in claims.values():
        if not c.get("ddr_candidates"):
            continue
        vs = por_claim.get(c["id"], [])
        sess = sessoes.get(c["session_id"], {})
        prontos.append({
            "claim_id": c["id"], "entidade": c["entity"],
            "tipo": c["claim_type"], "valor": c["value"],
            "documento_sha256": c["source_sha256"], "pagina": c["page"],
            "trecho": c["evidence"],
            "origem": c["value"].get("origem_evidencia", "corpus_autonomo"),
            "benchmark_contamination":
                bool(c["value"].get("benchmark_contamination")),
            "agente_modelo": sess.get("model", ""),
            "versao_prompt": sess.get("command", ""),
            "verificacao_independente": [
                {"verdict": v["verdict"], "verifier_model":
                 v["verifier_model"], "question": v["question"]}
                for v in vs] or [{"verdict": "nao_verificado"}],
            "materialidade": c["materiality"],
            "limitacoes": c.get("limitations", ""),
            "celulas_candidatas": c.get("ddr_candidates", []),
        })
    texto = json.dumps({"unit": unit["canonical_name"], "gerado_em": agora,
                        "itens": prontos}, ensure_ascii=False, indent=1)
    out["claims_ready"] = _grava(repo, unit, pasta, "claims_ready_vs3",
                                 "CLAIMS_READY_FOR_DDR_VS3.json", texto)

    # --- UNRESOLVED_ISSUES ---------------------------------------------------
    md = [f"# UNRESOLVED ISSUES VS3 — {unit['canonical_name']}",
          f"_gerado em {agora}_", "", "## Divergências de verificação "
          "(abertas — adjudicação pendente)"]
    houve = False
    for v in verifs:
        if v["verdict"] == "divergencia":
            c = claims.get(v["claim_id"], {})
            md.append(f"- claim {v['claim_id']} ({c.get('entity', '')[:60]})"
                      f": verificador extraiu "
                      f"{json.dumps(v['verifier_value'], ensure_ascii=False)[:120]}")
            houve = True
    if not houve:
        md.append("- (nenhuma)")
    md += ["", "## Evidência insuficiente / não verificável"]
    for v in verifs:
        if v["verdict"] in ("evidencia_insuficiente", "nao_verificavel"):
            md.append(f"- claim {v['claim_id']}: {v['verdict']} — "
                      f"{str(v['comparison'])[:100]}")
    md += ["", "## Dependências ausentes na simulação"]
    for titulo in rec["bloqueados_simulacao"]:
        md.append(f"- {titulo} (required_in_production_but_unavailable_"
                  f"in_simulation)")
    md += ["- DOTO/DOI (NAO_ENCONTRADO_EM_BUSCA_PARCIAL)",
           "- Quitclaim/Affidavit/Landman Statement Stewart", "",
           "## Perguntas abertas ao operador"]
    for q in repo.perguntas_vs2_abertas(uid):
        md.append(f"- [{q['id']}] {q['question'][:180]}")
    md += ["", "## Divergências documentais ativas (claims divergence)"]
    for c in claims.values():
        if c["claim_type"] == "divergence":
            md.append(f"- [{c['id']}] {c['entity'][:100]}")
    out["unresolved"] = _grava(repo, unit, pasta, "unresolved_vs3",
                               "UNRESOLVED_ISSUES_VS3.md",
                               "\n".join(md) + "\n")

    # --- EVIDENCE_COVERAGE ---------------------------------------------------
    md = [f"# EVIDENCE COVERAGE VS3 — {unit['canonical_name']}",
          f"_gerado em {agora}_", ""]
    md.append(f"- Leases do Exhibit A: {rec['leases_dpu']} · com "
              f"verificação independente: {rec['leases_verificadas']}")
    md.append(f"- Claims ativos: {rec['claims_ativos']} · com verificação: "
              f"{rec['claims_com_verificacao']}")
    md.append(f"- Vereditos: {rec['vereditos']}")
    md.append(f"- Posições canônicas: {rec['posicoes']} "
              f"({rec['posicoes_por_classe']})")
    md.append(f"- Gates: " + "; ".join(
        f"{g['condicao']}={g['status']}" for g in gates.avaliar(repo, unit)))
    out["coverage"] = _grava(repo, unit, pasta, "coverage_vs3",
                             "EVIDENCE_COVERAGE_VS3.md",
                             "\n".join(md) + "\n")

    # --- COST_REPORT ---------------------------------------------------------
    custos = repo.custo_por_categoria(uid)
    sess_vs3 = [s for s in repo.sessoes_da_unit(uid)
                if s["command"].startswith("exame.")]
    md = [f"# COST REPORT VS3 — {unit['canonical_name']}",
          f"_gerado em {agora}_", ""]
    for s in sess_vs3:
        md.append(f"- sessão {s['id']} ({s['command']}, {s['model']}): "
                  f"${s['cost_usd'] or 0} · {s['turns']} turnos · "
                  f"{s['stop_reason'][:60]}")
    md.append(f"- verificação (família B): "
              f"${custos.get('verificacao', 0.0):.4f}")
    md.append(f"- custo por categoria: {custos}")
    md.append(f"- **total da unit: ${repo.custo_acumulado(uid):.2f}** "
              f"(teto $25) · portal: ${custos.get('coleta', 0.0):.2f}")
    out["cost"] = _grava(repo, unit, pasta, "cost_vs3",
                         "COST_REPORT_VS3.md", "\n".join(md) + "\n")
    return out
