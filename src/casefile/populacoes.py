"""As populações nomeadas da unit — denominador preservado, deltas expostos.

Condições 1 e 2 da aprovação: a população da DPU (Exhibit "A") é o
denominador e NUNCA muda em silêncio; a série 0220936 fica em
`candidate_out_of_scope` até leitura provar exclusão; o que o XREF encontrou
vive em população própria, lado a lado — divergência é delta visível, nunca
substituição. Encanamento puro: os membros vêm de claims e de linhas
indexadas, com origem registrada.
"""
from __future__ import annotations

import re
from typing import Any

from src.casefile.xref_local import normalizar_lease

SERIE_CANDIDATA = "0220936"          # condição 1 (claim 100)
_LEASE_RE = re.compile(r"0\d{6}[-/]\d{3}")


def recalcular(repo: Any, unit: dict[str, Any]) -> dict[str, Any]:
    uid = unit["id"]
    # 1. dpu_exhibit_a — dos claims lease_in_unit; só cresce, nunca some.
    dpu: dict[str, int] = {}
    for c in repo.claims_da_unit(uid, "lease_in_unit"):
        membro = normalizar_lease(c["value"].get("lease_no") or c["entity"])
        dpu[membro] = c["id"]
        repo.gravar_membro_populacao(uid, "dpu_exhibit_a", membro,
                                     origem=f"claim {c['id']}")

    # 2. candidate_out_of_scope — a série 0220936, por condição expressa.
    for membro, cid in dpu.items():
        if membro.startswith(SERIE_CANDIDATA):
            repo.gravar_membro_populacao(
                uid, "candidate_out_of_scope", membro,
                origem=f"claim {cid}; condicao populacao-exhibit-a",
                note="permanece no denominador ate leitura provar exclusao")

    # 3. operacional — igual à DPU; exclusão só por decisão do operador.
    repo.limpar_populacao(uid, "operacional")
    for membro, cid in dpu.items():
        nota = ("candidate_out_of_scope pendente de leitura"
                if membro.startswith(SERIE_CANDIDATA) else "")
        repo.gravar_membro_populacao(uid, "operacional", membro,
                                     origem=f"claim {cid}", note=nota)

    # 4. xref_encontrada — leases das linhas recuperadas pelo índice local.
    repo.limpar_populacao(uid, "xref_encontrada")
    for r in repo.xref_rows_da_unit(uid):
        bruto = r["row"].get("LEASE NO", "")
        if not bruto:
            continue
        membro = normalizar_lease(bruto)
        repo.gravar_membro_populacao(
            uid, "xref_encontrada", membro,
            origem=f"xref_rows {r['sheet']}:{r['row_number']}",
            note=",".join(r["matched_keys"][:3]))

    # 5. documentos_ausentes_incompletos — dos claims document_missing.
    repo.limpar_populacao(uid, "documentos_ausentes_incompletos")
    for c in repo.claims_da_unit(uid, "document_missing"):
        alvo = _LEASE_RE.search(c["entity"] + " " +
                                str(c["value"].get("esperado", "")))
        membro = normalizar_lease(alvo.group()) if alvo else \
            c["entity"][:80]
        repo.gravar_membro_populacao(
            uid, "documentos_ausentes_incompletos", membro,
            origem=f"claim {c['id']}",
            note=str(c["value"].get("esperado", ""))[:120])

    # Deltas — exibidos, nunca resolvidos aqui.
    encontrada = {m["member"] for m in repo.populacao(uid, "xref_encontrada")}
    so_na_dpu = sorted(set(dpu) - encontrada)
    so_no_xref = sorted(encontrada - set(dpu))
    return {"contagens": repo.populacoes_contagens(uid),
            "dpu_sem_linha_no_xref": so_na_dpu,
            "xref_fora_da_dpu": so_no_xref}


def classificar_zero_acres(repo: Any, unit: dict[str, Any]
                           ) -> dict[str, Any]:
    """Determinação 5 (r2): se a leitura COMPLETA da série 0220936 declarar
    que nenhum instrumento abrange A-669/A-319, os 7 saem de
    candidate_out_of_scope para in_dpu_but_zero_unit_acres — presença no
    Exhibit A preservada, denominador intacto. O que se aplica aqui é a
    DECLARAÇÃO do modelo (claim citado), nunca inferência do código."""
    uid = unit["id"]
    facts = [c for c in repo.claims_da_unit(uid, "fact")
             if "0220936" in c["entity"]
             and c["value"].get("leitura_completa")
             and "abrange_a669_ou_a319" in c["value"]]
    if not facts:
        return {"classificado": False,
                "motivo": "sem leitura completa da serie com "
                          "abrange_a669_ou_a319 declarado"}
    melhor = facts[-1]
    if melhor["value"]["abrange_a669_ou_a319"] != "nao":
        return {"classificado": False,
                "motivo": f"claim {melhor['id']} declara "
                          f"{melhor['value']['abrange_a669_ou_a319']!r} — "
                          f"classificacao nao se aplica"}
    membros = [m["member"] for m in repo.populacao(uid, "dpu_exhibit_a")
               if m["member"].startswith(SERIE_CANDIDATA)]
    for membro in membros:
        repo.gravar_membro_populacao(
            uid, "in_dpu_but_zero_unit_acres", membro,
            origem=f"claim {melhor['id']}",
            note="Exhibit A preservado; zero acres na unit (A-811)")
    repo.limpar_populacao(uid, "candidate_out_of_scope")
    return {"classificado": True, "membros": membros,
            "claim": melhor["id"]}
