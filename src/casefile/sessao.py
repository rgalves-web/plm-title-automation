"""Sessões de modelo do casefile — abre, roda, contabiliza, persiste.

Reuso por import de src/examinador/loop.py::run_loop (o mesmo laço do minorh,
com injeção de `client` para os testes roteirizados). A diferença: a sessão e
o custo entram no BANCO (model_sessions + cost_entries), e a contabilidade é
gravada ANTES de qualquer print — um console que engasga num caractere não
pode apagar o que já foi gasto (lição de 23/08, codificada no minorh).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.casefile import caneta
from src.examinador.loop import run_loop

MODELO_DEFAULT = "claude-opus-5"


def modelo() -> str:
    return os.environ.get("CASEFILE_MODELO",
                          os.environ.get("MINORH_MODELO", MODELO_DEFAULT))


def rodar(*, repo: Any, unit: dict[str, Any], pasta: Path, comando: str,
          sistema: str, task: str, ferramentas: list[dict[str, Any]],
          dispatch: dict[str, Any], modelo_sessao: str,
          max_cost_usd: float, client: Any = None, max_turns: int = 250,
          session_ref: dict[str, Any] | None = None) -> tuple[Any, int]:
    session_id = repo.abrir_sessao(unit["id"], comando, modelo_sessao)
    if session_ref is not None:
        session_ref["id"] = session_id

    progresso = caneta.caminho(pasta) / f"progresso_{comando}.jsonl"

    def flush(rec: Any) -> None:
        with progresso.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"turno": rec.turn, "chamadas": [c["tool"] for c in rec.calls],
                 "uso": rec.usage, "texto": rec.text[:300]},
                ensure_ascii=False) + "\n")
        chamadas = ", ".join(c["tool"] for c in rec.calls) or "(sem chamadas)"
        custo = (rec.usage or {}).get("custo_usd")
        print(f"   turno {rec.turn}: {chamadas}"
              + (f" · ${custo}" if custo is not None else ""), flush=True)

    print("   modelo chamado — a primeira resposta pode levar de 1 a 3 "
          "minutos; cada turno imprime uma linha abaixo.", flush=True)
    log, _ = run_loop(system=sistema, task=task, tools=ferramentas,
                      dispatch=dispatch, model=modelo_sessao,
                      max_turns=max_turns, max_cost_usd=max_cost_usd,
                      on_turn=flush, client=client)

    log_path = caneta.caminho(pasta) / f"log_{comando}.json"
    log.save(log_path)
    uso = log.usage.to_dict(modelo_sessao)
    # Contabilidade antes de qualquer print pós-sessão.
    repo.fechar_sessao(session_id, log.stop_reason, len(log.turns), uso,
                       uso.get("custo_usd"), str(log_path))
    repo.registrar_custo(unit["id"], "modelo", uso.get("custo_usd") or 0.0,
                         {"session_id": session_id, "comando": comando,
                          "modelo": modelo_sessao})
    if "INCOMPLETA" in log.stop_reason:
        print(f"ATENCAO: {log.stop_reason}")
    return log, session_id
