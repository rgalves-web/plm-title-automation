"""Reconciliação de recordings por lease — DPU × Schedule × XREF × claims.

Determinações 3 e 4 do operador (02/09/2026): antes de qualquer pull,
cruzar o recording de cada lease em TODAS as fontes disponíveis no banco,
expor divergência, dizer que documento já existe no acervo e derivar a ação
de coleta. Tudo determinístico e rastreável: os pares vol/página vêm dos
claims (com id citado), das linhas indexadas da Schedule e das checagens
NOMEADAS pelo operador; nenhuma linha daqui decide title.

O XREF não tem coluna de recording (claim 111) — a coluna da matriz o
declara, em vez de fingir cruzamento.
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.casefile.xref_local import chave_recording, normalizar_lease

# Determinação 3, verbatim do operador — cada par é instrução, não inferência.
CHECAGENS_DO_OPERADOR: tuple[tuple[str, str, str, str], ...] = (
    ("0220604/018", "506", "386",
     "apresentado antes como 506.38 — CORRIGIDO para 506.386"),
    ("0220604/021", "557", "240", ""),
    ("0220604/023", "562", "895", ""),
    ("0220750/017", "509", "137", ""),
    ("0220750/008", "610", "245",
     "recording manuscrito; alternativas via indice de grantor no Vol 439"),
    ("0220953/005", "514", "412",
     "conferir Vol 515 (divergencia com a Schedule)"),
)

# Alvos herdados do exame dirigido (itens emitidos pelo modelo + achados),
# reconciliados aqui: cada um preso a uma lease e a um motivo.
ALVOS_HERDADOS: tuple[tuple[str, str, str, str], ...] = (
    ("0220604/026", "569", "324", "pasta so tem Change of Address"),
    ("0220750/018", "572", "118", "pasta so tem stale check"),
    ("0220953/002", "441", "275",
     "Prior Lease BRA-DE de 31/03/2008 — base da cadeia (claims 116/117)"),
    ("0220936/006", "596", "589",
     "unico instrumento ilegivel da serie 0220936 — decide a classificacao"),
)

_PAR_RE = re.compile(
    r"(?:vol(?:ume)?\.?\s*(\d{1,4})\D{0,10}?(?:pg|pag\w*|page|p)\.?\s*"
    r"(\d{1,4}))|(?:\b(\d{3,4})\s*/\s*(\d{1,4})\b)", re.IGNORECASE)


def _pares_no_texto(texto: str) -> set[tuple[str, str]]:
    out = set()
    for m in _PAR_RE.finditer(texto):
        vol, pg = (m.group(1), m.group(2)) if m.group(1) else \
            (m.group(3), m.group(4))
        out.add((vol.lstrip("0") or "0", pg.lstrip("0") or "0"))
    return out


def _par(vol: str, page: str) -> tuple[str, str]:
    return (str(vol).lstrip("0") or "0", str(page).lstrip("0") or "0")


def matriz(repo: Any, unit: dict[str, Any]) -> list[dict[str, Any]]:
    uid = unit["id"]
    # Determinação 1: existência no corpus AUTÔNOMO fecha ação; existência
    # SÓ na entrega vira decisão do operador (cópia contaminada × $0,50 no
    # cartório) — nunca consumo silencioso da entrega.
    por_origem = repo.nomes_por_origem(uid)
    nomes = {n for n, o in por_origem.items()
             if o - {"entrega", "outro"}}
    nomes_entrega = {n for n, o in por_origem.items()
                     if o <= {"entrega", "outro"} and "entrega" in o}
    claims_todos = repo.claims_da_unit(uid)

    # Linhas da Schedule (a única fonte tabular com RECORDING).
    sha_schedule = next(
        (shas[0] for nome, shas in repo.sha_por_nome(uid).items()
         if nome.startswith("referencias/") and "schedule" in nome), None)
    linhas_schedule = [r for r in repo.xref_rows_da_unit(uid)
                       if r["source_sha256"] == sha_schedule]

    checagens = {normalizar_lease(le): (v, p, nota)
                 for le, v, p, nota in CHECAGENS_DO_OPERADOR}
    herdados = {normalizar_lease(le): (v, p, nota)
                for le, v, p, nota in ALVOS_HERDADOS}

    out = []
    for c in sorted(repo.claims_da_unit(uid, "lease_in_unit"),
                    key=lambda c: c["value"].get("lease_no", "")):
        v = c["value"]
        lease = normalizar_lease(v.get("lease_no", ""))
        dpu_vol, dpu_pg = str(v.get("vol", "")), str(v.get("page", ""))

        # Schedule: a linha desta lease e o campo RECORDING cru + conferência.
        rec_cells = []
        for r in linhas_schedule:
            if any(k.startswith("lease_no:") and
                   normalizar_lease(k.split(":", 1)[1]) == lease
                   for k in r["matched_keys"]) or \
               any(k == f"recording:{dpu_vol}/{dpu_pg}"
                   for k in r["matched_keys"]):
                rec_cells.append(str(r["row"].get("RECORDING", ""))[:80])
        schedule_confere = None
        if rec_cells and dpu_vol and dpu_pg:
            chave = chave_recording(dpu_vol, dpu_pg, coluna="R")
            schedule_confere = any(chave.casa({"R": cell})
                                   for cell in rec_cells)

        # Outras fontes: pares citados em claims que mencionam esta lease.
        outras: dict[tuple[str, str], list[int]] = {}
        alvo_txts = (lease, lease.replace("-", "/"))
        for cl in claims_todos:
            if cl["id"] == c["id"]:
                continue
            texto = (cl["entity"] + " " + json.dumps(cl["value"],
                                                     ensure_ascii=False)
                     + " " + cl["evidence"])
            if not any(t in normalizar_lease(texto) or t in texto
                       for t in alvo_txts):
                continue
            for par in _pares_no_texto(texto):
                if dpu_vol and par == _par(dpu_vol, dpu_pg):
                    continue
                outras.setdefault(par, []).append(cl["id"])

        # Acervo: pasta, instrumento e arquivos por vol/página.
        pasta_tokens = [n for n in nomes if f"/{lease.lower()} (" in n
                        or n.startswith(f"files/{lease.lower()} (")]
        tem_pasta = bool(pasta_tokens)
        tem_instrumento = any(
            ("lease.tif" in n or "lease - rec" in n or "lease-rec" in n
             or " ogl" in n or "memo" in n) for n in pasta_tokens)
        arquivos_vol_pg, so_na_entrega = _existe_par(
            dpu_vol, dpu_pg, nomes, nomes_entrega)

        chec = checagens.get(lease)
        herd = herdados.get(lease)
        divergencias = []
        if schedule_confere is False:
            divergencias.append("Schedule NAO confere com a DPU")
        if outras:
            divergencias.append(
                "pares alternativos: " + "; ".join(
                    f"{v}/{p} (claims {ids})"
                    for (v, p), ids in sorted(outras.items())))
        if chec and chec[2]:
            divergencias.append(f"checagem do operador: {chec[2]}")

        acao, alvo = _acao(lease, dpu_vol, dpu_pg, tem_pasta,
                           tem_instrumento, arquivos_vol_pg, so_na_entrega,
                           chec, herd, nomes, nomes_entrega)
        out.append({
            "lease": v.get("lease_no", lease), "lessor":
                str(v.get("lessor", ""))[:34],
            "dpu": f"{dpu_vol}/{dpu_pg}" if dpu_vol else "(sem par)",
            "schedule": ("confere" if schedule_confere
                         else "NAO confere" if schedule_confere is False
                         else "sem linha"),
            "xref": "n/a (sem coluna RECORDING — claim 111)",
            "acervo": ("instrumento na pasta" if tem_instrumento
                       else "pasta SEM instrumento" if tem_pasta
                       else "SEM pasta")
            + (f"; vol/pg no corpus: {arquivos_vol_pg}"
               if arquivos_vol_pg else "")
            + (f"; SO NA ENTREGA: {so_na_entrega}" if so_na_entrega
               else ""),
            "divergencia": "; ".join(divergencias) or "-",
            "acao": acao, "alvo": alvo, "claim": c["id"],
        })
    return out


def _existe_par(vol: str, pg: str, nomes: set[str],
                nomes_entrega: set[str]) -> tuple[list[str], list[str]]:
    """(no corpus autônomo, só na entrega) para os nomes derivados do par."""
    autonomo, entrega = [], []
    if not (vol and pg):
        return autonomo, entrega
    candidatos = [f"{vol}.{pg}.pdf", f"{vol}_{pg}.tif", f"{vol}.{pg} "]
    if str(pg).isdigit():
        candidatos.append(f"{vol}_{int(pg):04d}.tif")
    for cand in candidatos:
        baixo = cand.lower()
        if any(baixo in n for n in nomes):
            autonomo.append(cand)
        elif any(baixo in n for n in nomes_entrega):
            entrega.append(cand)
    return autonomo, entrega


def _acao(lease: str, vol: str, pg: str, tem_pasta: bool,
          tem_instrumento: bool, arquivos: list[str],
          so_na_entrega: list[str], chec: tuple | None, herd: tuple | None,
          nomes: set[str] = frozenset(),
          nomes_entrega: set[str] = frozenset()
          ) -> tuple[str, dict[str, str] | None]:
    fonte = chec or herd
    if fonte:
        # O alvo é um documento ESPECÍFICO (vol/página da checagem ou do
        # achado) — a existência se confere contra ELE, nunca contra o
        # instrumento genérico da pasta (a Prior Lease 441/275 não é a
        # lease.tif da /002).
        v, p, nota = fonte
        alvo = {"book": v, "page": p, "arquivo_alvo": f"{v}.{p}.pdf",
                "motivo": nota or "checagem/alvo reconciliado"}
        alvo_auto, alvo_entrega = _existe_par(v, p, nomes, nomes_entrega)
        if alvo_auto:
            return ("nenhuma — alvo ja no corpus autonomo", None)
        if alvo_entrega:
            return (f"DECISAO DO OPERADOR: usar copia da entrega "
                    f"(benchmark_contamination) OU coletar {v}.{p}.pdf "
                    f"($0,50)", None)
        extra = " + indice de grantor Vol 439" if lease.startswith(
            "0220750-008") else ""
        return (f"coletar {v}.{p}.pdf{extra}", alvo)
    if arquivos or tem_instrumento:
        return ("nenhuma — instrumento no corpus autonomo", None)
    if so_na_entrega:
        return ("DECISAO DO OPERADOR: usar copia da entrega "
                "(benchmark_contamination) OU coletar "
                f"{vol}.{pg}.pdf ($0,50)", None)
    if vol and pg:
        return (f"coletar {vol}.{pg}.pdf",
                {"book": vol, "page": pg,
                 "arquivo_alvo": f"{vol}.{pg}.pdf",
                 "motivo": "sem instrumento no corpus autonomo (recording "
                           "da DPU)"})
    return ("indice de grantor (sem par deterministico)", None)


def render_md(linhas: list[dict[str, Any]], custo_estimado: float,
              pulls: int) -> str:
    md = ["# RECONCILIACAO DE RECORDINGS — matriz por lease",
          "", "DPU = Exhibit A (claims); Schedule = linhas indexadas "
          "(RECORDING); XREF sem coluna de recording (claim 111); "
          "checagens da determinacao 3 do operador embutidas.", "",
          "| lease | lessor | DPU | Schedule | acervo | divergencia | acao |",
          "|---|---|---|---|---|---|---|"]
    for li in linhas:
        md.append(f"| {li['lease']} | {li['lessor']} | {li['dpu']} | "
                  f"{li['schedule']} | {li['acervo'][:60]} | "
                  f"{li['divergencia'][:90]} | {li['acao']} |")
    decisoes = sum(1 for li in linhas
                   if li["acao"].startswith("DECISAO DO OPERADOR"))
    md += ["", f"**Pull list reconciliada: {pulls} documento(s) · custo "
           f"estimado ${custo_estimado:.2f}** (US$ 0,50/abertura)",
           f"**Decisões do operador pendentes (cópia da entrega × coleta "
           f"paga): {decisoes}**", ""]
    return "\n".join(md)


def regenerar_pull(repo: Any, unit: dict[str, Any],
                   linhas: list[dict[str, Any]]) -> dict[str, Any]:
    """Cancela os itens de cartório antigos não-promovidos e cria o conjunto
    reconciliado e deduplicado. Nada some: cancelado leva nota."""
    uid = unit["id"]
    antigos = [i for i in repo.collection_items(uid)
               if i["method"] == "courthousedirect"
               and i["status"] in ("pendente", "requer_intervencao",
                                   "falhou", "staged")]
    for i in antigos:
        repo.atualizar_collection_item(
            i["id"], status="cancelado",
            note="substituido pela pull list reconciliada de 02/09 "
                 "(determinacoes 3-4; inclui correcao 506.38 -> 506.386)")

    vistos: set[tuple[str, str]] = set()
    novos = []
    for li in linhas:
        alvo = li.get("alvo")
        if not alvo:
            continue
        par = _par(alvo["book"], alvo["page"])
        if par in vistos:
            continue
        vistos.add(par)
        iid = repo.criar_collection_item(
            uid, title=alvo["arquivo_alvo"], method="courthousedirect",
            target={"book": alvo["book"], "page": alvo["page"],
                    "condado": "Montague", "arquivo_alvo":
                        alvo["arquivo_alvo"],
                    "instrumento": f"lease {li['lease']}",
                    "motivo": alvo["motivo"]})
        novos.append(iid)
    return {"cancelados": len(antigos), "novos": len(novos),
            "custo_estimado_usd": round(len(novos) * 0.50, 2)}
