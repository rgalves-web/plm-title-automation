"""The agent loop — messages in, tool calls out, until the model stops.

This file is the plumbing the architecture allows Python to keep: send, receive,
dispatch, record. It has no opinion about what the model should read next, when
it has read enough, or whether an answer is good. The only thing it enforces is
that the run is finite and its cost is visible.

Every turn is logged: which tool, with what arguments, how many tokens, how much
it cost. "Sem relatorio sem artefato" — the log IS the artefact that says what
the Examiner did.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MAX_TOKENS = 8000
# Cortes seguidos de max_tokens sem conteúdo aproveitável antes de declarar a
# rodada incompleta.
MAX_CORTES = 3


def _uso_do_turno(message: Any, model: str) -> dict[str, Any]:
    uso = Usage()
    uso.add(message.usage)
    return uso.to_dict(model)

# Public list prices, USD per million tokens. Kept in one place and declared,
# not buried: if a rate is wrong every cost number below is wrong with it.
RATES: dict[str, dict[str, float]] = {
    "claude-opus-5": {"input": 5.0, "output": 25.0,
                      "cache_write": 6.25, "cache_read": 0.5},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0,
                        "cache_write": 2.5, "cache_read": 0.2},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0,
                                  "cache_write": 1.25, "cache_read": 0.1},
    # Ramo B (auditor OpenAI) — tarifa Standard em 24/08/2026, de
    # developers.openai.com/api/docs/pricing. A OpenAI não cobra escrita de
    # cache à parte (entra como input normal); "cached input" é só leitura.
    "gpt-5.6-terra": {"input": 2.0, "output": 12.0,
                      "cache_write": 2.5, "cache_read": 0.2},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.5,
                     "cache_write": 0.75, "cache_read": 0.075},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6,
                    "cache_write": 0.15, "cache_read": 0.075},
}


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0

    def add(self, raw: Any) -> None:
        self.input += int(getattr(raw, "input_tokens", 0) or 0)
        self.output += int(getattr(raw, "output_tokens", 0) or 0)
        self.cache_write += int(
            getattr(raw, "cache_creation_input_tokens", 0) or 0)
        self.cache_read += int(getattr(raw, "cache_read_input_tokens", 0) or 0)

    def cost(self, model: str) -> float | None:
        rate = RATES.get(model)
        if rate is None:
            return None
        return round(
            (self.input * rate["input"] + self.output * rate["output"]
             + self.cache_write * rate["cache_write"]
             + self.cache_read * rate["cache_read"]) / 1_000_000, 4)

    def to_dict(self, model: str) -> dict[str, Any]:
        # `entrada` sozinha engana: com cache, a API reporta ali só a fatia não
        # cacheada (dava "entrada: 2" num turno que pagou 20k). O total soma as
        # três colunas que de fato entraram no contexto.
        return {"entrada": self.input, "saida": self.output,
                "cache_escrita": self.cache_write, "cache_leitura": self.cache_read,
                "entrada_total": self.input + self.cache_write + self.cache_read,
                "custo_usd": self.cost(model)}


@dataclass
class TurnRecord:
    turn: int
    text: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunLog:
    model: str
    turns: list[TurnRecord] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    stop_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "modelo": self.model,
            "turnos": len(self.turns),
            "parou_porque": self.stop_reason,
            "uso": self.usage.to_dict(self.model),
            "ordem_das_ferramentas": [c["tool"] for t in self.turns
                                      for c in t.calls],
            "detalhe": [{"turno": t.turn, "texto": t.text, "chamadas": t.calls,
                         "uso": t.usage} for t in self.turns],
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path


def _client():
    import os

    try:
        from dotenv import load_dotenv
        load_dotenv(Path(".env"))
    except Exception:
        pass
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY nao esta definido.")
    import anthropic
    return anthropic.Anthropic(api_key=key)


def _tool_result_content(result: Any) -> Any:
    """A page asked for in `imagem` mode comes back as pixels, so the tool
    result carries an image block. Everything else is JSON text."""
    if isinstance(result, dict) and result.get("kind") == "image":
        return [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/png",
                "data": base64.standard_b64encode(result["png"]).decode("ascii")}},
            {"type": "text",
             "text": f"{result['documento']} pagina {result['pagina']} (imagem)"},
        ]
    return json.dumps(result, ensure_ascii=False, default=str)


def run_loop(*, system: str, task: str, tools: list[dict[str, Any]],
             dispatch: dict[str, Callable], model: str,
             max_turns: int = 400, max_cost_usd: float | None = None,
             max_output_tokens: int = MAX_TOKENS,
             on_turn: Callable[[TurnRecord], None] | None = None,
             client: Any = None,
             ) -> tuple[RunLog, list[dict[str, Any]]]:
    """Run until the model stops asking for tools, or a declared limit is hit.

    The limits are budget, not judgement: they say how much the operator is
    willing to spend, never what the answer should be. When one is reached the
    run stops and SAYS so in `stop_reason` — a truncated run reported as a
    finished one would poison the measurement this whole round exists for."""
    client = client or _client()
    log = RunLog(model=model)
    cortes = 0
    # The assignment carries the whole template map — 17k tokens that never
    # change. It is pinned in the cache; the rolling breakpoint below then
    # covers everything the conversation has accumulated since.
    messages: list[dict[str, Any]] = [{"role": "user", "content": [
        {"type": "text", "text": task,
         "cache_control": {"type": "ephemeral"}}]}]

    for turn in range(1, max_turns + 1):
        _roll_cache_breakpoint(messages)
        message = _create_com_retry(
            client, model=model, max_tokens=max_output_tokens,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            tools=tools, messages=messages)
        log.usage.add(message.usage)

        text = "".join(b.text for b in message.content
                       if getattr(b, "type", "") == "text")
        uses = [b for b in message.content if getattr(b, "type", "") == "tool_use"]

        # Resposta cortada no teto de saída SEM nenhuma chamada aproveitável:
        # o SDK descarta o tool_use incompleto e o conteúdo chega vazio. Tratar
        # isso como "o modelo parou" embarcou um DDR vazio no replay da Josh B
        # (24/08). O corte vira instrução de refazer em passos menores — com
        # teto próprio, para um modelo que só produz cortes não rodar à toa.
        if (getattr(message, "stop_reason", "") == "max_tokens"
                and not uses and not text.strip()):
            cortes += 1
            registro = TurnRecord(
                turn=turn, text=f"[resposta cortada em {max_output_tokens} tokens "
                                f"sem conteudo aproveitavel — corte "
                                f"{cortes}/{MAX_CORTES}]")
            registro.usage = _uso_do_turno(message, model)
            log.turns.append(registro)
            if on_turn:
                on_turn(registro)
            if cortes >= MAX_CORTES:
                log.stop_reason = (f"{MAX_CORTES} respostas seguidas cortadas "
                                   f"no teto de {MAX_TOKENS} tokens — "
                                   f"RODADA INCOMPLETA")
                break
            messages.append({"role": "user", "content": [{
                "type": "text",
                "text": ("Sua ultima resposta estourou o teto de "
                         f"{max_output_tokens} tokens de saida e chegou vazia — "
                         "NADA foi aplicado. Refaca em passos menores: "
                         "poucas chamadas de ferramenta por vez, trechos "
                         "curtos, sem listas gigantes num turno so. "
                         "Continue de onde parou.")}]})
            continue
        cortes = 0
        # The cache columns are most of the bill in a long loop; a per-turn line
        # without them reads as an order of magnitude cheaper than the run is.
        turn_usage = Usage()
        turn_usage.add(message.usage)
        record = TurnRecord(turn=turn, text=text,
                            usage=turn_usage.to_dict(model))
        messages.append({"role": "assistant", "content": message.content})

        if not uses:
            log.turns.append(record)
            if on_turn:
                on_turn(record)
            log.stop_reason = "o modelo parou de pedir ferramentas"
            break

        results = []
        for use in uses:
            args = dict(use.input or {})
            try:
                result = dispatch[use.name](**args)
                error = False
            except Exception as exc:            # the model sees its own mistakes
                result = {"erro": f"{exc.__class__.__name__}: {exc}"}
                error = True
            preview = (result.get("kind") if isinstance(result, dict) else None)
            record.calls.append({
                "tool": use.name, "args": _short(args),
                "input_sha256": __import__('hashlib').sha256(json.dumps(args,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest(),
                "erro": error,
                "resposta": ("imagem" if preview == "image"
                             else _short(result, 400)),
            })
            results.append({"type": "tool_result", "tool_use_id": use.id,
                            "content": _tool_result_content(result),
                            "is_error": error})
        messages.append({"role": "user", "content": results})

        log.turns.append(record)
        if on_turn:
            on_turn(record)

        spent = log.usage.cost(model)
        if max_cost_usd is not None and spent is not None and spent >= max_cost_usd:
            log.stop_reason = (f"teto de custo atingido: ${spent} de "
                               f"${max_cost_usd} — RODADA INCOMPLETA")
            break
    else:
        log.stop_reason = f"teto de {max_turns} turnos — RODADA INCOMPLETA"

    return log, messages


RETRY_TENTATIVAS = 5
RETRY_BASE_S = 2.0


def _transitorio(exc: Exception) -> bool:
    """Erro que vale repetir: sobrecarga, rate limit, 5xx, timeout/conexão.
    Nada de conteúdo — erro definitivo (400/401/403) não se repete."""
    status = getattr(exc, "status_code", None)
    if status in (429, 500, 502, 503, 504, 529):
        return True
    # Timeout e queda de conexão não carregam status; o nome da classe é o
    # contrato do SDK (APITimeoutError derrubou o ship do replay 2 em 24/08).
    return exc.__class__.__name__ in ("APITimeoutError", "APIConnectionError")


def _create_com_retry(client: Any, **kwargs: Any) -> Any:
    """`messages.create` com backoff exponencial para erro transitório.

    Dois 529 seguidos mataram sessões no turno 1 em 24/08; num turno 40 o
    mesmo erro perderia uma conversa inteira já paga. Repetir sobrecarga da
    API é plumbing — não muda o que o modelo responde, só quando."""
    import time

    if getattr(client,'manages_retries',False):
        return client.messages.create(**kwargs)
    for tentativa in range(RETRY_TENTATIVAS):
        try:
            return client.messages.create(**kwargs)
        except Exception as exc:
            if not _transitorio(exc) or tentativa == RETRY_TENTATIVAS - 1:
                raise
            espera = RETRY_BASE_S * (2 ** tentativa)
            print(f"   API {getattr(exc, 'status_code', '?')} transitório — "
                  f"tentativa {tentativa + 1}/{RETRY_TENTATIVAS}, aguardando "
                  f"{espera:.0f}s…", flush=True)
            time.sleep(espera)


def _roll_cache_breakpoint(messages: list[dict[str, Any]]) -> None:
    """Cache everything up to the latest turn, not just the assignment.

    An agentic loop re-sends the whole conversation every turn, so by turn 50
    the unchanged prefix is most of what is paid for. Four breakpoints are
    allowed; this keeps two — the pinned assignment and a moving one at the
    end — and clears the previous moving mark so they do not accumulate."""
    for msg in messages[1:]:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block.pop("cache_control", None)
    last = messages[-1]
    content = last.get("content")
    if isinstance(content, list) and content and isinstance(content[-1], dict):
        content[-1]["cache_control"] = {"type": "ephemeral"}


def _short(value: Any, limit: int = 220) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"
