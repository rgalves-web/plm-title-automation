"""Decision card for Renato (issue 11).

Every task waiting for Renato's decision opens with a plain card, in
Portuguese: what is being decided, the Claim under decision (text, source
document, page, literal quote), what the Function concluded and why, the
observations and limits it raised, and what Accept and Reject each do.

The card is assembled only from recorded files: the task's accepted output
file and, for each Claim under decision, its Claim file. A Claim from before
Claim files has none; its index row is shown instead and labelled as such.
The source document's name comes from the artifact index. No model is
called and nothing is written while building a card.

An observation can become an open item with one click (`record_open_item`):
a new Claim of nature `item_aberto`, written as its own write-once Case file
beside the output that raised it.

Plumbing only: nothing here judges title content. The split of a free-text
justification into a short conclusion and observations follows fixed
markers; the full text is always shown alongside.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.casefile import case_file_store

OPEN_ITEM = "item_aberto"
MARKER = re.compile(
    r"^(observaç(?:ão|ões)|obs\b|limites?\b|limitaç(?:ão|ões)|ressalvas?\b|"
    r"pendente\b|pendênci(?:a|as)\b|atenção\b|nota\b)", re.IGNORECASE)
_DECISIONS = {"mantido": "Manteve a afirmação {cid}",
              "corrigido": "Corrigiu a afirmação {cid} com uma nova afirmação",
              "escalado": "Escalou a afirmação {cid} para a sua decisão"}
_ROLE = {"coordenador": "Coordenador", "pesquisador": "Pesquisador",
         "arquivista": "Arquivista", "classificador": "Classificador",
         "examinador": "Examinador", "verificador": "Verificador",
         "arbitro": "Árbitro", "redator": "Redator", "qa_pacote": "Qualidade",
         "retrospectivo": "Aprendizado"}


# --- text --------------------------------------------------------------------

def _abbreviation(token: str) -> bool:
    token = token.strip("([{\"'")
    return bool(token) and not any(ch.isdigit() for ch in token) and (
        "." in token or (token[0].isupper() and len(token) <= 3))


def sentences(text: str) -> list[str]:
    """Split a justification into sentences: a period, question or
    exclamation mark outside brackets, followed by a capital, a digit or a
    quote, and not closing a short capitalised abbreviation (Co., Ry., S.A.)."""
    out, start, depth, i = [], 0, 0, 0
    text = str(text or "")
    while i < len(text):
        ch = text[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch in ".!?" and depth == 0:
            j = i + 1
            while j < len(text) and text[j] in "'\"”’)":
                j += 1
            k = j
            while k < len(text) and text[k].isspace():
                k += 1
            ends = k >= len(text) or (k > j and (text[k].isupper() or
                                                  text[k].isdigit() or
                                                  text[k] in "'\"“‘"))
            previous = re.search(r"([\w.&-]+)$", text[start:i])
            if ends and not (ch == "." and previous and
                             _abbreviation(previous.group(1))):
                out.append(text[start:j].strip())
                start, i = k, k
                continue
        i += 1
    if text[start:].strip():
        out.append(text[start:].strip())
    return out


def split_justification(text: str) -> tuple[list[str], list[str]]:
    """(conclusion, observations): the three sentences just before the first
    marked observation, and each marked passage (a marker sentence and the
    unmarked sentences that follow it)."""
    parts = sentences(text)
    first = next((n for n, s in enumerate(parts) if MARKER.match(s)), len(parts))
    conclusion = parts[max(0, first - 3):first]
    observations: list[str] = []
    for sentence in parts[first:]:
        if MARKER.match(sentence) or not observations:
            observations.append(sentence)
        else:
            observations[-1] += " " + sentence
    return conclusion, observations


# --- sources -------------------------------------------------------------------

def accepted_output(repo: Any, task_id: int) -> dict[str, Any] | None:
    """The latest accepted output file of the task's latest run with one."""
    files = [f for f in repo.function_files(task_id=task_id, direction="output")
             if f["status"] == "accepted"]
    return files[-1] if files else None


def _source_name(repo: Any, unit_id: int, sha: str | None) -> str | None:
    if not sha:
        return None
    for artifact in repo.operation_artifacts(unit_id):
        if artifact["kind"] == "source" and artifact["sha256"] == sha:
            return (artifact["metadata"] or {}).get("display_name") or \
                Path(artifact["path"]).name
    return None


def _claim(repo: Any, unit_id: int, claim_id: int) -> dict[str, Any] | None:
    row = repo.claim(claim_id)
    if not row or row["unit_id"] != unit_id:
        return None
    if row["case_file"]:
        document = json.loads(case_file_store.read_bytes(unit_id, row["case_file"]))
        fields, origin, relative = document["claim"], "arquivo", row["case_file"]
    else:
        fields, origin, relative = row, "indice", None
    value = fields.get("value") or {}
    return {"id": claim_id, "entidade": fields.get("entity"),
            "campos": [[k, v] for k, v in value.items() if k != "tipo_resultado"],
            "natureza": value.get("tipo_resultado"),
            "documento": _source_name(repo, unit_id, fields.get("source_sha256")),
            "documento_sha256": fields.get("source_sha256"),
            "pagina": fields.get("page"), "trecho": fields.get("evidence"),
            "limitacoes": fields.get("limitations") or "",
            "status": row["status"], "origem": origin, "arquivo": relative}


def _claim_ids(repo: Any, task: dict[str, Any], output: dict[str, Any]) -> list[int]:
    if task["output_schema"] in ("adjudicacao", "comparacao_independente"):
        return [int(output["claim_id"])] if output.get("claim_id") else []
    return list(repo.claims_da_tarefa(task["id"]))


# --- the card --------------------------------------------------------------------

def _question(task: dict[str, Any], output: dict[str, Any], claims: list[int]) -> str:
    schema, tid = task["output_schema"], task["id"]
    if schema == "adjudicacao":
        return (f"Aceitar ou recusar o desfecho do Árbitro sobre a afirmação "
                f"{output.get('claim_id')} (tarefa {tid}).")
    if schema == "claims":
        return (f"Aceitar ou recusar as {len(claims)} afirmações registradas pelo "
                f"Examinador na tarefa {tid}.")
    return (f"Aceitar ou recusar o resultado da tarefa {tid} "
            f"({_ROLE.get(task['role'], task['role'])}): {task['title']}.")


def _conclusion(task: dict[str, Any], output: dict[str, Any], claims: list[int]
                ) -> tuple[dict[str, Any], list[str]]:
    schema = task["output_schema"]
    text = output.get("justificativa") or output.get("reason") or \
        output.get("resumo") or ""
    summary, observations = split_justification(text)
    if output.get("resumo"):
        summary = sentences(output["resumo"])
    if isinstance(output.get("observacoes"), list):
        observations = [str(o) for o in output["observacoes"] if str(o).strip()]
    if schema == "adjudicacao":
        decision = _DECISIONS.get(output.get("desfecho"), "Desfecho {d}").format(
            cid=output.get("claim_id"), d=output.get("desfecho"))
    elif schema == "claims":
        decision = f"Registrou {len(claims)} afirmações"
    else:
        decision = "Entregou o resultado da tarefa"
    return {"decisao": decision, "desfecho": output.get("desfecho"),
            "resumo": summary, "justificativa": text}, observations


def _effects(task: dict[str, Any], output: dict[str, Any],
             claims: list[int]) -> dict[str, str]:
    """What Accept and Reject do, as the code does it: Accept moves the task
    to accepted, Reject to refused; neither undoes what the task applied."""
    tid, cid = task["id"], output.get("claim_id")
    nothing_new = "Nenhuma tarefa nova é criada; uma nova análise exige uma nova tarefa."
    undone = "O que esta tarefa já aplicou não é desfeito."
    if task["output_schema"] == "adjudicacao":
        outcome = output.get("desfecho")
        if outcome == "corrigido":
            accept = (f"A tarefa {tid} passa a aceita: vale a correção do Árbitro. "
                      f"A afirmação {cid} fica substituída pela nova afirmação, já "
                      f"registrada e enviada à revisão independente.")
            reject = (f"A tarefa {tid} passa a recusada: a correção não é aceita, "
                      f"mas a substituição da afirmação {cid} já aplicada não é "
                      f"desfeita. {nothing_new}")
        elif outcome == "escalado":
            accept = (f"A tarefa {tid} passa a aceita: o escalonamento aberto pelo "
                      f"Árbitro continua na fila de decisões. A afirmação {cid} "
                      f"não muda.")
            reject = (f"A tarefa {tid} passa a recusada. A afirmação {cid} não "
                      f"muda e o escalonamento já aberto continua na fila. "
                      f"{nothing_new}")
        else:
            accept = (f"A tarefa {tid} passa a aceita: fica registrado que a "
                      f"afirmação {cid} se mantém como está. Nada mais muda no "
                      f"caso.")
            reject = (f"A tarefa {tid} passa a recusada: o desfecho do Árbitro não "
                      f"é aceito. A afirmação {cid} continua ativa como está. "
                      f"{nothing_new}")
    elif task["output_schema"] == "claims":
        accept = (f"A tarefa {tid} passa a aceita: as {len(claims)} afirmações "
                  f"registradas valem para o caso.")
        reject = (f"A tarefa {tid} passa a recusada. As afirmações já registradas "
                  f"não são retiradas por esta decisão. {nothing_new}")
    else:
        accept = (f"A tarefa {tid} passa a aceita: o resultado já aplicado vale "
                  f"para o caso.")
        reject = f"A tarefa {tid} passa a recusada. {undone} {nothing_new}"
    return {"aceitar": accept, "recusar": reject}


def _open_items(repo: Any, unit_id: int, output_sha: str) -> dict[int, int]:
    rows = repo.conn.execute(
        "SELECT id, value FROM claims WHERE unit_id=%s AND value @> %s::jsonb",
        (unit_id, json.dumps({"tipo_resultado": OPEN_ITEM,
                              "origem": {"output_sha256": output_sha}}))).fetchall()
    return {int(r["value"]["origem"]["observacao"]): r["id"] for r in rows}


def card(repo: Any, task_id: int) -> dict[str, Any] | None:
    """The decision card of a task waiting for Renato, or None for any other
    task. Read-only."""
    task = repo.tarefa(task_id)
    if not task or task["status"] != "aguardando_operador":
        return None
    row = accepted_output(repo, task_id)
    if row is None:
        return {"available": False,
                "reason": "Esta tarefa é anterior aos arquivos de saída; o cartão "
                          "não pode ser montado a partir de arquivos. Veja os "
                          "detalhes técnicos abaixo."}
    try:
        document = json.loads(case_file_store.read_bytes(task["unit_id"],
                                                         row["relative"]))
        output = document.get("output") or {}
        claim_ids = _claim_ids(repo, task, output)
        claims = [c for c in (_claim(repo, task["unit_id"], i) for i in claim_ids) if c]
    except case_file_store.CaseFileError as exc:
        return {"available": False,
                "reason": f"Arquivo registrado ilegível ou alterado ({exc.code}); "
                          f"o cartão não é montado."}
    conclusion, observations = _conclusion(task, output, claim_ids)
    recorded = _open_items(repo, task["unit_id"], row["sha256"])
    return {"available": True, "task_id": task_id,
            "pergunta": _question(task, output, claim_ids),
            "afirmacoes": claims, "conclusao": conclusion,
            "observacoes": [{"indice": n, "texto": text,
                             "item_aberto": recorded.get(n)}
                            for n, text in enumerate(observations, start=1)],
            "efeitos": _effects(task, output, claim_ids),
            "fonte": {"saida": row["relative"], "sha256": row["sha256"],
                      "run_id": row["run_id"]}}


# --- one click: an observation becomes an open item -------------------------------

def record_open_item(repo: Any, unit_id: int, task_id: int, index: int,
                     actor: str, note: str) -> int:
    """Record observation `index` of the task's card as a Claim of nature
    `item_aberto`, with its own Case file. Refuses a second record."""
    from src.casefile import case_records
    task = repo.tarefa(task_id)
    if not task or task["unit_id"] != unit_id:
        raise ValueError("task_outside_case")
    current = card(repo, task_id)
    if not current or not current.get("available"):
        raise ValueError("decision_card_not_available")
    observation = next((o for o in current["observacoes"]
                        if o["indice"] == int(index)), None)
    if observation is None:
        raise ValueError("observation_not_found")
    if observation["item_aberto"]:
        raise ValueError("open_item_already_recorded")
    related = current["afirmacoes"][0] if current["afirmacoes"] else None
    row = repo.function_files(run_id=current["fonte"]["run_id"], direction="output",
                              sha256=current["fonte"]["sha256"])[-1]
    run = repo.run(row["run_id"])
    if not run.get("operation_session_id"):
        raise ValueError("open_item_session_unknown")
    output = json.loads(case_file_store.read_bytes(unit_id, row["relative"]))["output"]
    source = (related or {}).get("documento_sha256") or \
        str(output.get("documento", "")).removeprefix("sha256:")
    if not source:
        raise ValueError("open_item_source_unknown")
    value = {"tipo_resultado": OPEN_ITEM, "observacao": observation["texto"],
             "origem": {"task_id": task_id, "run_id": row["run_id"],
                        "output_file": row["relative"], "output_sha256": row["sha256"],
                        "observacao": int(index)},
             "afirmacao_relacionada": related["id"] if related else None,
             "registrado_por": actor, "nota": note}
    claim_id = repo.inserir_claim(
        unit_id=unit_id, claim_type="fact",
        entity=(related or {}).get("entidade") or f"tarefa {task_id}",
        value=value, source_sha256=source,
        page=(related or {}).get("pagina") or str(output.get("pagina") or "n/a"),
        evidence=observation["texto"], confidence="media",
        materiality=repo.claim(related["id"])["materiality"] if related else "media",
        session_id=run["operation_session_id"])
    case_records.write_open_item_file(repo, task, claim_id, row, int(index))
    repo.operation_event("claim.open_item_recorded", actor,
                         {"claim_id": claim_id, "observation": int(index),
                          "output_file": row["relative"]},
                         unit_id=unit_id, task_id=task_id)
    return claim_id
