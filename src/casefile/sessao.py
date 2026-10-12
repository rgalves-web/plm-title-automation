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
from src.infra.loop import run_loop, Usage

MODELO_DEFAULT = "claude-opus-5"


def modelo() -> str:
    return os.environ.get("CASEFILE_MODELO",
                          os.environ.get("MINORH_MODELO", MODELO_DEFAULT))


def rodar(*, repo: Any, unit: dict[str, Any], pasta: Path, comando: str,
          sistema: str, task: str, ferramentas: list[dict[str, Any]],
          dispatch: dict[str, Any], modelo_sessao: str,
          max_cost_usd: float, client: Any = None, max_turns: int = 250,
          session_ref: dict[str, Any] | None = None) -> tuple[Any, int]:
    # Prepare the write root before opening a database session.
    root = caneta.caminho(pasta)
    session_id = repo.abrir_sessao(unit["id"], comando, modelo_sessao)
    if session_ref is not None:
        session_ref["id"] = session_id

    progresso = root / f"progresso_{comando}.jsonl"
    uso_pago = Usage()
    turns = 0
    accounted = 0.0
    received = 0
    log = None
    reason = "INTERROMPIDA: antes do primeiro turno"
    log_path = caneta.caminho(pasta) / f"log_{comando}_{session_id}.json"

    def account(u: dict[str, Any], turn: int) -> None:
        nonlocal accounted
        uso_pago.input += u.get('entrada', 0)
        uso_pago.output += u.get('saida', 0)
        uso_pago.cache_write += u.get('cache_escrita', 0)
        uso_pago.cache_read += u.get('cache_leitura', 0)
        total = uso_pago.cost(modelo_sessao)
        if total is not None:
            repo.registrar_custo(unit['id'], 'modelo', round(total - accounted, 4),
                                 {'session_id': session_id, 'comando': comando,
                                  'modelo': modelo_sessao, 'turno': turn})
            accounted = total

    class AccountedClient:
        """Persist each received response before any tool can interrupt execution."""
        def __init__(self):
            self.messages = self
            self.delegate = client

        def create(self, **kwargs):
            nonlocal received
            if self.delegate is None:
                from src.infra.loop import _client
                self.delegate = _client()
            message = self.delegate.messages.create(**kwargs)
            received += 1
            usage = Usage()
            usage.add(message.usage)
            account(usage.to_dict(modelo_sessao), received)
            return message

    def flush(rec: Any) -> None:
        nonlocal turns
        turns += 1
        if received < rec.turn:  # scripted run_loop harnesses can emit records directly
            account(rec.usage or {}, rec.turn)
        with progresso.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"session_id": session_id, "turno": rec.turn, "chamadas": [c["tool"] for c in rec.calls],
                 "uso": rec.usage, "texto": rec.text[:300]},
                ensure_ascii=False) + "\n")
        chamadas = ", ".join(c["tool"] for c in rec.calls) or "(sem chamadas)"
        custo = (rec.usage or {}).get("custo_usd")
        print(f"   turno {rec.turn}: {chamadas}"
              + (f" · ${custo}" if custo is not None else ""), flush=True)

    try:
        if comando in ('planejar.examinador', 'exame.vs3'):
            from src.casefile.training_runtime import prepare
            context, extra_tools, extra_dispatch = prepare(repo, unit, session_id, comando)
            task += context
            ferramentas = list(ferramentas) + extra_tools
            dispatch = {**dispatch, **extra_dispatch}
            if session_ref is not None:
                session_ref['knowledge'] = True
        print("   modelo chamado — a primeira resposta pode levar de 1 a 3 "
              "minutos; cada turno imprime uma linha abaixo.", flush=True)
        log, _ = run_loop(system=sistema, task=task, tools=ferramentas,
                      dispatch=dispatch, model=modelo_sessao,
                      max_turns=max_turns, max_cost_usd=max_cost_usd,
                      on_turn=flush, client=AccountedClient())

        reason = log.stop_reason
        log.save(log_path)
        # Compatibility pointer; the database references the retained session log.
        log.save(caneta.caminho(pasta) / f'log_{comando}.json')
    except BaseException as exc:
        reason = f'INTERROMPIDA: {type(exc).__name__}; uso confirmado ate o ultimo turno persistido'
        raise
    finally:
        uso = log.usage.to_dict(modelo_sessao) if log else uso_pago.to_dict(modelo_sessao)
        # API errors never cause the already observed paid turns to disappear.
        # Unknown price remains null in model_sessions, not certified zero.
        if uso.get('custo_usd') is not None and uso['custo_usd'] != accounted:
            repo.registrar_custo(unit['id'], 'modelo', round(uso['custo_usd'] - accounted, 4),
                                 {'session_id': session_id, 'comando': comando, 'reconciliation': True})
        repo.fechar_sessao(session_id, reason, len(log.turns) if log else max(turns, received), uso,
                           uso.get('custo_usd'), str(log_path) if log else (str(progresso) if progresso.exists() else ''))
    if "INCOMPLETA" in log.stop_reason:
        print(f"ATENCAO: {log.stop_reason}")
    return log, session_id
