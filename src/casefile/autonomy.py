"""Autonomous operation: Lot + Job in, deliverable out (issue 13).

Renato declares a Lot (the Cases PLM assigned) and its Job once, with an
envelope: allowed sources, a turn cap and a cost cap per Case, the through
date and, optionally, a deadline. From then on the Coordinator runs each
Case: it opens the Round inside the envelope, advances the stage, accepts
results whose AI dispositions all hold, sends everything else to the
exceptions queue, triggers the Writer and QA, and assembles the package.
Renato sees the exceptions queue and, per Case, the deliverable ready for
release. Release, purchases, external communication, PREP transmission and
submission stay his, each with its own authorization.

Python never compares title values (invariant 2): auto-accept reads the
dispositions the AI heads wrote in their accepted output and review files,
and compares only identities (Claim, document sha256, page). Every
Coordinator decision and every acceptance is a write-once Case file with its
reason (ADR 0001). The exceptions queue is the existing escalations table,
so there is one queue.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.casefile import case_file_store, case_records, decision_card, rounds
from src.casefile.estados import ESTADOS
from src.casefile.training import digest

COORDINATOR = "process:coordenador"
RULE = "autoaccept-v1"
# Sources a Lot declared before issue 17 (no routine) may still name.
LEGACY_SOURCES = ("local", "drive", "countyrecords", "texasfile", "cad", "pacer", "sos")
OPEN_LOT = "c.status NOT IN ('released','superseded')"
STAGE_ORDER = [s for s in ESTADOS if s != "BLOQUEADA"]
OPEN_ITEM_NATURES = ("item_aberto", "decisao_humana")
LAYOUT = ("1. Landman Submitted/Maps", "1. Landman Submitted/Misc. Title Files",
          "1. Landman Submitted/PACER Search", "1. Landman Submitted/SOS Search",
          "1. Landman Submitted/Tax Documents",
          "1. Landman Submitted/Title Documents/Easements, Plats, Oil, gas, mineral leases",
          "1. Landman Submitted/Title Documents/Federal Court",
          "1. Landman Submitted/Title Documents/Mortgages",
          "1. Landman Submitted/Title Documents/Surface")
KINDS = {
    "source_access": "Acesso à fonte (login, credencial ou rede)",
    "paid_document": "Documento ou consulta paga",
    "external_communication": "Comunicação externa",
    "divergence": "Divergência não resolvida pelo Árbitro",
    "insufficient_evidence": "Evidência insuficiente nas fontes permitidas",
    "envelope_exhausted": "Envelope esgotado",
    "case_blocked": "Tarefa bloqueada",
    "open_item": "Item aberto no caso",
    "needs_decision": "Resultado sem disposições para aceite automático",
    "audit_suspended": "Tipo de afirmação suspenso pela revisão por amostra",
    "deliverable_prerequisite": "Pré-requisito do entregável ausente",
    "protocol_pending": "Etapas do protocolo que exigem você",
    "escalation": "Questão levantada por uma função",
}
OPTIONS = {
    "source_access": ["retry_source", "dismiss"],
    "paid_document": ["dismiss"],
    "external_communication": ["acknowledge", "dismiss"],
    "divergence": ["accept", "reject", "re_read", "release_blank", "dismiss"],
    "insufficient_evidence": ["accept", "reject", "re_read", "allow_source",
                              "release_blank", "dismiss"],
    "envelope_exhausted": ["raise_cap", "dismiss"],
    "case_blocked": ["retry", "dismiss"],
    "open_item": ["dismiss", "release_blank"],
    "needs_decision": ["accept", "reject", "dismiss"],
    "audit_suspended": ["accept", "reject"],
    "deliverable_prerequisite": ["dismiss"],
    "protocol_pending": ["dismiss"],
    "escalation": ["dismiss"],
}
REJECT_PRESETS = ("A citação não corresponde à página",
                  "Documento ou página errados",
                  "O raciocínio não decorre da evidência",
                  "É preciso ler outra página")
BLANK_PRESETS = ("Evidência insuficiente nas fontes permitidas",
                 "Documento fora do escopo do tract",
                 "Depende de fonte externa não autorizada")
FAILURE_ORDER = ("audit_suspended", "divergence", "insufficient_evidence",
                 "open_item")
# Exceptions that can still change a Claim: the Writer waits for them, so the
# deliverable is never drafted from Claims still under decision.
CLAIM_BLOCKING = ("divergence", "insufficient_evidence", "needs_decision",
                  "open_item", "case_blocked", "audit_suspended",
                  "deliverable_prerequisite")


# --- lot and envelope ------------------------------------------------------------

def _envelope(raw: dict[str, Any], case: dict[str, Any], spent: float,
              routine: str | None = None) -> dict[str, Any]:
    from src.casefile import routines
    # Issue 17: the envelope is every source the Job lists; RRC never.
    allowed = routines.job_sources(routine) if routine else list(LEGACY_SOURCES)
    sources = list(dict.fromkeys(raw.get("sources") or allowed))
    if set(sources) & routines.FORBIDDEN_SOURCES:
        raise ValueError("envelope_source_forbidden_rrc")
    if not sources or set(sources) - set(allowed):
        raise ValueError("envelope_sources_unknown")
    turns = rounds.validate_cap(raw.get("turn_cap_per_case", 60))
    default_cost = float(case["approved_budget_usd"] or 0) or \
        float(os.environ.get("MINORH_TETO_UNIT_USD", "25"))
    cost = float(raw.get("cost_cap_usd_per_case") or default_cost)
    if not 0 < cost <= 50:
        raise ValueError("envelope_cost_cap_between_zero_and_50_required")
    if cost <= spent:
        raise ValueError("envelope_cost_cap_has_no_remaining_balance")
    through = raw.get("through_date") or case["scope"].get("through_date")
    if not through:
        raise ValueError("envelope_through_date_required")
    date.fromisoformat(str(through))
    deadline = raw.get("deadline")
    if deadline:
        datetime.fromisoformat(str(deadline))
    rate = float(raw.get("audit_rate", 0.10))
    limit = int(raw.get("audit_wrong_limit", 2))
    if not 0 < rate <= 1 or limit < 0:
        raise ValueError("envelope_audit_settings_invalid")
    return {"sources": sources, "turn_cap_per_case": turns,
            "cost_cap_usd_per_case": cost, "through_date": str(through),
            "deadline": deadline, "audit_rate": rate, "audit_wrong_limit": limit}


def _job(raw: dict[str, Any]) -> dict[str, Any]:
    from src.casefile import routines
    plm_job = str(raw.get("plm_job_id") or "").strip()
    if not plm_job:
        raise ValueError("plm_job_id_required")
    # Issue 14: the Job names its routine; there is no default.
    routine = routines.get(raw.get("routine"))
    extra = raw.get("extra_requests") or []
    if isinstance(extra, str):
        extra = [line.strip() for line in extra.splitlines() if line.strip()]
    return {"plm_job_id": plm_job, "routine": routine["id"],
            "deliverable_type": raw.get("deliverable_type") or "surface_runsheet",
            "template_artifact_id": raw.get("template_artifact_id"),
            "package_format": raw.get("package_format") or "plm_standard",
            "extra_requests": [str(x) for x in extra]}


def open_lot_case(repo: Any, unit_id: int) -> dict[str, Any] | None:
    """The Case's place in its open Lot (not yet released), with the Lot."""
    return repo.conn.execute(
        "SELECT c.*, l.job, l.envelope, l.created_at AS lot_created_at "
        "FROM operation_lot_cases c JOIN operation_lots l ON l.id=c.lot_id "
        f"WHERE c.unit_id=%s AND {OPEN_LOT}", (unit_id,)).fetchone()


def create_lot(repo: Any, actor: str, note: str, command_id: str,
               job: dict[str, Any], unit_ids: list[int],
               envelope: dict[str, Any]) -> dict[str, Any]:
    """Declare a Lot once. Each Case is approved for the whole envelope, its
    Round is opened by the Coordinator, and the Case starts running."""
    from src.casefile import routines
    from src.casefile.operations import seed_coordinator, validate_scope
    ids = list(dict.fromkeys(int(u) for u in unit_ids))
    if not ids:
        raise ValueError("lot_cases_required")
    job = _job(job)
    cases = {}
    for uid in ids:
        case = repo.operation_case(uid, lock=True)
        if not case:
            raise ValueError("operation_case_not_registered")
        current = open_lot_case(repo, uid)
        if current and current["status"] != "stopped":
            raise ValueError("case_already_in_an_open_lot")
        if repo.conn.execute(
                "SELECT 1 FROM task_runs r JOIN tasks t ON t.id=r.task_id WHERE "
                "t.unit_id=%s AND r.finished_at IS NULL LIMIT 1", (uid,)).fetchone():
            raise ValueError("pause_and_wait_before_lot")
        cases[uid] = case
    first = cases[ids[0]]
    routine = routines.get(job["routine"])
    stored = _envelope(envelope, first, repo.custo_acumulado(ids[0]), job["routine"])
    lot = repo.conn.execute(
        "INSERT INTO operation_lots(job,envelope,created_by,note,command_id) "
        "VALUES (%s,%s,%s,%s,%s) RETURNING *",
        (json.dumps(job, ensure_ascii=False), json.dumps(stored, ensure_ascii=False),
         actor, note, command_id)).fetchone()
    for uid, case in cases.items():
        previous = open_lot_case(repo, uid)
        if previous:
            # Issue 17: a stopped Lot case is superseded by this declaration;
            # its row, decisions and queue entries stay as history.
            repo.conn.execute(
                "UPDATE operation_lot_cases SET status='superseded',updated_at=now() "
                "WHERE lot_id=%s AND unit_id=%s", (previous["lot_id"], uid))
            _decision(repo, previous["lot_id"], uid, "superseded",
                      f"Renato declarou o lote {lot['id']} para este caso; o lote "
                      f"{previous['lot_id']} (parado: {previous['stop_reason']}) fica como histórico.",
                      {"new_lot_id": lot["id"]})
        env = _envelope(envelope, case, repo.custo_acumulado(uid), job["routine"])
        scope = validate_scope({**case["scope"], "sources": env["sources"],
                                "through_date": env["through_date"],
                                "work_type": routine["work_type"],
                                "status": "approved"})
        approval = {"actor": actor, "note": note, "lot_id": lot["id"],
                    "command_id": command_id, "scope_sha256": digest(scope),
                    "budget_usd": env["cost_cap_usd_per_case"],
                    "turn_cap": env["turn_cap_per_case"],
                    "at": datetime.now(timezone.utc).isoformat()}
        profile = case["profile"]
        if job.get("template_artifact_id"):
            profile = {**profile, "template_artifact_id": int(job["template_artifact_id"])}
        repo.operation_update(uid, scope=scope, profile=profile,
                              approved_budget_usd=env["cost_cap_usd_per_case"],
                              approval=approval, execution_state="running")
        repo.conn.execute(
            "INSERT INTO operation_lot_cases(lot_id,unit_id,turn_cap) VALUES (%s,%s,%s)",
            (lot["id"], uid, env["turn_cap_per_case"]))
        opened = rounds.approve(repo, uid, env["turn_cap_per_case"], COORDINATOR,
                                f"Lote {lot['id']}: envelope de "
                                f"{env['turn_cap_per_case']} turnos", command_id)
        _decision(repo, lot["id"], uid, "open_round",
                  f"Lote {lot['id']} declarado por Renato para o job "
                  f"{job['plm_job_id']}: rodada {opened['number']} aberta com o "
                  f"envelope inteiro de {env['turn_cap_per_case']} turnos, fontes "
                  f"{', '.join(env['sources'])}.",
                  {"round_id": opened["id"], "envelope": env})
        advance(repo, lot["id"], uid, "PLANEJANDO",
                "O Coordenador recebe o caso inteiro dentro do envelope do lote.")
        seed_coordinator(repo, uid, env["cost_cap_usd_per_case"] - repo.custo_acumulado(uid),
                         routine=routine["id"])
        repo.operation_event("lot.case_started", actor,
                             {"lot_id": lot["id"], "job": job["plm_job_id"]}, unit_id=uid)
    return lot


# --- coordinator files ------------------------------------------------------------

TURN_RECORDS = ("stop", "wait_limit", "deliverable_ready")


def turns_by_function(repo: Any, unit_id: int, lot_id: int | None = None) -> dict[str, int]:
    """Issue 14: launched terminal calls (turns) per Function in the Case's
    Lot Rounds, i.e. the Rounds approved since the Lot was declared.
    Issue 15: the independent comparison of every Claim runs on the
    Verifier's family under the Arbiter's card; it is counted on its own
    (`comparacao`), so `arbitro` counts only arbitrations."""
    lot = lot_id or (open_lot_case(repo, unit_id) or {}).get("lot_id")
    if not lot:
        return {}
    rows = repo.conn.execute(
        "SELECT CASE WHEN t.input_json ? 'independent_comparison' THEN 'comparacao' "
        "ELSE t.role END AS role, count(*) AS n FROM operation_terminal_calls c "
        "JOIN task_runs r ON r.id=c.run_id JOIN tasks t ON t.id=r.task_id "
        "JOIN operation_rounds o ON o.id=c.round_id JOIN operation_lots l ON l.id=%s "
        "WHERE t.unit_id=%s AND c.launched_at IS NOT NULL AND o.approved_at >= l.created_at "
        "GROUP BY 1 ORDER BY n DESC, 1", (lot, unit_id)).fetchall()
    return {r["role"]: r["n"] for r in rows}


def _decision(repo: Any, lot_id: int | None, unit_id: int, kind: str,
              reason: str, detail: dict[str, Any] | None = None) -> str:
    """Every Coordinator decision is a write-once Case file with its reason.
    The decisions that close a stretch of work also record the turns each
    Function used (issue 14)."""
    if kind in TURN_RECORDS:
        detail = {**(detail or {}), "turns_by_function": turns_by_function(repo, unit_id, lot_id)}
    document = {"schema": 1, "kind": "coordinator_decision", "decision": kind,
                "decided_by": COORDINATOR, "lot_id": lot_id, "unit_id": unit_id,
                "reason": reason, "detail": detail or {}}
    seq = 1 + repo.conn.execute(
        "SELECT count(*) AS n FROM operation_coordinator_decisions WHERE unit_id=%s",
        (unit_id,)).fetchone()["n"]
    record = case_records._write(
        unit_id, stage=repo.estado_da_unit(unit_id), function="coordenador",
        task=f"lot-{lot_id}" if lot_id else "sem-lote",
        name=f"decision_{seq:04d}_{kind}_{digest(document)[:8]}.json",
        document=document)
    repo.conn.execute(
        "INSERT INTO operation_coordinator_decisions(lot_id,unit_id,kind,relative,sha256) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (unit_id,relative) DO NOTHING",
        (lot_id, unit_id, kind, record.relative, record.sha256))
    repo.operation_event("coordinator." + kind, COORDINATOR,
                         {"reason": reason, "file": record.relative, "lot_id": lot_id},
                         unit_id=unit_id)
    return record.relative


def advance(repo: Any, lot_id: int | None, unit_id: int, target: str,
            reason: str) -> bool:
    """Move the Case's stage forward (never back), recorded with the reason."""
    current = repo.estado_da_unit(unit_id)
    if current not in STAGE_ORDER or \
            STAGE_ORDER.index(current) >= STAGE_ORDER.index(target):
        return False
    repo.transicionar(unit_id, current, target, "coordenador:" + target.lower(),
                      COORDINATOR, reason)
    _decision(repo, lot_id, unit_id, "advance_stage", reason,
              {"from": current, "to": target})
    return True


def _exception(repo: Any, lot_id: int | None, unit_id: int, task_id: int | None,
               kind: str, key: str, question: str,
               detail: dict[str, Any] | None = None, adopt: tuple[int, Any] | None = None
               ) -> int | None:
    """Open an entry in the exceptions queue once per key; returns its id
    when it is new (and records the Coordinator's decision to send it).
    Issue 14: `adopt` = (task id, run start) takes over the entry the worker
    opened for that same failure, so one failure is one queue entry."""
    if repo.conn.execute("SELECT 1 FROM escalations WHERE unit_id=%s AND exception_key=%s",
                         (unit_id, key)).fetchone():
        return None
    worker_entry = repo.conn.execute(
        "SELECT id FROM escalations WHERE unit_id=%s AND task_id=%s AND respondido_em IS NULL "
        "AND exception_key IS NULL AND kind='escalation' AND created_at >= %s "
        "ORDER BY id DESC LIMIT 1", (unit_id, adopt[0], adopt[1])).fetchone() if adopt else None
    if worker_entry:
        row = repo.conn.execute(
            "UPDATE escalations SET motivo=%s,pergunta=%s,opcoes=%s,kind=%s,detail=%s,"
            "lot_id=%s,exception_key=%s WHERE id=%s RETURNING id",
            (KINDS[kind], question, json.dumps(OPTIONS[kind]), kind,
             json.dumps({**(detail or {}), "adopted_worker_entry": True},
                        ensure_ascii=False, default=str), lot_id, key,
             worker_entry["id"])).fetchone()
        _decision(repo, lot_id, unit_id, "exception", f"{KINDS[kind]}: {question}",
                  {"exception_id": row["id"], "kind": kind, "task_id": task_id,
                   "adopted_worker_entry": True})
        return row["id"]
    row = repo.conn.execute(
        "INSERT INTO escalations(unit_id,task_id,motivo,pergunta,opcoes,kind,detail,"
        "lot_id,exception_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (unit_id, exception_key) WHERE exception_key IS NOT NULL "
        "DO NOTHING RETURNING id",
        (unit_id, task_id, KINDS[kind], question,
         json.dumps(OPTIONS[kind]), kind,
         json.dumps(detail or {}, ensure_ascii=False, default=str), lot_id, key)
    ).fetchone()
    if row:
        _decision(repo, lot_id, unit_id, "exception",
                  f"{KINDS[kind]}: {question}",
                  {"exception_id": row["id"], "kind": kind, "task_id": task_id})
    return row["id"] if row else None


def open_exceptions(repo: Any, unit_id: int) -> list[dict[str, Any]]:
    rows = repo.escalonamentos(unit_id, abertos=True)
    for row in rows:
        row["options"] = OPTIONS.get(row.get("kind") or "escalation", ["dismiss"])
        row["label"] = KINDS.get(row.get("kind") or "escalation", row["motivo"])
    return rows


# --- dispositions and auto-accept ---------------------------------------------------

def _output(repo: Any, task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    row = decision_card.accepted_output(repo, task["id"])
    if row is None:
        return None
    document = json.loads(case_file_store.read_bytes(task["unit_id"], row["relative"]))
    return row, document.get("output") or {}


def _claims_for(repo: Any, task: dict[str, Any], output: dict[str, Any]) -> list[int]:
    schema = task["output_schema"]
    if schema == "projecao_celulas":
        return sorted({int(c) for cell in output.get("celulas", [])
                       for c in cell.get("claim_ids", [])})
    if schema == "relatorio_qa":
        latest = repo.deliverables(task["unit_id"], "surface_runsheet")
        if not latest:
            return []
        rows = repo.conn.execute(
            "SELECT claim_ids FROM derived_cells WHERE deliverable_version_id=%s",
            (latest[-1]["id"],)).fetchall()
        return sorted({int(c) for r in rows for c in (r["claim_ids"] or [])})
    ids = list(repo.claims_da_tarefa(task["id"]))
    if schema == "adjudicacao" and output.get("claim_id"):
        ids.append(int(output["claim_id"]))
    return sorted(set(ids))


def _review(repo: Any, unit_id: int, verification: dict[str, Any]) -> dict[str, Any]:
    """A review as its AI head wrote it: from its Case file when it has one,
    otherwise from the index row (labelled)."""
    if verification.get("case_file"):
        document = json.loads(case_file_store.read_bytes(unit_id, verification["case_file"]))
        return {**document["review"], "source": verification["case_file"]}
    return {k: verification.get(k) for k in case_records.REVIEW_FIELDS} | {"source": "indice"}


def _arbiter(repo: Any, unit_id: int, claim_id: int,
             comparison: dict[str, Any] | None) -> dict[str, Any]:
    """The Arbiter's disposition on a Claim: its latest adjudication when one
    exists, otherwise its independent comparison."""
    for task in reversed(repo.tarefas(unit_id)):
        if task["output_schema"] != "adjudicacao" or \
                (task["input_json"].get("claim") or {}).get("id") != claim_id:
            continue
        found = _output(repo, task)
        if found:
            row, output = found
            return {"keep": output.get("desfecho") == "mantido",
                    "value": output.get("desfecho"), "source": row["relative"]}
    if comparison:
        return {"keep": comparison.get("verdict") == "concordancia",
                "value": comparison.get("verdict"), "source": comparison["source"]}
    return {"keep": False, "value": None, "source": None}


def dispositions(repo: Any, task: dict[str, Any]) -> dict[str, Any]:
    """The four dispositions of issue 13 for every active Claim the task's
    result depends on. Reads what the AI heads recorded; compares only
    identities."""
    found = _output(repo, task)
    if found is None:
        return {"ok": False, "kind": "needs_decision", "claims": [],
                "failures": [["needs_decision", "sem arquivo de saída aceito"]]}
    row, output = found
    unit_id = task["unit_id"]
    suspended = {r["claim_type"] for r in repo.conn.execute(
        "SELECT claim_type FROM operation_autoaccept_suspensions").fetchall()}
    open_items = [r["id"] for r in repo.conn.execute(
        "SELECT id FROM claims WHERE unit_id=%s AND status='ativo' AND "
        "value->>'tipo_resultado' = ANY(%s)", (unit_id, list(OPEN_ITEM_NATURES)))]
    claims, failures = [], []
    for claim_id in _claims_for(repo, task, output):
        claim = repo.claim(claim_id)
        if not claim or claim["unit_id"] != unit_id or claim["status"] != "ativo":
            continue
        reviews = repo.verificacoes_do_claim(claim_id)
        blind = [v for v in reviews if (v["comparison"] or {}).get("stage") == "blind_extraction"]
        valid = [v for v in reviews if v.get("status", "valida") == "valida"
                 and (v["comparison"] or {}).get("ai_judgment")]
        comparison = _review(repo, unit_id, valid[-1]) if valid else None
        verdict = comparison.get("verdict") if comparison else None
        compared = (comparison or {}).get("verifier_value") or {}
        verifier = {"concurs": bool(blind) and verdict == "concordancia",
                    "value": verdict, "blind_extraction": bool(blind),
                    "source": (comparison or {}).get("source")}
        citation = {"matches": bool(str(compared.get("quote") or "").strip())
                    and compared.get("source_sha256") == claim["source_sha256"]
                    and str(compared.get("page")) == str(claim["page"]),
                    "quote": compared.get("quote"), "page": compared.get("page")}
        arbiter = _arbiter(repo, unit_id, claim_id, comparison)
        entry = {"claim_id": claim_id, "claim_type": claim["claim_type"],
                 "claim_file": claim["case_file"], "arbiter": arbiter,
                 "verifier": verifier, "citation": citation}
        claims.append(entry)
        if claim["claim_type"] in suspended:
            failures.append(["audit_suspended", claim_id])
        if not arbiter["keep"] or verdict == "divergencia":
            failures.append(["divergence", claim_id])
        elif not verifier["concurs"] or not citation["matches"]:
            failures.append(["insufficient_evidence", claim_id])
    if open_items:
        failures.append(["open_item", open_items])
    if not claims:
        return {"ok": False, "kind": "needs_decision", "claims": [], "output": row,
                "open_items": open_items,
                "failures": [["needs_decision", "nenhuma afirmação ativa a conferir"]]}
    kind = next((k for k in FAILURE_ORDER if any(f[0] == k for f in failures)), None)
    return {"ok": not failures, "kind": kind, "claims": claims, "failures": failures,
            "open_items": open_items, "output": row}


def card_summary(card: dict[str, Any] | None) -> str:
    """The decision card in one paragraph: what was decided, the Function's
    conclusion and its short reasoning (ticket 12)."""
    if not card or not card.get("available"):
        return "Sem cartão de decisão montado a partir de arquivos."
    parts = [card["pergunta"], card["conclusao"]["decisao"] + "."]
    parts.extend(card["conclusao"]["resumo"])
    for claim in card.get("afirmacoes", []):
        parts.append(f"Afirmação {claim['id']}: {claim.get('documento') or ''} "
                     f"página {claim.get('pagina')}.")
    items = [o["item_aberto"] for o in card.get("observacoes", []) if o.get("item_aberto")]
    if items:
        parts.append("Itens abertos registrados das observações: "
                     + ", ".join(str(i) for i in items) + ".")
    return " ".join(p for p in parts if p)


def _failure_text(verdict: dict[str, Any]) -> str:
    """Which of the four dispositions failed, as the AI heads recorded them."""
    parts = []
    for claim in verdict["claims"]:
        parts.append(f"afirmação {claim['claim_id']}: Árbitro {claim['arbiter']['value'] or 'sem disposição'}, "
                     f"Verificador {claim['verifier']['value'] or 'sem comparação'}"
                     + ("" if claim["verifier"]["blind_extraction"] else " (sem extração cega)")
                     + (", citação confere" if claim["citation"]["matches"] else ", citação não confere"))
    if verdict.get("open_items"):
        parts.append("itens abertos no caso: " + ", ".join(str(i) for i in verdict["open_items"]))
    if any(f[0] == "audit_suspended" for f in verdict["failures"]):
        parts.append("tipo de afirmação suspenso pela revisão por amostra")
    if not parts:
        parts.append(str(verdict["failures"][0][1]) if verdict["failures"] else "sem detalhe")
    return "; ".join(parts) + "."


def _reason(card: dict[str, Any] | None, verdict: dict[str, Any]) -> str:
    parts = [card_summary(card)]
    parts.append("Aceito pelo Coordenador (regra " + RULE + "): " + "; ".join(
        f"afirmação {c['claim_id']}: Árbitro {c['arbiter']['value']}, "
        f"Verificador {c['verifier']['value']}, citação confere"
        for c in verdict["claims"]) + "; nenhum item aberto no caso.")
    return " ".join(p for p in parts if p)


def _accept(repo: Any, lot: dict[str, Any], task: dict[str, Any],
            verdict: dict[str, Any]) -> str:
    card = decision_card.card(repo, task["id"])
    reason = _reason(card, verdict)
    output_row = verdict["output"]
    document = {"schema": 1, "kind": "acceptance", "accepted_by": "coordinator",
                "rule": RULE, "lot_id": lot["lot_id"], "unit_id": task["unit_id"],
                "task_id": task["id"], "run_id": output_row["run_id"],
                "output_file": {"relative": output_row["relative"],
                                "sha256": output_row["sha256"]},
                "dispositions": verdict["claims"], "open_items": verdict["open_items"],
                "reason": reason}
    record = case_records._write(
        task["unit_id"], stage=repo.estado_da_unit(task["unit_id"]),
        function=task["role"], task=task["id"],
        name=f"acceptance_run{output_row['run_id']}_{digest(document)[:8]}.json",
        document=document)
    rate = float(lot["envelope"].get("audit_rate", 0.10))
    sampled = int(record.sha256[:8], 16) < rate * 0x100000000
    repo.conn.execute(
        "INSERT INTO operation_acceptances(lot_id,unit_id,task_id,claim_types,relative,"
        "sha256,sampled) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (lot["lot_id"], task["unit_id"], task["id"],
         sorted({c["claim_type"] for c in verdict["claims"]}), record.relative,
         record.sha256, sampled))
    repo.transicionar_tarefa(task["id"], ("aguardando_operador",), "aceita",
                             COORDINATOR, reason[:2000])
    repo.operation_event("task.auto_accepted", COORDINATOR,
                         {"file": record.relative, "rule": RULE, "sampled": sampled},
                         unit_id=task["unit_id"], task_id=task["id"])
    return record.relative


# --- the Coordinator's step ------------------------------------------------------------

def _stop(repo: Any, lc: dict[str, Any], reason: str, question: str,
          key: str, exception: bool = True, adopt: tuple[int, Any] | None = None) -> None:
    repo.conn.execute(
        "UPDATE operation_lot_cases SET status='stopped',stop_reason=%s,resume_at=NULL,"
        "updated_at=now() WHERE lot_id=%s AND unit_id=%s", (reason, lc["lot_id"], lc["unit_id"]))
    repo.operation_update(lc["unit_id"], execution_state="waiting")
    new = _exception(repo, lc["lot_id"], lc["unit_id"], None, "envelope_exhausted",
                     key, question, {"reason": reason}, adopt=adopt) if exception else None
    if new or not exception:
        _decision(repo, lc["lot_id"], lc["unit_id"], "stop", question, {"reason": reason})


def _envelope_stop(repo: Any, lc: dict[str, Any]) -> tuple[str, str, str] | None:
    uid, env = lc["unit_id"], lc["envelope"]
    state = rounds.state(repo, uid)
    if state is None:
        return ("envelope_round_missing", "O caso não tem rodada aberta no lote.", "round:none")
    if state["turns_remaining"] <= 0 or (not state["open"] and
                                         state["close_reason"] == rounds.CAP_REACHED):
        return ("envelope_turns",
                f"Os {state['turn_cap']} turnos da rodada {state['number']} foram usados.",
                f"turns:round{state['id']}")
    spent, cap = repo.custo_acumulado(uid), float(repo.operation_case(uid)["approved_budget_usd"])
    if spent >= cap:
        return ("envelope_cost", f"Custo conhecido US$ {spent:.2f} atingiu o teto US$ {cap:.2f}.",
                f"cost:{cap}")
    deadline = env.get("deadline")
    if deadline and datetime.now(timezone.utc) > datetime.fromisoformat(str(deadline)).astimezone(timezone.utc):
        return ("envelope_deadline", f"O prazo do lote ({deadline}) passou.", f"deadline:{deadline}")
    return None


def _claims_in_flight(repo: Any, unit_id: int) -> set[int]:
    """Claims that a planned, ready or running task (or a queued follow-up)
    is still reviewing: their dispositions are not final yet."""
    rows = repo.conn.execute(
        "SELECT input_json FROM tasks WHERE unit_id=%s AND status IN "
        "('planejada','pronta','em_execucao') UNION ALL SELECT input_json FROM "
        "operation_followups WHERE unit_id=%s AND task_id IS NULL", (unit_id, unit_id)).fetchall()
    ids = set()
    for row in rows:
        data = row["input_json"] or {}
        for value in (data.get("claim_id"), (data.get("claim") or {}).get("id")):
            if isinstance(value, int):
                ids.add(value)
    return ids


def _runnable(repo: Any, unit_id: int) -> bool:
    return bool(repo.conn.execute(
        "SELECT 1 FROM tasks WHERE unit_id=%s AND status IN ('pronta','em_execucao') "
        "UNION ALL SELECT 1 FROM operation_followups WHERE unit_id=%s AND task_id IS NULL "
        "LIMIT 1", (unit_id, unit_id)).fetchone())


def _lot_task(repo: Any, unit_id: int, lot_id: int, kind: str) -> dict[str, Any] | None:
    rows = [t for t in repo.tarefas(unit_id)
            if t["ref"].startswith(f"lote-{lot_id}-{kind}-")]
    return rows[-1] if rows else None


def _create_phase_task(repo: Any, lot: dict[str, Any], kind: str,
                       previous: dict[str, Any] | None = None) -> dict[str, Any]:
    from src.casefile import orquestracao
    uid, lot_id = lot["unit_id"], lot["lot_id"]
    n = 1 + sum(t["ref"].startswith(f"lote-{lot_id}-{kind}-") for t in repo.tarefas(uid))
    job = lot["job"]
    if kind == "redator":
        row = {"role": "redator", "output_schema": "projecao_celulas",
               "title": f"Montar o entregável do lote {lot_id} ({job['deliverable_type']})",
               "acceptance": "Template sem amostra; cada célula cita afirmações revisadas "
                             "ou é branco declarado com motivo e responsável."}
    else:
        row = {"role": "qa_pacote", "output_schema": "relatorio_qa",
               "title": f"Conferir o entregável do lote {lot_id}",
               "acceptance": "Relatório de QA da versão exata; observação, não aprovação."}
    orquestracao.registrar_versoes(repo)
    # A Lot declared before issue 14 has no routine; its pack stays the surface one.
    created = repo.criar_tarefas(uid, [{
        **row, "ref": f"lote-{lot_id}-{kind}-{n}", "pack": repo.operation_pack(uid),
        "input_json": {"operation": True, "lot_id": lot_id, "job": job,
                       "lacunas_declaradas": declared_gaps(repo, uid, lot_id),
                       **({"tentativa_anterior": previous} if previous else {})},
        "depends_on_refs": [], "budget_usd": 1.0, "priority": 0,
        "verificacao": "operador"}], COORDINATOR)[0]
    repo.promover_prontas(uid, COORDINATOR)
    return created


PHASE_ATTEMPTS = 2


def _phase_kind(lc: dict[str, Any], task: dict[str, Any]) -> str | None:
    for kind in ("redator", "qa"):
        if task["ref"].startswith(f"lote-{lc['lot_id']}-{kind}-"):
            return kind
    return None


def _phase_retry_left(repo: Any, lc: dict[str, Any], task: dict[str, Any]) -> bool:
    kind = _phase_kind(lc, task)
    if not kind:
        return False
    rows = [t for t in repo.tarefas(lc["unit_id"]) if t["ref"].startswith(f"lote-{lc['lot_id']}-{kind}-")]
    return any(t["id"] > task["id"] for t in rows) or len(rows) < PHASE_ATTEMPTS


def _phase_retry(repo: Any, lc: dict[str, Any], task: dict[str, Any], last: dict[str, Any],
                 reason: str) -> bool:
    """A refused Writer or QA task is the Coordinator's own phase: it gets a
    fresh attempt with the failure in its input (at most PHASE_ATTEMPTS per
    Lot), not a replan and not a queue item."""
    kind = _phase_kind(lc, task)
    if not kind or not _phase_retry_left(repo, lc, task):
        return False
    uid = lc["unit_id"]
    rows = [t for t in repo.tarefas(uid) if t["ref"].startswith(f"lote-{lc['lot_id']}-{kind}-")]
    repo.conn.execute(
        "UPDATE escalations SET resposta=%s,respondido_por=%s,respondido_em=now(),resolution=%s "
        "WHERE unit_id=%s AND task_id=%s AND respondido_em IS NULL",
        ("O Coordenador repete a etapa com a falha na entrada.", COORDINATOR,
         json.dumps({"option": "phase_retry", "rule": RULE}), uid, task["id"]))
    if any(t["id"] > task["id"] for t in rows):
        return True
    errors = [str(e) for e in (last.get("validation_errors") or [])[:3]]
    created = _create_phase_task(repo, lc, kind, {"task_id": task["id"], "motivo": reason or "recusada",
                                                  "erros": errors})
    _decision(repo, lc["lot_id"], uid, "phase_retry",
              f"A tarefa {task['id']} ({task['title']}) foi recusada ({reason}); o Coordenador "
              f"cria a tarefa {created['id']} com a falha na entrada "
              f"({len(rows) + 1} de {PHASE_ATTEMPTS} tentativas da etapa).",
              {"task_id": task["id"], "new_task_id": created["id"], "errors": errors})
    return True


def _writer_prerequisites(repo: Any, unit_id: int) -> list[str]:
    profile = repo.operation_case(unit_id)["profile"]
    missing = []
    if not profile.get("template_artifact_id"):
        missing.append("template do PLM não selecionado")
    if not profile.get("lead_example_artifact_id"):
        missing.append("exemplar do Lead/PM não selecionado")
    if profile.get("sample_data_clearance") not in ("blank_template_confirmed",
                                                    "clear_declared_cells"):
        missing.append("limpeza dos dados de amostra do template não confirmada")
    return missing


# --- issue 17: research every Job source before anything reaches the queue -----------

RESEARCHABLE = ("divergence", "insufficient_evidence", "open_item")
LOT_QUEUE_KINDS = ("source_access", "paid_document", "external_communication",
                   "protocol_pending")


def _lot_queue(repo: Any, lc: dict[str, Any]) -> list[dict[str, Any]]:
    """This Lot's queue: entries it opened, and entries opened after it was
    declared. Older entries stay on the Case as history outside it."""
    return [e for e in open_exceptions(repo, lc["unit_id"])
            if e.get("lot_id") == lc["lot_id"] or
            (e.get("lot_id") is None and e["created_at"] >= lc["lot_created_at"])]


def _first_lot_at(repo: Any, unit_id: int) -> Any:
    return repo.conn.execute(
        "SELECT min(l.created_at) AS at FROM operation_lot_cases c JOIN operation_lots l "
        "ON l.id=c.lot_id WHERE c.unit_id=%s", (unit_id,)).fetchone()["at"]


def _outside_lot(repo: Any, task: dict[str, Any]) -> bool:
    """Learning is never accepted inside a Lot (invariant 7), and a result
    that was already waiting for Renato before any Lot stays his."""
    if task["role"] == "retrospectivo" or task["output_schema"] == "fichas_candidatas":
        return True
    first = _first_lot_at(repo, task["unit_id"])
    return first is not None and task["updated_at"] < first


def _probe(repo: Any, lc: dict[str, Any], source: str) -> str | None:
    """A source gated by login, payment or network is tried once per Case
    (and again after Renato answers its queue item), with no model call.
    Returns the block, or None when the Researcher can use it."""
    from src.casefile import routines, source_adapters
    if routines.access(source) == "public":
        return None
    uid = lc["unit_id"]
    generation = repo.conn.execute(
        "SELECT count(*) AS n FROM escalations WHERE unit_id=%s AND lot_id=%s AND "
        "exception_key LIKE %s AND respondido_em IS NOT NULL",
        (uid, lc["lot_id"], f"source:{source}:%")).fetchone()["n"]
    request = {"kind": "access_probe", "source": source, "lot_id": lc["lot_id"],
               "generation": generation}
    job = repo.operation_source_request(uid, source, digest(request), request,
                                        impact=f"Sondagem de acesso do lote {lc['lot_id']}")
    if job["status"] == "blocked":
        return job["receipt"].get("reason") or "blocked"
    if job["status"] == "complete":
        return None
    case = repo.operation_case(uid)
    try:
        if routines.access(source) == "paid":
            raise source_adapters.SourceUnavailable("paid_source:" + source)
        if source == "terrell_cad":
            source_adapters.cad_view(case, {"terms": []})
        elif source == "drive":
            source_adapters.drive_catalog(case, {"terms": []})
        else:
            recipe = (case["profile"].get("source_recipes") or {}).get(source) or {}
            if not recipe.get("verified_by"):
                raise source_adapters.SourceUnavailable(
                    f"login_required:{source}:verified_recipe_and_operator_session_missing")
        repo.operation_source_result(job["id"], "complete",
                                     {"reachable": True, "source": source})
        return None
    except source_adapters.SourceUnavailable as exc:
        reason = str(exc)
        repo.operation_source_result(job["id"], "blocked", {
            "blocked": True, "reason": reason, "source": source, "owner": "Renato",
            "access": source_adapters.blocked_access(source, reason)})
        return reason


def _access_entry(repo: Any, lc: dict[str, Any], source: str, reason: str,
                  claim_ids: list[int]) -> None:
    from src.casefile import routines, source_adapters
    access = source_adapters.blocked_access(source, reason)
    generation = repo.conn.execute(
        "SELECT count(*) AS n FROM escalations WHERE unit_id=%s AND lot_id=%s AND "
        "exception_key LIKE %s AND respondido_em IS NOT NULL",
        (lc["unit_id"], lc["lot_id"], f"source:{source}:%")).fetchone()["n"]
    name = routines.label(source)
    question = {
        "paid": f"{name} é fonte paga: autorizar a compra ou consulta com o custo apresentado, "
                "ou manter a lacuna declarada.",
        "network": f"{name} não responde desta máquina ({reason}). Fornecer a rede (VPN) ou "
                   "manter a lacuna declarada.",
    }.get(access, f"{name} exige login ou credencial do operador ({reason}). Entrar na sessão "
                  "ou manter a lacuna declarada.")
    _exception(repo, lc["lot_id"], lc["unit_id"], None,
               "paid_document" if access == "paid" else "source_access",
               f"source:{source}:g{generation}", question,
               {"source": source, "reason": reason, "access": access, "claims": claim_ids})


def _lot_tasks(repo: Any, lc: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    prefix = f"lote-{lc['lot_id']}-{kind}-"
    return [t for t in repo.tarefas(lc["unit_id"]) if t["ref"].startswith(prefix)]


TERMINAL = ("aceita", "recusada", "cancelada")


def _claim_brief(repo: Any, cid: int, reason: str) -> dict[str, Any]:
    claim = repo.claim(cid)
    return {"id": cid, "entidade": claim["entity"], "valor": claim["value"],
            "documento": "sha256:" + claim["source_sha256"], "pagina": claim["page"],
            "limitacoes": claim.get("limitations"), "motivo": reason}


def _research_or_gap(repo: Any, lc: dict[str, Any], needing: dict[int, str]) -> str:
    """For Claims that need another source: research every reachable Job
    source not yet tried for them; re-examine once with the documents found;
    then declare the gap with each source's outcome. Never a queue item."""
    from src.casefile import routines
    uid, lot_id = lc["unit_id"], lc["lot_id"]
    sources = [s for s in lc["envelope"].get("sources", []) if s not in routines.FORBIDDEN_SOURCES]
    research = _lot_tasks(repo, lc, "pesquisa")
    reexam_ids = {t["id"] for t in _lot_tasks(repo, lc, "reexame")}
    state: dict[tuple[int, str], str] = {}
    for cid in needing:
        origin = repo.conn.execute("SELECT task_id FROM task_claims WHERE claim_id=%s", (cid,)).fetchone()
        if origin and origin["task_id"] in reexam_ids:
            # A Claim born of a re-examination already had every source tried.
            for source in sources:
                state[(cid, source)] = f"pesquisada antes do reexame da tarefa {origin['task_id']}"
    for t in research:
        for cid in t["input_json"].get("claim_ids", []):
            state[(cid, t["input_json"].get("fonte"))] = (
                f"pesquisada na tarefa {t['id']} ({t['status']})" if t["status"] in TERMINAL
                else "in_flight")
    blocked, busy = {}, False
    for source in sources:
        reason = _probe(repo, lc, source)
        if reason:
            blocked[source] = reason
            _access_entry(repo, lc, source, reason, sorted(needing))
            continue
        todo = [c for c in needing if (c, source) not in state]
        if todo:
            n = 1 + sum(t["input_json"].get("fonte") == source for t in research)
            repo.criar_tarefas(uid, [{
                "ref": f"lote-{lot_id}-pesquisa-{source}-{n}", "role": "pesquisador",
                "pack": repo.operation_pack(uid), "output_schema": "resultado_pesquisa",
                "title": f"Pesquisar em {routines.label(source)} para {len(todo)} afirmação(ões)",
                "acceptance": "Fonte pesquisada com termos, intervalo e resultados completos; "
                              "documentos públicos pertinentes capturados; buscas negativas com limites.",
                "input_json": {"operation": True, "lot_id": lot_id, "fonte": source,
                               "claim_ids": todo,
                               "afirmacoes": [_claim_brief(repo, c, needing[c]) for c in todo],
                               "instrucao": f"Use pesquisar_fonte(fonte='{source}') com as partes, "
                                            "abstracts, referências e descrições destas afirmações. "
                                            "Capture com capturar_preview os documentos públicos "
                                            "pertinentes. Registre o que não foi encontrado com os "
                                            "limites da fonte. Não conclua title."},
                "depends_on_refs": [], "budget_usd": 1.0, "priority": 0,
                "verificacao": "nenhuma"}], COORDINATOR)
            repo.promover_prontas(uid, COORDINATOR)
            _decision(repo, lot_id, uid, "research",
                      f"{len(todo)} afirmação(ões) precisam de outra fonte; o Pesquisador vai a "
                      f"{routines.label(source)} antes de qualquer item na fila.",
                      {"source": source, "claims": todo})
            busy = True
        elif any(state.get((c, source)) == "in_flight" for c in needing):
            busy = True
    if busy:
        return "researching"
    found = {}
    for t in research:
        docs = [a for a in repo.operation_artifacts(uid, "source") if a.get("task_id") == t["id"]]
        for cid in t["input_json"].get("claim_ids", []):
            if cid in needing and docs:
                found.setdefault(cid, []).extend(docs)
    reexams = _lot_tasks(repo, lc, "reexame")
    covered = {c: t for t in reexams for c in t["input_json"].get("claim_ids", [])}
    if any(covered[c]["status"] not in TERMINAL for c in needing if c in covered):
        return "researching"
    fresh = [c for c in needing if c in found and c not in covered and
             not any((c, s) in state and state[(c, s)].startswith("pesquisada antes do reexame")
                     for s in sources)]
    if fresh:
        docs = {a["id"]: a for c in fresh for a in found[c]}
        repo.criar_tarefas(uid, [{
            "ref": f"lote-{lot_id}-reexame-{1 + len(reexams)}", "role": "examinador",
            "pack": repo.operation_pack(uid), "output_schema": "claims",
            "title": f"Reexaminar {len(fresh)} afirmação(ões) com os documentos novos",
            "acceptance": "Afirmações com documento, página e trecho dos documentos novos; o que "
                          "seguir sem prova fica como item aberto com motivo.",
            "input_json": {"operation": True, "lot_id": lot_id, "claim_ids": fresh,
                           "afirmacoes": [_claim_brief(repo, c, needing[c]) for c in fresh],
                           "documentos_novos": [{"artifact_id": a["id"], "documento": "sha256:" + a["sha256"],
                                                 "nome": a["metadata"].get("display_name")} for a in docs.values()]},
            "depends_on_refs": [], "budget_usd": 1.0, "priority": 0,
            "verificacao": "obrigatoria_e_operador"}], COORDINATOR)
        repo.promover_prontas(uid, COORDINATOR)
        _decision(repo, lot_id, uid, "reexamine",
                  f"A pesquisa trouxe {len(docs)} documento(s) novo(s); o Examinador reexamina "
                  f"{len(fresh)} afirmação(ões).", {"claims": fresh, "documents": sorted(docs)})
        return "researching"
    for cid in needing:
        if repo.claim(cid)["status"] != "ativo":
            continue
        if cid in covered and covered[cid]["status"] == "aceita":
            repo.atualizar_claim_status(uid, cid, "retirado", None,
                                        nota=f"Substituída pelo reexame da tarefa {covered[cid]['id']} "
                                             f"(lote {lot_id}).")
            _decision(repo, lot_id, uid, "superseded_by_reexam",
                      f"A afirmação {cid} foi reexaminada com documentos novos na tarefa "
                      f"{covered[cid]['id']}.", {"claim_id": cid, "task_id": covered[cid]["id"]})
            continue
        outcomes = {s: (f"bloqueada: {blocked[s]}" if s in blocked else state.get((cid, s), "não tentada"))
                    for s in sources}
        reason = (f"Lacuna declarada: {needing[cid]}. Todas as fontes do job foram tentadas: "
                  + "; ".join(f"{routines.label(s)} — {o}" for s, o in outcomes.items()) + ".")
        repo.atualizar_claim_status(uid, cid, "retirado", None, nota=reason[:1500])
        _close_claim_escalations(repo, uid, cid, reason)
        claim = repo.claim(cid)
        _decision(repo, lot_id, uid, "declared_gap", reason,
                  {"claim_id": cid, "entity": claim["entity"], "value": claim["value"],
                   "sources": outcomes})
    return "gaps_declared"


def _close_claim_escalations(repo: Any, unit_id: int, cid: int, reason: str) -> None:
    """Questions opened about a Claim before this rule close with its gap."""
    tasks = [r["id"] for r in repo.conn.execute(
        "SELECT id FROM tasks WHERE unit_id=%s AND (input_json->'claim'->>'id' = %s "
        "OR input_json->>'claim_id' = %s)", (unit_id, str(cid), str(cid)))]
    if tasks:
        repo.conn.execute(
            "UPDATE escalations SET resposta=%s,respondido_por=%s,respondido_em=now(),resolution=%s "
            "WHERE unit_id=%s AND respondido_em IS NULL AND kind='escalation' AND task_id = ANY(%s)",
            (reason[:4000], COORDINATOR, json.dumps({"option": "declared_gap", "claim_id": cid}),
             unit_id, tasks))


LOT_ESCALATION_KINDS = {"credencial": "source_access", "documento_pago": "paid_document",
                        "comunicacao_externa": "external_communication"}


def lot_escalation(repo: Any, task: dict[str, Any], tipo: str, motivo: str, pergunta: str,
                   evidence: dict[str, Any]) -> int | None:
    """Issue 17: inside a Lot a Function may only ask for a credential, a paid
    document or an external communication. Anything else is researched in
    the Job's sources or shipped as a declared gap."""
    lc = open_lot_case(repo, task["unit_id"])
    if tipo not in LOT_ESCALATION_KINDS:
        raise ValueError("lot_queue_only_credencial_documento_pago_comunicacao_externa: pesquise "
                         "as fontes do job com pesquisar_fonte ou registre a lacuna na sua saída")
    kind = LOT_ESCALATION_KINDS[tipo]
    question = pergunta + (("\nEvidência: " + json.dumps(evidence, ensure_ascii=False)) if evidence else "")
    return _exception(repo, lc["lot_id"], task["unit_id"], task["id"], kind,
                      f"tool:{task['id']}:{digest({'tipo': tipo, 'q': question})[:16]}",
                      question, {"motivo": motivo, "tipo": tipo, "evidence": evidence})


def declared_gaps(repo: Any, unit_id: int, lot_id: int) -> list[dict[str, Any]]:
    rows = repo.conn.execute(
        "SELECT relative FROM operation_coordinator_decisions WHERE unit_id=%s AND lot_id=%s "
        "AND kind='declared_gap' ORDER BY id", (unit_id, lot_id)).fetchall()
    gaps = []
    for row in rows:
        document = json.loads(case_file_store.read_bytes(unit_id, row["relative"]))
        gaps.append({"claim_id": document["detail"].get("claim_id"),
                     "entity": document["detail"].get("entity"),
                     "reason": document["reason"], "file": row["relative"]})
    return gaps


def _failing_claims(verdict: dict[str, Any]) -> dict[int, str]:
    needing = {}
    by_id = {c["claim_id"]: c for c in verdict["claims"]}
    for kind, value in verdict["failures"]:
        if kind in ("divergence", "insufficient_evidence") and isinstance(value, int):
            c = by_id.get(value, {})
            needing[value] = (f"Árbitro {(c.get('arbiter') or {}).get('value') or 'sem disposição'}, "
                              f"Verificador {(c.get('verifier') or {}).get('value') or 'sem comparação'}")
        elif kind == "open_item":
            for cid in value:
                needing.setdefault(cid, "item aberto")
    return needing


MAX_REPLANS = 3


def _refusal_reason(task: dict[str, Any], last: dict[str, Any], reason: str) -> str:
    """What the re-planning Coordinator needs to plan differently: the stop,
    the contract the Function had to meet and the validation errors."""
    from src.casefile.runtime import ARCHIVIST_CONTRACT
    errors = "; ".join(str(e) for e in (last.get("validation_errors") or [])[:3])
    contract = ARCHIVIST_CONTRACT if task["role"] == "arquivista" else \
        f"esquema exigido {task['output_schema']}"
    return f"{reason or 'recusada'}: nenhuma entrega válida nas tentativas ({errors}); {contract}"


def _replans(repo: Any, lc: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in repo.tarefas(lc["unit_id"]) if t["role"] == "coordenador"
            and (t["input_json"] or {}).get("replanejar_apos", {}).get("lot_id") == lc["lot_id"]]


def _replan(repo: Any, lc: dict[str, Any], task: dict[str, Any], last: dict[str, Any],
            reason: str) -> bool:
    """Issue 17: a refused task in a Lot is not a question for Renato. Its
    pending dependents are cancelled and the Coordinator plans again with the
    failure in its input; at most MAX_REPLANS times per Lot."""
    from src.casefile import agentes, orquestracao, routines
    uid, lot_id = lc["unit_id"], lc["lot_id"]
    done = _replans(repo, lc)
    if any(t["input_json"]["replanejar_apos"].get("task_id") == task["id"] for t in done):
        return True
    if len(done) >= MAX_REPLANS:
        return False
    cancelled, frontier = [], {task["id"]}
    # The new plan covers all remaining work: earlier plans' pending tasks go.
    for t in _plan_tasks(repo, lc):
        if t["status"] in ("planejada", "pronta"):
            repo.transicionar_tarefa(t["id"], (t["status"],), "cancelada", COORDINATOR,
                                     "O Coordenador replaneja todo o trabalho restante do lote.")
            cancelled.append(t["id"])
            frontier.add(t["id"])
    while frontier:
        nxt = set()
        for t in repo.tarefas(uid):
            if t["status"] in ("planejada", "pronta") and frontier & set(t["depends_on"] or []):
                repo.transicionar_tarefa(t["id"], (t["status"],), "cancelada", COORDINATOR,
                                         f"Depende da tarefa {task['id']}, recusada; o Coordenador replaneja.")
                cancelled.append(t["id"])
                nxt.add(t["id"])
        frontier = nxt
    repo.conn.execute(
        "UPDATE escalations SET resposta=%s,respondido_por=%s,respondido_em=now(),resolution=%s "
        "WHERE unit_id=%s AND task_id=%s AND respondido_em IS NULL",
        ("O Coordenador replaneja sem esta tarefa.", COORDINATOR,
         json.dumps({"option": "replan", "rule": RULE}), uid, task["id"]))
    case = repo.operation_case(uid)
    routine = (lc["job"] or {}).get("routine")
    chosen = routines.get(routine) if routine else None
    role = next(f for f in agentes.carregar() if f.tipo == "Role" and f.nome == "coordenador")
    orquestracao.registrar_versoes(repo)
    repo.criar_tarefas(uid, [{
        "ref": f"lote-{lot_id}-replano-{len(done) + 1}", "role": "coordenador",
        "pack": repo.operation_pack(uid), "output_schema": role.front["saida_esquema"],
        "title": "Replanejar o trabalho restante depois de uma tarefa recusada",
        "acceptance": "Cobrir as pendências atuais sem repetir a tarefa recusada; usar apenas "
                      "escopo, fontes e orçamento aprovados.",
        "input_json": {"operation": True, "scope": case["scope"],
                       "operation_revision": case["revision"],
                       **({"routine": {k: chosen[k] for k in ("id", "pack", "label")}} if chosen else {}),
                       "replanejar_apos": {"lot_id": lot_id, "task_id": task["id"], "ref": task["ref"],
                                           "title": task["title"], "role": task["role"],
                                           "motivo": reason, "dependentes_cancelados": cancelled}},
        "budget_usd": 1.0, "verificacao": "operador", "depends_on_refs": [], "priority": 0,
        "pendencias": []}], COORDINATOR)
    repo.promover_prontas(uid, COORDINATOR)
    _decision(repo, lot_id, uid, "replan",
              f"A tarefa {task['id']} ({task['title']}) foi recusada ({reason}). O Coordenador "
              f"cancela {len(cancelled)} tarefa(s) que dependiam dela e replaneja "
              f"({len(done) + 1} de {MAX_REPLANS}).",
              {"refused_task": task["id"], "cancelled": cancelled})
    return True


def _plan_tasks(repo: Any, lc: dict[str, Any]) -> list[dict[str, Any]]:
    """Tasks the Coordinator's plans created in this Lot (not the Lot's own
    research, re-examination, Writer, QA or follow-ups)."""
    return [t for t in repo.tarefas(lc["unit_id"]) if t["created_by"] == COORDINATOR
            and t["role"] != "coordenador" and not t["ref"].startswith("lote-")
            and t["created_at"] >= lc["lot_created_at"]]


def _supersede_older_plan_tasks(repo: Any, lc: dict[str, Any]) -> list[int]:
    """A pending plan task whose pending searches a newer plan already covers
    is cancelled, so a replan never runs the same research twice."""
    pending = [t for t in _plan_tasks(repo, lc)
               if t["status"] in ("planejada", "pronta") and t["pendencias"]]
    cancelled: list[int] = []
    for t in sorted(pending, key=lambda x: x["id"]):
        newer = set().union(*[set(o["pendencias"]) for o in pending
                              if o["id"] > t["id"] and o["id"] not in cancelled]) if pending else set()
        if set(t["pendencias"]) <= newer:
            repo.transicionar_tarefa(t["id"], (t["status"],), "cancelada", COORDINATOR,
                                     "As mesmas pesquisas estão numa tarefa mais nova do plano.")
            cancelled.append(t["id"])
    if cancelled:
        _decision(repo, lc["lot_id"], lc["unit_id"], "supersede_plan_tasks",
                  f"{len(cancelled)} tarefa(s) de planos anteriores repetiam pesquisas que um plano "
                  "mais novo cobre; foram canceladas.", {"cancelled": cancelled})
    return cancelled


def _close_non_queue_entries(repo: Any, lc: dict[str, Any]) -> None:
    """Issue 17: a rejected capture or a Claim without a physical page opened
    before this rule is no queue item inside a Lot."""
    repo.conn.execute(
        "UPDATE escalations SET resposta=%s,respondido_por=%s,respondido_em=now(),resolution=%s "
        "WHERE unit_id=%s AND respondido_em IS NULL AND kind='escalation' AND "
        "motivo IN ('capture','document_evidence') AND created_at >= %s",
        ("Dentro do lote não é item da fila: o motivo fica na saída da função e a afirmação segue "
         "para pesquisa nas fontes do job ou lacuna declarada.", COORDINATOR,
         json.dumps({"option": "not_a_queue_item_in_lot", "rule": RULE}),
         lc["unit_id"], lc["lot_created_at"]))


def _cancel_infeasible(repo: Any, lc: dict[str, Any]) -> list[int]:
    """Issue 17: a pending Archivist task that names no document cannot meet
    its contract; it is cancelled (with what depended on it) before it burns
    turns, and the decision says why."""
    from src.casefile.runtime import ARCHIVIST_CONTRACT, archivist_target
    uid = lc["unit_id"]
    bad = [t for t in repo.tarefas(uid) if t["role"] == "arquivista"
           and t["status"] in ("planejada", "pronta") and t["created_at"] >= lc["lot_created_at"]
           and not archivist_target(t["input_json"] or {})]
    cancelled = []
    frontier = set()
    for t in bad:
        repo.transicionar_tarefa(t["id"], (t["status"],), "cancelada", COORDINATOR,
                                 "Contrato inviável: " + ARCHIVIST_CONTRACT)
        cancelled.append(t["id"])
        frontier.add(t["id"])
    while frontier:
        nxt = set()
        for t in repo.tarefas(uid):
            if t["status"] in ("planejada", "pronta") and frontier & set(t["depends_on"] or []):
                repo.transicionar_tarefa(t["id"], (t["status"],), "cancelada", COORDINATOR,
                                         "Dependia de uma tarefa do Arquivista com contrato inviável.")
                cancelled.append(t["id"])
                nxt.add(t["id"])
        frontier = nxt
    if cancelled:
        _decision(repo, lc["lot_id"], uid, "cancel_infeasible",
                  f"{len(bad)} tarefa(s) do Arquivista sem documento a registrar foram canceladas "
                  f"(e {len(cancelled) - len(bad)} dependente(s)): {ARCHIVIST_CONTRACT}.",
                  {"cancelled": cancelled})
    return cancelled


def _infeasible_refusal(repo: Any, lc: dict[str, Any], task: dict[str, Any]) -> bool:
    """A refused Archivist task that named no document never could deliver:
    its entry closes and what depended on it is cancelled; no replan is spent."""
    from src.casefile.runtime import ARCHIVIST_CONTRACT, archivist_target
    if task["role"] != "arquivista" or archivist_target(task["input_json"] or {}):
        return False
    uid = lc["unit_id"]
    open_entries = repo.conn.execute(
        "SELECT id FROM escalations WHERE unit_id=%s AND task_id=%s AND respondido_em IS NULL",
        (uid, task["id"])).fetchall()
    dependents = [t for t in repo.tarefas(uid)
                  if t["status"] in ("planejada", "pronta") and task["id"] in (t["depends_on"] or [])]
    for t in dependents:
        repo.transicionar_tarefa(t["id"], (t["status"],), "cancelada", COORDINATOR,
                                 "Dependia de uma tarefa do Arquivista com contrato inviável.")
    if open_entries:
        repo.conn.execute(
            "UPDATE escalations SET resposta=%s,respondido_por=%s,respondido_em=now(),resolution=%s "
            "WHERE unit_id=%s AND task_id=%s AND respondido_em IS NULL",
            ("Contrato inviável: " + ARCHIVIST_CONTRACT, COORDINATOR,
             json.dumps({"option": "infeasible_contract", "rule": RULE}), uid, task["id"]))
    if open_entries or dependents:
        _decision(repo, lc["lot_id"], uid, "infeasible_refusal",
                  f"A tarefa {task['id']} do Arquivista não nomeava documento e não podia entregar; "
                  f"sua entrada fecha e {len(dependents)} dependente(s) são cancelada(s): "
                  f"{ARCHIVIST_CONTRACT}.",
                  {"task_id": task["id"], "cancelled": [t["id"] for t in dependents]})
    return True


def _revivable(repo: Any, lc: dict[str, Any]) -> bool:
    """A Lot case stopped only by entries the Coordinator now handles itself:
    refused tasks it can replan, refused Archivist tasks that named no
    document, and Lot-internal entries that are no queue items."""
    from src.casefile.runtime import archivist_target
    if lc["status"] != "stopped" or lc["stop_reason"] != "awaiting_exceptions":
        return False
    _close_non_queue_entries(repo, lc)
    blocking = [e for e in _lot_queue(repo, lc) if e.get("kind") not in LOT_QUEUE_KINDS]
    if not blocking:
        return False
    replans_left = len(_replans(repo, lc)) < MAX_REPLANS
    for entry in blocking:
        task = repo.tarefa(entry["task_id"]) if entry.get("task_id") else None
        if entry.get("kind") != "case_blocked" or not task or task["status"] != "recusada" \
                or task["role"] == "coordenador":
            return False
        infeasible = task["role"] == "arquivista" and not archivist_target(task["input_json"] or {})
        if _phase_kind(lc, task):
            if not _phase_retry_left(repo, lc, task):
                return False
        elif not (infeasible or replans_left):
            return False
    return True


ATTEMPTS = 3
RESULT_KINDS = ("divergence", "insufficient_evidence", "needs_decision", "open_item",
                "audit_suspended")


def _merge_claim_entries(repo: Any, lc: dict[str, Any]) -> None:
    """Issue 15: one queue item per Claim. An escalation the Arbiter (or the
    independent comparison) opened on a Claim joins the Coordinator's entry
    for that Claim: its question is appended to the entry, and it is closed
    as merged, with the entry it joined."""
    uid = lc["unit_id"]
    entries = repo.conn.execute(
        "SELECT * FROM escalations WHERE unit_id=%s AND respondido_em IS NULL AND kind = ANY(%s) "
        "ORDER BY id", (uid, list(RESULT_KINDS))).fetchall()
    for entry in entries:
        detail = entry["detail"] or {}
        claim_ids = [str(c["claim_id"]) for c in detail.get("claims", [])]
        if not claim_ids:
            continue
        tasks = {entry["task_id"]} | {r["id"] for r in repo.conn.execute(
            "SELECT id FROM tasks WHERE unit_id=%s AND (input_json->'claim'->>'id' = ANY(%s) "
            "OR input_json->>'claim_id' = ANY(%s))", (uid, claim_ids, claim_ids))}
        others = repo.conn.execute(
            "SELECT id, motivo, pergunta FROM escalations WHERE unit_id=%s AND respondido_em IS NULL "
            "AND kind='escalation' AND exception_key IS NULL AND task_id = ANY(%s) ORDER BY id",
            (uid, [t for t in tasks if t])).fetchall()
        if not others:
            continue
        ids = [o["id"] for o in others]
        repo.conn.execute(
            "UPDATE escalations SET resposta=%s,respondido_por=%s,respondido_em=now(),resolution=%s "
            "WHERE id = ANY(%s)",
            (f"Unido ao item {entry['id']} da fila: uma entrada por afirmação.", COORDINATOR,
             json.dumps({"option": "merged", "merged_into": entry["id"]}), ids))
        merged = detail.get("merged_escalations", []) + [
            {"id": o["id"], "motivo": o["motivo"], "pergunta": o["pergunta"]} for o in others]
        question = entry["pergunta"] + "".join(
            f"\nÁrbitro: {o['pergunta'][:600]}" for o in others)
        repo.conn.execute(
            "UPDATE escalations SET pergunta=%s,detail=%s WHERE id=%s",
            (question, json.dumps({**detail, "merged_escalations": merged},
                                  ensure_ascii=False, default=str), entry["id"]))
        _decision(repo, lc["lot_id"], uid, "merge",
                  f"As escalações {', '.join(map(str, ids))} do Árbitro sobre a(s) afirmação(ões) "
                  f"{', '.join(claim_ids)} foram unidas ao item {entry['id']} da fila.",
                  {"exception_id": entry["id"], "merged": ids})


def _call_failure(repo: Any, run: dict[str, Any]) -> dict[str, Any] | None:
    return repo.conn.execute(
        "SELECT * FROM operation_terminal_calls WHERE run_id=%s AND failure_class IS NOT NULL "
        "ORDER BY ordinal DESC, id DESC LIMIT 1", (run["id"],)).fetchone()


def _settle(repo: Any, task: dict[str, Any], since: Any, answer: str) -> None:
    """Close the worker's entry for a failure the Coordinator resolves by
    itself (a limit wait, an automatic retry), with the reason."""
    repo.conn.execute(
        "UPDATE escalations SET resposta=%s,respondido_por=%s,respondido_em=now(),resolution=%s "
        "WHERE unit_id=%s AND task_id=%s AND respondido_em IS NULL AND exception_key IS NULL "
        "AND kind='escalation' AND created_at >= %s",
        (answer, COORDINATOR, json.dumps({"option": "auto", "rule": RULE}),
         task["unit_id"], task["id"], since))


def _auto_retry(repo: Any, task: dict[str, Any], note: str) -> None:
    """The Coordinator's retry: the failed call is marked reviewed (its text
    and class are on file), and the task goes back to planned."""
    repo.conn.execute(
        "UPDATE operation_terminal_calls c SET receipt=c.receipt || %s::jsonb FROM task_runs r "
        "WHERE c.run_id=r.id AND r.task_id=%s AND r.finished_at IS NOT NULL "
        "AND c.status IN ('running','interrupted') AND NOT (c.receipt ? 'reviewed_by')",
        (json.dumps({"reviewed_by": COORDINATOR, "review_note": note}), task["id"]))
    repo.transicionar_tarefa(task["id"], ("bloqueada",), "planejada", COORDINATOR, note)
    repo.promover_prontas(task["unit_id"], COORDINATOR)


def _blocked(repo: Any, lc: dict[str, Any], task: dict[str, Any], last: dict[str, Any],
             reason: str) -> str:
    """Issue 14: a blocked task, by the class of its last failed call."""
    from src.casefile import cli_failures
    uid = task["unit_id"]
    failure = _call_failure(repo, last)
    kind = failure["failure_class"] if failure else (
        "login" if cli_failures.classify(reason) == "login" else None)
    text = (failure or {}).get("failure_text") or reason
    adopt = (task["id"], last["started_at"])
    if kind == "login":
        _stop(repo, lc, "envelope_cli", "O terminal oficial pede login (ou não está "
              f"instalado): {text[:300]}", f"envelope:cli:run{last['id']}", adopt=adopt)
        return "stopped"
    if kind == "limit":
        until = cli_failures.resume_at(text)
        _auto_retry(repo, task, "O limite da assinatura foi atingido; a tarefa volta quando ele passar.")
        _settle(repo, task, last["started_at"], "O Coordenador aguarda o limite da assinatura "
                f"e retoma sozinho em {until.isoformat()}.")
        repo.conn.execute(
            "UPDATE operation_lot_cases SET stop_reason='waiting_limit',resume_at=%s,updated_at=now() "
            "WHERE lot_id=%s AND unit_id=%s", (until, lc["lot_id"], uid))
        repo.operation_update(uid, execution_state="waiting")
        _decision(repo, lc["lot_id"], uid, "wait_limit",
                  f"Tarefa {task['id']} atingiu o limite da assinatura; o caso espera até "
                  f"{until.isoformat()} e retoma sozinho, sem contar a tentativa.",
                  {"task_id": task["id"], "run_id": last["id"], "resume_at": until.isoformat(),
                   "failure_file": (failure or {}).get("failure_relative")})
        return "waiting_limit"
    if kind == "invalid_output" and repo.task_attempts(task["id"]) < ATTEMPTS:
        _auto_retry(repo, task, "Saída fora do contrato; nova tentativa automática.")
        _settle(repo, task, last["started_at"], "O Coordenador repetiu a tarefa: a saída do "
                "terminal veio fora do contrato.")
        _decision(repo, lc["lot_id"], uid, "retry",
                  f"Tarefa {task['id']}: a saída do terminal veio fora do contrato; nova "
                  f"tentativa ({repo.task_attempts(task['id'])} de {ATTEMPTS} usadas).",
                  {"task_id": task["id"], "run_id": last["id"],
                   "failure_file": (failure or {}).get("failure_relative")})
        return "retried"
    labels = {"crash": "o terminal falhou", "invalid_output": "a saída veio fora do contrato "
              "em todas as tentativas"}
    question = (f"Tarefa {task['id']} ({task['title']}) parou: "
                f"{labels.get(kind, reason or 'sem motivo registrado')}."
                + (f" Texto do terminal: {text[:400]}" if failure else ""))
    _exception(repo, lc["lot_id"], uid, task["id"], "case_blocked",
               f"task:{task['id']}:blocked:run{last['id']}", question,
               {"reason": reason, "run_id": last["id"], "failure_class": kind,
                "failure_file": (failure or {}).get("failure_relative")}, adopt=adopt)
    if kind == "crash":
        _stop(repo, lc, "cli_crash", question, f"crash:run{last['id']}", exception=False)
        return "stopped"
    return "queued"


def coordinate(repo: Any, unit_id: int) -> str:
    """One Coordinator step for a Case in an open Lot. Returns what it did:
    idle (not in a running Lot), stopped, working (tasks to run), writer,
    qa, deliverable, or awaiting_exceptions."""
    lc = open_lot_case(repo, unit_id)
    if not lc or lc["status"] != "running":
        return "idle"
    with repo.transacao():
        repo.operation_case(unit_id, lock=True)
        stop = _envelope_stop(repo, lc)
        if stop:
            _stop(repo, lc, stop[0], stop[1], "envelope:" + stop[2])
            return "stopped"
        _cancel_infeasible(repo, lc)
        _supersede_older_plan_tasks(repo, lc)
        _close_non_queue_entries(repo, lc)
        for task in repo.tarefas(unit_id):
            runs = repo.runs_da_tarefa(task["id"])
            last = runs[-1] if runs else None
            reason = str((last or {}).get("stop_reason") or "")
            if task["status"] == "bloqueada" and last:
                acted = _blocked(repo, lc, task, last, reason)
                if acted in ("stopped", "waiting_limit"):
                    return acted
            elif task["status"] == "recusada" and last and \
                    task["created_at"] >= lc["lot_created_at"]:
                if _infeasible_refusal(repo, lc, task):
                    continue
                if _phase_kind(lc, task):
                    if _phase_retry(repo, lc, task, last, reason):
                        continue
                elif task["role"] != "coordenador" and _replan(repo, lc, task, last, _refusal_reason(task, last, reason)):
                    continue
                _exception(repo, lc["lot_id"], unit_id, task["id"], "case_blocked",
                           f"task:{task['id']}:refused:run{last['id']}",
                           f"Tarefa {task['id']} ({task['title']}) foi recusada após as "
                           f"tentativas: {reason}.", {"reason": reason, "run_id": last["id"]},
                           adopt=(task["id"], last["started_at"]))
        in_flight = _claims_in_flight(repo, unit_id)
        needing: dict[int, str] = {}
        for task in repo.tarefas(unit_id, "aguardando_operador"):
            if _outside_lot(repo, task):
                continue
            pending = repo.conn.execute(
                "SELECT id FROM escalations WHERE unit_id=%s AND respondido_em IS NULL "
                "AND exception_key LIKE %s", (unit_id, f"task:{task['id']}:decision:%")).fetchall()
            verdict = dispositions(repo, task)
            if in_flight & {c["claim_id"] for c in verdict["claims"]}:
                continue            # a review of these Claims is still running
            no_claims_left = verdict["kind"] == "needs_decision" and bool(verdict.get("output"))
            if verdict["ok"] or no_claims_left:
                # Issue 17: a result with no active Claim left to check (none, or
                # every one a declared gap or superseded) asserts nothing more.
                for row in pending:
                    repo.conn.execute(
                        "UPDATE escalations SET resposta=%s,respondido_por=%s,respondido_em=now(),"
                        "resolution=%s WHERE id=%s AND respondido_em IS NULL",
                        ("Resolvido pelo Coordenador: as quatro disposições passaram a valer."
                         if verdict["ok"] else "Resolvido pelo Coordenador: não resta afirmação "
                         "ativa a conferir (lacunas declaradas ou substituídas).",
                         COORDINATOR, json.dumps({"option": "auto", "rule": RULE}), row["id"]))
                _accept(repo, lc, task, verdict)
                continue
            if verdict["kind"] in RESEARCHABLE:
                needing.update(_failing_claims(verdict))
                continue
            if pending:
                continue
            version = max([v["id"] for c in verdict["claims"]
                           for v in repo.verificacoes_do_claim(c["claim_id"])] or [0])
            _exception(repo, lc["lot_id"], unit_id, task["id"], verdict["kind"],
                       f"task:{task['id']}:decision:v{version}:{verdict['kind']}",
                       f"Tarefa {task['id']} ({task['title']}) não reúne as quatro "
                       f"disposições para aceite automático: {_failure_text(verdict)}",
                       {"failures": verdict["failures"], "claims": verdict["claims"]})
        if needing:
            _research_or_gap(repo, lc, needing)
        _merge_claim_entries(repo, lc)
        if _runnable(repo, unit_id):
            if repo.estado_da_unit(unit_id) == "PLANEJANDO" and any(
                    t["role"] == "coordenador" and t["status"] == "aceita" and
                    t["updated_at"] >= lc["lot_created_at"] for t in repo.tarefas(unit_id)):
                advance(repo, lc["lot_id"], unit_id, "EXAMINANDO",
                        "O plano do Coordenador foi aplicado; as tarefas de pesquisa e "
                        "exame seguem.")
            return "working"
        return _next_phase(repo, lc)


def _next_phase(repo: Any, lc: dict[str, Any]) -> str:
    uid, lot_id = lc["unit_id"], lc["lot_id"]
    writer = _lot_task(repo, uid, lot_id, "redator")
    qa = _lot_task(repo, uid, lot_id, "qa")
    if writer is None:
        blocking = [e for e in _lot_queue(repo, lc) if e.get("kind") in CLAIM_BLOCKING]
        if blocking:
            return _await(repo, lc)
        if any(not _outside_lot(repo, t) for t in repo.tarefas(uid, "aguardando_operador")):
            return "working"        # a result is being researched or re-evaluated
        missing = _writer_prerequisites(repo, uid)
        if missing:
            _exception(repo, lot_id, uid, None, "deliverable_prerequisite",
                       f"prerequisite:{','.join(missing)}",
                       "O entregável não pode ser montado: " + "; ".join(missing) + ".",
                       {"missing": missing})
            return _await(repo, lc)
        accepted = repo.conn.execute(
            "SELECT count(*) AS n FROM claims WHERE unit_id=%s AND status='ativo'",
            (uid,)).fetchone()["n"]
        opened = len(_lot_queue(repo, lc))
        _create_phase_task(repo, lc, "redator")
        advance(repo, lot_id, uid, "PREENCHENDO",
                "Não resta tarefa executável de pesquisa e exame.")
        _decision(repo, lot_id, uid, "writer_ready",
                  f"Sem tarefa executável: {accepted} afirmações ativas e {opened} "
                  f"exceções abertas. O Redator monta o entregável com células citadas "
                  f"ou brancos declarados.", {"active_claims": accepted, "open_exceptions": opened})
        return "writer"
    if writer["status"] == "aceita" and qa is None:
        _create_phase_task(repo, lc, "qa")
        advance(repo, lot_id, uid, "AUDITANDO", "O entregável foi aceito pelas disposições.")
        _decision(repo, lot_id, uid, "qa_ready",
                  "O Redator entregou e o resultado foi aceito; a Qualidade confere a versão.")
        return "qa"
    if qa is not None and qa["status"] == "aceita" and not lc["deliverable_artifact_id"]:
        _deliver(repo, lc)
        return "deliverable"
    return _await(repo, lc)


def _await(repo: Any, lc: dict[str, Any]) -> str:
    """Nothing runnable and the next phase waits on the exceptions queue."""
    if [e for e in _lot_queue(repo, lc) if e.get("kind") not in LOT_QUEUE_KINDS]:
        repo.conn.execute(
            "UPDATE operation_lot_cases SET status='stopped',stop_reason='awaiting_exceptions',"
            "updated_at=now() WHERE lot_id=%s AND unit_id=%s", (lc["lot_id"], lc["unit_id"]))
        repo.operation_update(lc["unit_id"], execution_state="waiting")
        _decision(repo, lc["lot_id"], lc["unit_id"], "stop",
                  "Nada mais é executável até as exceções abertas serem tratadas.",
                  {"reason": "awaiting_exceptions",
                   "open_exceptions": len(_lot_queue(repo, lc))})
        return "awaiting_exceptions"
    return "working"


# --- deliverable, package and release ----------------------------------------------------

def _deliver(repo: Any, lc: dict[str, Any]) -> dict[str, Any]:
    from src.casefile import operation_packet
    from src.casefile.storage import checked_artifact, write_bytes
    uid, lot_id = lc["unit_id"], lc["lot_id"]
    repo.operation_update(uid, execution_state="paused")
    packet = operation_packet.build(repo, uid)
    unit = next(u for u in repo.listar_units() if u["id"] == uid)
    report = repo.operation_artifacts(uid, "working_report")[-1]
    deliverable = repo.deliverables(uid, "surface_runsheet")[-1]
    cited = repo.conn.execute(
        "SELECT DISTINCT unnest(claim_ids) AS claim_id FROM derived_cells "
        "WHERE deliverable_version_id=%s", (deliverable["id"],)).fetchall()
    documents = {}
    for row in cited:
        claim = repo.claim(row["claim_id"])
        for artifact in repo.operation_artifacts(uid, "source"):
            if artifact["sha256"] == claim["source_sha256"]:
                documents[artifact["sha256"]] = {
                    "name": (artifact["metadata"] or {}).get("display_name") or Path(artifact["path"]).name,
                    "sha256": artifact["sha256"], "path": artifact["path"]}
    base = f"entregas/lote-{lot_id}/v{deliverable['version']}"
    name = unit["canonical_name"].replace("/", "-")
    data = checked_artifact(report).read_bytes()
    runsheet, sha = write_bytes(
        uid, f"{base}/{name}/1. Landman Submitted/{name} - WORKING DRAFT v{deliverable['version']}.xlsx", data)
    for folder in LAYOUT:
        (runsheet.parents[1] / folder).mkdir(parents=True, exist_ok=True)
    manifest = {"schema": 1, "status": "WORKING DRAFT", "lot_id": lot_id, "job": lc["job"],
                "envelope": lc["envelope"], "case": unit["canonical_name"],
                "runsheet": {"path": str(runsheet), "sha256": sha,
                             "working_report_artifact_id": report["id"]},
                "decision_packet": {"artifact_id": packet["id"], "sha256": packet["sha256"]},
                "cited_documents": sorted(documents.values(), key=lambda d: d["name"]),
                "documents_copied": False,
                "pending": ["Q3 PREP Gem sobre esta versão (exige autorização e execução)",
                            "Q4 Spell Check final", "Q5 consulta a SME quando houver questão técnica",
                            "Cópia e classificação dos documentos citados nas pastas do pacote"],
                "title_approval": False, "release": "pending Renato"}
    raw = json.dumps(manifest, ensure_ascii=False, indent=2, default=str).encode()
    manifest_path, manifest_sha = write_bytes(uid, f"{base}/MANIFESTO_WORKING_DRAFT.json", raw)
    artifact = repo.operation_add_artifact(
        uid, "deliverable_package", runsheet, sha, len(data),
        {"display_name": f"{name} · entregável WORKING DRAFT v{deliverable['version']}",
         "package_root": str(runsheet.parents[1]), "manifest": str(manifest_path),
         "manifest_sha256": manifest_sha, "lot_id": lot_id, "status": "Pronto para você ver e liberar"},
        None)
    repo.conn.execute(
        "UPDATE operation_lot_cases SET status='deliverable_ready',deliverable_artifact_id=%s,"
        "stop_reason='',updated_at=now() WHERE lot_id=%s AND unit_id=%s",
        (artifact["id"], lot_id, uid))
    current = rounds.current(repo, uid)
    if current and current["closed_at"] is None:
        rounds._close(repo, uid, current, "deliverable_ready", COORDINATOR)
    advance(repo, lot_id, uid, "AGUARDANDO_RENATO",
            "Entregável montado e conferido; aguarda a sua liberação.")
    _decision(repo, lot_id, uid, "deliverable_ready",
              f"Pacote no layout PLM em {runsheet.parents[1]}; runsheet {sha[:12]}.",
              {"artifact_id": artifact["id"], "manifest": str(manifest_path)})
    _exception(repo, lot_id, uid, None, "protocol_pending", f"protocol:v{deliverable['version']}",
               "Antes de qualquer envio: PREP Gem real sobre esta versão (Q3), Spell Check "
               "final (Q4) e SME se houver questão técnica (Q5) dependem de você. A "
               "liberação não envia nem certifica nada.",
               {"version": deliverable["version"], "runsheet_sha256": sha})
    return artifact


def release_case(repo: Any, unit_id: int, actor: str, note: str) -> None:
    """Renato's one click after viewing the deliverable: stage LIBERADA.
    Releasing uploads nothing and submits nothing."""
    from src.casefile import estados
    lc = open_lot_case(repo, unit_id)
    if not lc or lc["status"] != "deliverable_ready":
        raise ValueError("deliverable_not_ready_for_release")
    unit = next(u for u in repo.listar_units() if u["id"] == unit_id)
    estados.transicionar(repo, unit, "liberar", actor, note)
    repo.conn.execute(
        "UPDATE operation_lot_cases SET status='released',updated_at=now() "
        "WHERE lot_id=%s AND unit_id=%s", (lc["lot_id"], unit_id))
    if not repo.conn.execute(
            "SELECT 1 FROM operation_lot_cases WHERE lot_id=%s AND status NOT IN ('released','superseded')",
            (lc["lot_id"],)).fetchone():
        repo.conn.execute("UPDATE operation_lots SET closed_at=now() WHERE id=%s",
                          (lc["lot_id"],))
    repo.operation_event("lot.case_released", actor,
                         {"lot_id": lc["lot_id"], "note": note}, unit_id=unit_id)


# --- the exceptions queue: one-click options ----------------------------------------------

def _resume(repo: Any, unit_id: int) -> None:
    lc = open_lot_case(repo, unit_id)
    if lc and lc["status"] == "stopped":
        repo.conn.execute(
            "UPDATE operation_lot_cases SET status='running',stop_reason='',updated_at=now() "
            "WHERE lot_id=%s AND unit_id=%s", (lc["lot_id"], unit_id))
        repo.operation_update(unit_id, execution_state="running")


def _page_count(repo: Any, unit_id: int, sha: str) -> int | None:
    from src.casefile.storage import checked_artifact
    for artifact in repo.operation_artifacts(unit_id, "source"):
        if artifact["sha256"] == sha:
            path = checked_artifact(artifact)
            if path.suffix.lower() == ".pdf":
                import fitz
                with fitz.open(path) as document:
                    return len(document)
    return None


def _next_pages(repo: Any, claim: dict[str, Any]) -> str:
    """The cited pages plus the next one, when the document has it;
    otherwise the same pages, read again."""
    from src.casefile.runtime import cited_pages
    pages = [int(p) for p in cited_pages(claim["page"]) if str(p).isdigit()]
    if not pages:
        return str(claim["page"])
    count = _page_count(repo, claim["unit_id"], claim["source_sha256"])
    last = max(pages) + 1 if count is None or max(pages) + 1 <= count else max(pages)
    return str(min(pages)) if last == min(pages) else f"{min(pages)}-{last}"


def resolve_exception(repo: Any, unit_id: int, actor: str, exception_id: int,
                      option: str, params: dict[str, Any] | None, note: str) -> dict[str, Any]:
    """One click on an exception. Free text is optional; every refusal names
    its reason."""
    from src.casefile import orquestracao
    from src.casefile.runtime import add_followup
    params = params or {}
    entry = next((e for e in open_exceptions(repo, unit_id) if e["id"] == int(exception_id)), None)
    if entry is None:
        raise ValueError("open_exception_required")
    if option not in entry["options"]:
        raise ValueError(f"option_not_available_for_this_exception: {option}")
    task = repo.tarefa(entry["task_id"]) if entry["task_id"] else None
    detail = entry.get("detail") or {}
    failing = [f[1] for f in detail.get("failures", []) if isinstance(f[1], int)]
    text = str(note or "").strip()
    outcome: dict[str, Any] = {"option": option}
    if option in ("accept", "reject"):
        if not task or task["status"] != "aguardando_operador":
            raise ValueError("task_not_waiting_for_decision")
        if task["output_schema"] == "fichas_candidatas":
            raise ValueError("knowledge_requires_independent_review_and_human_batch")
        card = decision_card.card(repo, task["id"])
        if option == "accept":
            reason = ("Aceito por Renato com um clique; motivo gerado a partir do cartão: "
                      + card_summary(card)
                      + f" Fonte: {(card or {}).get('fonte', {}).get('saida', 'sem arquivo')}.")
        else:
            preset = REJECT_PRESETS[int(params.get("preset", 0))]
            reason = "Recusado por Renato: " + preset + (". " + text if text else "")
        orquestracao.decidir(repo, task["id"], aceitar=option == "accept",
                             ator=actor, nota=reason)
        outcome["reason"] = reason
    elif option == "re_read":
        claim = repo.claim(failing[0]) if failing else None
        if not claim:
            raise ValueError("re_read_needs_a_claim_under_decision")
        n = 1 + sum(t["ref"].startswith(f"review-claim-{claim['id']}-r") for t in repo.tarefas(unit_id))
        pages = _next_pages(repo, claim)
        add_followup(repo, unit_id, "verificador",
                     f"Releitura independente da afirmação {claim['id']} "
                     f"({'páginas' if '-' in pages else 'página'} {pages})",
                     {"claim_id": claim["id"], "claim_type": claim["claim_type"],
                      "source_sha256": claim["source_sha256"], "pagina": pages,
                      "pergunta": "Transcreva os fatos e cláusulas legíveis destas páginas em "
                                  "um objeto valor, com trecho literal. Inclua partes, datas, "
                                  "identificação de registro, descrição territorial e "
                                  "restrições quando presentes. Não complete campos por "
                                  "suposição; declare se a evidência é insuficiente."},
                     "extracao_cega", .6, ref=f"review-claim-{claim['id']}-r{n}",
                     parent=task["id"] if task else None)
        outcome["pages"] = pages
    elif option == "allow_source":
        from src.casefile import routines
        source = str(params.get("source") or "")
        if source not in routines.SOURCE_KEYS or source in routines.FORBIDDEN_SOURCES:
            raise ValueError("source_unknown")
        case = repo.operation_case(unit_id)
        scope = {**case["scope"], "sources": list(dict.fromkeys([*case["scope"].get("sources", []), source]))}
        repo.operation_update(unit_id, scope=scope)
        outcome["source"] = source
    elif option == "raise_cap":
        turns = rounds.validate_cap(params.get("turns", 20))
        lc = open_lot_case(repo, unit_id)
        opened = rounds.approve(repo, unit_id, turns, COORDINATOR,
                                f"Teto ampliado por Renato em {turns} turnos", "exception-" + str(entry["id"]))
        if lc:
            repo.conn.execute("UPDATE operation_lot_cases SET turn_cap=turn_cap+%s "
                              "WHERE lot_id=%s AND unit_id=%s", (turns, lc["lot_id"], unit_id))
            _decision(repo, lc["lot_id"], unit_id, "open_round",
                      f"Renato ampliou o envelope em {turns} turnos; rodada {opened['number']} aberta.",
                      {"round_id": opened["id"], "turns": turns})
        outcome["turns"] = turns
    elif option == "retry":
        if not task:
            raise ValueError("retry_needs_a_task")
        from src.casefile.operator_actions import apply
        apply(repo, repo.operation_case(unit_id),
              {"action": "retry_task", "task_id": task["id"],
               "note": text or "Nova tentativa pedida por Renato na fila de exceções."}, actor)
    elif option == "release_blank":
        preset = BLANK_PRESETS[int(params.get("preset", 0))]
        targets = failing or [c for c in (detail.get("failures") or [[None, []]])[-1][1]
                              if isinstance(c, int)]
        if not targets:
            raise ValueError("release_blank_needs_a_claim")
        for cid in targets:
            repo.atualizar_claim_status(unit_id, cid, "retirado", None,
                                        nota=f"Liberado em branco por Renato: {preset}")
        if task and task["status"] == "aguardando_operador" and not any(
                repo.claim(c)["status"] == "ativo" for c in repo.claims_da_tarefa(task["id"])):
            orquestracao.decidir(repo, task["id"], aceitar=False, ator=actor,
                                 nota=f"Afirmações liberadas em branco: {preset}")
        outcome["preset"] = preset
        outcome["claims"] = targets
    elif option in ("retry_source", "acknowledge"):
        outcome["note"] = ("A fonte será tentada de novo na próxima passada do Coordenador."
                           if option == "retry_source" else "Registrado como feito por Renato.")
    elif option == "dismiss":
        if entry.get("kind") == "open_item":
            for cid in (detail.get("failures") or [[None, []]])[-1][1]:
                if isinstance(cid, int) and repo.claim(cid)["status"] == "ativo":
                    repo.atualizar_claim_status(unit_id, cid, "retirado", None,
                                                nota="Dispensado por Renato: não trata do caso")
    answer = f"{option}: " + json.dumps(outcome, ensure_ascii=False, default=str)
    repo.conn.execute(
        "UPDATE escalations SET resposta=%s,respondido_por=%s,respondido_em=now(),resolution=%s "
        "WHERE id=%s AND respondido_em IS NULL",
        (answer[:4000], actor, json.dumps({**outcome, "note": text}, ensure_ascii=False, default=str),
         entry["id"]))
    if not (entry.get("kind") == "envelope_exhausted" and option == "dismiss"):
        _resume(repo, unit_id)
    repo.operation_event("exception.resolved", actor,
                         {"exception_id": entry["id"], "option": option}, unit_id=unit_id,
                         task_id=entry["task_id"])
    return outcome


# --- sample audit ------------------------------------------------------------------

def audit_acceptance(repo: Any, unit_id: int, actor: str, acceptance_id: int,
                     mark: str, note: str) -> list[str]:
    """Renato marks a sampled auto-acceptance right or wrong. A Claim type
    with more than N wrong in its last 20 marks goes back to the exceptions
    queue until he turns auto-accept on again. Marks never change prompts."""
    if mark not in ("right", "wrong"):
        raise ValueError("audit_mark_unknown")
    row = repo.conn.execute(
        "UPDATE operation_acceptances SET audit_mark=%s,audit_note=%s,marked_by=%s,"
        "marked_at=now() WHERE id=%s AND unit_id=%s RETURNING *",
        (mark, str(note or ""), actor, acceptance_id, unit_id)).fetchone()
    if not row:
        raise ValueError("acceptance_outside_case")
    lot = repo.conn.execute("SELECT envelope FROM operation_lots WHERE id=%s",
                            (row["lot_id"],)).fetchone() if row["lot_id"] else None
    limit = int(((lot or {}).get("envelope") or {}).get("audit_wrong_limit", 2))
    suspended = []
    for claim_type in row["claim_types"]:
        marks = repo.conn.execute(
            "SELECT audit_mark FROM operation_acceptances WHERE audit_mark IS NOT NULL "
            "AND %s = ANY(claim_types) ORDER BY marked_at DESC LIMIT 20", (claim_type,)).fetchall()
        wrong = sum(m["audit_mark"] == "wrong" for m in marks)
        if wrong > limit:
            inserted = repo.conn.execute(
                "INSERT INTO operation_autoaccept_suspensions(claim_type,reason) VALUES (%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING claim_type",
                (claim_type, f"{wrong} de {len(marks)} marcadas erradas (limite {limit})")).fetchone()
            if inserted:
                suspended.append(claim_type)
                repo.operation_event("autoaccept.suspended", actor,
                                     {"claim_type": claim_type, "wrong": wrong,
                                      "last": len(marks), "limit": limit}, unit_id=unit_id)
    return suspended


def resume_autoaccept(repo: Any, unit_id: int, actor: str, claim_type: str) -> None:
    gone = repo.conn.execute("DELETE FROM operation_autoaccept_suspensions WHERE claim_type=%s "
                             "RETURNING claim_type", (claim_type,)).fetchone()
    if not gone:
        raise ValueError("claim_type_not_suspended")
    repo.operation_event("autoaccept.resumed", actor, {"claim_type": claim_type}, unit_id=unit_id)


# --- dashboard ----------------------------------------------------------------------

def overview(repo: Any, unit_id: int) -> dict[str, Any] | None:
    lc = open_lot_case(repo, unit_id) or repo.conn.execute(
        "SELECT c.*, l.job, l.envelope, l.created_at AS lot_created_at FROM operation_lot_cases c "
        "JOIN operation_lots l ON l.id=c.lot_id WHERE c.unit_id=%s ORDER BY c.lot_id DESC LIMIT 1",
        (unit_id,)).fetchone()
    if not lc:
        return None
    acceptances = repo.conn.execute(
        "SELECT * FROM operation_acceptances WHERE unit_id=%s ORDER BY id", (unit_id,)).fetchall()
    turns = turns_by_function(repo, unit_id, lc["lot_id"])
    return {"lot_id": lc["lot_id"], "status": lc["status"], "stop_reason": lc["stop_reason"],
            "resume_at": lc.get("resume_at"), "turns_by_function": turns,
            "turns_used": sum(turns.values()),
            "turn_cap": lc["turn_cap"], "job": lc["job"], "envelope": lc["envelope"],
            "deliverable_artifact_id": lc["deliverable_artifact_id"],
            "exceptions_open": len(_lot_queue(repo, lc) if lc["status"] not in
                                   ("released", "superseded") else open_exceptions(repo, unit_id)),
            "lot_queue_ids": [e["id"] for e in _lot_queue(repo, lc)],
            "acceptances": {"total": len(acceptances),
                            "sampled": [a for a in acceptances if a["sampled"]]},
            "suspended_claim_types": [r["claim_type"] for r in repo.conn.execute(
                "SELECT claim_type FROM operation_autoaccept_suspensions ORDER BY 1")],
            "decisions": repo.conn.execute(
                "SELECT * FROM operation_coordinator_decisions WHERE unit_id=%s ORDER BY id",
                (unit_id,)).fetchall()}


def parked_lot_cases(repo: Any) -> list[int]:
    return [r["unit_id"] for r in repo.conn.execute(
        "SELECT lc.unit_id FROM operation_lot_cases lc JOIN operation_cases o "
        "ON o.unit_id=lc.unit_id WHERE o.execution_state='waiting' AND (lc.status='running' "
        "OR (lc.status='stopped' AND lc.stop_reason='awaiting_exceptions')) "
        "ORDER BY lc.unit_id").fetchall()]


def wake(repo: Any, unit_id: int) -> str:
    """The worker parks a Case in 'waiting' when a task stops with no
    automatic retry (a terminal call failed, the Round cap was reached
    mid-run). In a Lot the Coordinator owns the Case: it puts the block in
    the exceptions queue and keeps the rest moving within the envelope, or
    stops the Case with a reason. A Case Renato paused stays paused."""
    from src.casefile.operations import has_unbounded_usage
    lc = open_lot_case(repo, unit_id)
    if lc and repo.operation_case(unit_id)["execution_state"] == "waiting" and _revivable(repo, lc):
        # Issue 17: stopped only by refused tasks; the Coordinator replans.
        repo.conn.execute(
            "UPDATE operation_lot_cases SET status='running',stop_reason='',updated_at=now() "
            "WHERE lot_id=%s AND unit_id=%s", (lc["lot_id"], unit_id))
        lc = open_lot_case(repo, unit_id)
    if not lc or lc["status"] != "running" or \
            repo.operation_case(unit_id)["execution_state"] != "waiting":
        return "idle"
    after_limit = bool(lc.get("resume_at"))
    if after_limit:
        if lc["resume_at"] > datetime.now(timezone.utc):
            return "waiting_limit"
        repo.conn.execute(
            "UPDATE operation_lot_cases SET stop_reason='',resume_at=NULL,updated_at=now() "
            "WHERE lot_id=%s AND unit_id=%s", (lc["lot_id"], unit_id))
    action = coordinate(repo, unit_id)
    if action not in ("working", "writer", "qa"):
        return action
    with repo.transacao():
        if repo.operation_case(unit_id, lock=True)["execution_state"] != "waiting":
            return action
        lc = open_lot_case(repo, unit_id)
        if has_unbounded_usage(repo, unit_id):
            _stop(repo, lc, "awaiting_exceptions", "Um run terminou sem recibo de uso "
                  "conferido; o caso espera a conferência na fila.", "usage:unbounded",
                  exception=False)
            return "stopped"
        repo.operation_update(unit_id, execution_state="running")
        blocked = sorted(e["task_id"] for e in open_exceptions(repo, unit_id)
                         if e.get("kind") == "case_blocked" and e.get("task_id"))
        _decision(repo, lc["lot_id"], unit_id, "resume",
                  "O limite da assinatura passou; o caso retoma dentro do envelope."
                  if after_limit else
                  "Uma tarefa parou sem nova tentativa automática e está na fila de "
                  "exceções; o restante do caso segue dentro do envelope.",
                  {"blocked_tasks": blocked})
    return action


def step(repo: Any, unit_id: int, client: Any = None,
         worker_name: str = "process:worker-lot") -> str:
    """The supervisor's unit of work for a Case in a Lot, also used by tests:
    a Coordinator step, then at most one task run when work is runnable."""
    from src.casefile import worker
    if repo.operation_case(unit_id)["execution_state"] == "waiting":
        action = wake(repo, unit_id)
    else:
        action = coordinate(repo, unit_id)
    if action not in ("working", "writer", "qa"):
        return action
    case = repo.operation_case(unit_id)
    if case["execution_state"] != "running":
        return "not_running"
    result = worker.executar_uma(repo, unit_id, worker_name,
                                 teto=float(case["approved_budget_usd"]),
                                 operation=True, client=client)
    return "ran" if result is not None else "nothing"
