"""Execução dos acessos externos — cartório (CourthouseDirect) e RRC.

Reuso por import da receita provada da Etapa H (src/minorh/coleta.py):
captura CDP no Chrome corporativo LOGADO do operador, corte do PNG pelas
alturas reais, validação de carimbo pela família B. Diferenças do VS2:
captura nasce em STAGING (nunca direto em FILES/ — condição 6), o ledger de
aberturas é o banco (`cost_entries` categoria 'coleta', separada de
'modelo'), e cada item é um `collection_item` com procedência.

Proibições de sempre: nenhuma credencial, nenhum pagamento digitado; sem
Chrome logado (CDP), os itens viram `requer_intervencao` nomeando o
pré-requisito do operador.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.casefile import staging
from src.minorh.coleta import (CUSTO_ABERTURA_USD, _capturar_cdp,
                               png_para_pdf, validar_carimbo)


def teto_coleta() -> float:
    return float(os.environ.get(
        "CASEFILE_TETO_COLETA_USD",
        os.environ.get("MINORH_TETO_COLETA_USD", "25")))


def cdp_disponivel(cdp_url: str = "http://localhost:9222") -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{cdp_url}/json/version",
                                    timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def executar_cartorio(repo: Any, unit: dict[str, Any], pasta: Path,
                      cdp_url: str = "http://localhost:9222",
                      capturador: Any = None,
                      validador: Any = None) -> dict[str, Any]:
    from src.casefile import simulacao

    capturador = capturador or _capturar_cdp
    validador = validador or validar_carimbo
    itens = [i for i in repo.collection_items(unit["id"])
             if i["method"] == "courthousedirect"
             and i["status"] in ("pendente", "staged", "falhou")]
    resumo = {"pendentes": len(itens), "ja_no_disco": 0, "promovidos": 0,
              "falhas": [], "carimbo_invalido": [], "aberturas": 0,
              "custo_coleta_usd": 0.0, "intervencao": [],
              "bloqueados_simulacao": []}
    if not itens:
        return resumo

    # Gate GLOBAL de simulação: falha/bloqueio ANTES de abrir qualquer
    # documento, independente de instrução do agente (política de 02/09).
    if simulacao.ativa(repo, unit["id"]):
        for i in itens:
            repo.atualizar_collection_item(
                i["id"], status="bloqueado_simulacao",
                note=f"{simulacao.MARCADOR_BLOQUEIO} — "
                     f"{i['target'].get('motivo', '')}"[:380])
        resumo["bloqueados_simulacao"] = [i["title"] for i in itens]
        return resumo

    if not cdp_disponivel(cdp_url):
        for i in itens:
            repo.atualizar_collection_item(
                i["id"], status="requer_intervencao",
                note="Chrome corporativo com CDP (porta 9222) nao esta de "
                     "pe — operador abre o CourthouseDirect logado com "
                     "--remote-debugging-port=9222")
        resumo["intervencao"] = [i["title"] for i in itens]
        return resumo

    primeiro_conferido = False
    for item in itens:
        alvo = item["target"]
        destino_final = pasta / "FILES" / alvo["arquivo_alvo"]
        if destino_final.exists():
            repo.atualizar_collection_item(
                item["id"], status="promovido",
                promoted_path=str(destino_final),
                note="ja estava no disco — nunca se reabre")
            resumo["ja_no_disco"] += 1
            continue
        gasto = repo.custo_por_categoria(unit["id"]).get("coleta", 0.0)
        if gasto >= teto_coleta():
            repo.atualizar_collection_item(
                item["id"], status="requer_intervencao",
                note=f"TETO DE COLETA atingido (${gasto} >= "
                     f"${teto_coleta()}) — autorizar excecao: "
                     f"CASEFILE_TETO_COLETA_USD=<novo>")
            resumo["intervencao"].append(item["title"])
            continue
        simulacao.exigir_bloqueio_pagamento(
            f"abertura CourthouseDirect {alvo['arquivo_alvo']}",
            repo, unit["id"])
        try:
            png, alturas = capturador(
                {"book": alvo["book"], "page": alvo["page"]},
                cdp_url=cdp_url)
        except Exception as exc:
            repo.registrar_custo(unit["id"], "coleta", CUSTO_ABERTURA_USD,
                                 {"item": item["id"],
                                  "resultado": f"falha: "
                                               f"{exc.__class__.__name__}"})
            staging.marcar_falha(repo, item["id"],
                                 f"{exc.__class__.__name__}: {exc}")
            resumo["falhas"].append({"arquivo": alvo["arquivo_alvo"],
                                     "erro": str(exc)[:160]})
            resumo["aberturas"] += 1
            continue
        repo.registrar_custo(unit["id"], "coleta", CUSTO_ABERTURA_USD,
                             {"item": item["id"], "resultado": "capturado"})
        resumo["aberturas"] += 1
        staged = staging.dir_staging(pasta) / alvo["arquivo_alvo"]
        png_para_pdf(png, alturas, staged)
        dados = staged.read_bytes()
        import hashlib
        sha = hashlib.sha256(dados).hexdigest()
        repo.atualizar_collection_item(
            item["id"], status="staged", staged_path=str(staged), sha256=sha,
            provenance={"portal": "courthousedirect", "book": alvo["book"],
                        "page": alvo["page"], "condado": alvo.get("condado"),
                        "custo_abertura_usd": CUSTO_ABERTURA_USD,
                        "bytes": len(dados)})
        veredito = validador(staged, book=alvo["book"], page=alvo["page"])
        if not veredito["valido"]:
            resumo["carimbo_invalido"].append(veredito)
            staging.marcar_falha(
                repo, item["id"],
                "carimbo NAO validado pela familia B — fica em staging, "
                "nada promovido")
            continue
        staging.marcar_validado(repo, item["id"],
                                "carimbo validado pela familia B")
        item_atual = next(i for i in repo.collection_items(unit["id"])
                          if i["id"] == item["id"])
        staging.promover(repo, unit, pasta, item_atual)
        resumo["promovidos"] += 1
        if not primeiro_conferido:
            # Regra da receita: conferir o 1º documento no disco antes de
            # liberar a fila (40 capturas perdidas na rodada manual).
            if not destino_final.exists() or \
                    destino_final.stat().st_size == 0:
                raise SystemExit(
                    f"CONFERENCIA DO PRIMEIRO DOCUMENTO FALHOU: "
                    f"{destino_final} nao esta integro. Fila parada.")
            primeiro_conferido = True
            print(f"   primeiro documento conferido no disco: "
                  f"{destino_final.name}", flush=True)
    resumo["custo_coleta_usd"] = \
        repo.custo_por_categoria(unit["id"]).get("coleta", 0.0)
    return resumo


def baixar_publico(repo: Any, unit: dict[str, Any], pasta: Path,
                   item_id: int, url: str, nome_alvo: str,
                   nota_validacao: str) -> dict[str, Any]:
    """Documento PÚBLICO (RRC) por HTTP → staging → validado → promovido.
    Sem carimbo de cartório; a validação é a nota declarada (origem pública
    + URL na procedência)."""
    from src.casefile import simulacao
    simulacao.exigir_bloqueio_pagamento(f"download externo {url}",
                                        repo, unit["id"])
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dados = resp.read()
    if not dados:
        raise RuntimeError(f"download vazio: {url}")
    staged, sha = staging.stage_bytes(
        repo, unit, pasta, item_id, nome_alvo, dados,
        {"portal": "rrc-publico", "url": url})
    staging.marcar_validado(repo, item_id, nota_validacao)
    item = next(i for i in repo.collection_items(unit["id"])
                if i["id"] == item_id)
    final = staging.promover(repo, unit, pasta, item)
    return {"promovido": str(final), "sha256": sha, "bytes": len(dados)}
