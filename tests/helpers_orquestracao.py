"""A interface de `src/casefile/orquestracao_repo.py::OrquestracaoRepo` em
memória. `RepoFake` herda daqui; os testes rodam a mesma bateria contra
este fake e contra o Postgres real (schema temporário)."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from src.casefile.orquestracao_repo import PENDENTES, TransicaoInvalida


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class OrquestracaoFake:
    def _orq(self) -> dict[str, Any]:
        if not hasattr(self, "_orq_estado"):
            self._orq_estado = {"versoes": {}, "tasks": [], "trans": [],
                                "runs": [], "task_claims": set(),
                                "escal": []}
        return self._orq_estado

    # --- versões ------------------------------------------------------------
    def registrar_versao_ficha(self, sha256, path, kind, name, content):
        self._orq()["versoes"].setdefault(sha256, {
            "sha256": sha256, "path": path, "kind": kind, "name": name,
            "content": content, "first_seen": _agora()})

    def versao_ficha(self, sha256):
        return self._orq()["versoes"].get(sha256)

    # --- tarefas ------------------------------------------------------------
    def criar_tarefas(self, unit_id, tarefas, created_by):
        estado = self._orq()
        backup = copy.deepcopy((estado["tasks"], estado["trans"]))
        criadas = []
        try:
            for t in tarefas:
                if self.tarefa_por_ref(unit_id, t["ref"]):
                    raise ValueError(f"ref_duplicada: {t['ref']!r} já existe "
                                     f"na unit {unit_id}")
                deps = []
                for r in t.get("depends_on_refs", []):
                    dep = self.tarefa_por_ref(unit_id, r)
                    if dep is None:
                        raise ValueError(f"dependencia_inexistente: {r!r}")
                    deps.append(dep["id"])
                row = {"id": len(estado["tasks"]) + 1, "unit_id": unit_id,
                       "parent_id": t.get("parent_id"), "ref": t["ref"],
                       "role": t["role"], "pack": t.get("pack", ""),
                       "title": t["title"],
                       "input_json": copy.deepcopy(t.get("input_json", {})),
                       "output_schema": t["output_schema"],
                       "acceptance": t["acceptance"], "depends_on": deps,
                       "budget_usd": float(t.get("budget_usd", 0)),
                       "priority": t.get("priority", 0),
                       "verificacao": t["verificacao"],
                       "justificativa": t.get("justificativa", ""),
                       "status": "planejada", "created_by": created_by,
                       "created_at": _agora(), "updated_at": _agora()}
                estado["tasks"].append(row)
                self._log_tarefa(row["id"], "", "planejada", created_by, "")
                criadas.append(copy.deepcopy(row))
        except Exception:
            estado["tasks"], estado["trans"] = backup
            raise
        return criadas

    def _t(self, task_id):
        tasks = self._orq()["tasks"]
        return tasks[task_id - 1] if 0 < task_id <= len(tasks) else None

    def tarefa(self, task_id):
        return copy.deepcopy(self._t(task_id))

    def tarefa_por_ref(self, unit_id, ref):
        return copy.deepcopy(next(
            (t for t in self._orq()["tasks"]
             if t["unit_id"] == unit_id and t["ref"] == ref), None))

    def tarefas(self, unit_id, status=None):
        return [copy.deepcopy(t) for t in self._orq()["tasks"]
                if t["unit_id"] == unit_id
                and (status is None or t["status"] == status)]

    def _log_tarefa(self, task_id, de, para, actor, note):
        trans = self._orq()["trans"]
        trans.append({"id": len(trans) + 1, "task_id": task_id,
                      "from_status": de, "to_status": para, "actor": actor,
                      "note": note, "at": _agora()})

    def transicionar_tarefa(self, task_id, de, para, actor, note=""):
        t = self._t(task_id)
        if t is None:
            raise TransicaoInvalida(f"tarefa {task_id} inexistente")
        if t["status"] not in de:
            raise TransicaoInvalida(
                f"tarefa {task_id} está em {t['status']!r}; "
                f"{para!r} exige {list(de)}")
        antes = t["status"]
        t.update(status=para, updated_at=_agora())
        self._log_tarefa(task_id, antes, para, actor, note)
        return copy.deepcopy(t)

    def transicoes_da_tarefa(self, task_id):
        return [copy.deepcopy(x) for x in self._orq()["trans"]
                if x["task_id"] == task_id]

    def promover_prontas(self, unit_id, actor):
        ids = []
        for t in self._orq()["tasks"]:
            if t["unit_id"] == unit_id and t["status"] == "planejada" and \
                    all(self._t(d)["status"] == "aceita"
                        for d in t["depends_on"]):
                t.update(status="pronta", updated_at=_agora())
                self._log_tarefa(t["id"], "planejada", "pronta", actor,
                                 "dependências aceitas")
                ids.append(t["id"])
        return ids

    def bloquear_pendentes(self, unit_id, actor, note):
        ids = []
        for t in self._orq()["tasks"]:
            if t["unit_id"] == unit_id and t["status"] in PENDENTES:
                self._log_tarefa(t["id"], t["status"], "bloqueada", actor,
                                 note)
                t.update(status="bloqueada", updated_at=_agora())
                ids.append(t["id"])
        return ids

    # --- runs ---------------------------------------------------------------
    def liberar_leases_vencidos(self, unit_id, actor):
        ids = []
        for r in self._orq()["runs"]:
            t = self._t(r["task_id"])
            if t["unit_id"] == unit_id and r["finished_at"] is None and \
                    r["lease_until"] < _agora():
                r.update(finished_at=_agora(), stop_reason="lease_expirado")
                self.transicionar_tarefa(t["id"], ("em_execucao",), "pronta",
                                         actor, "lease expirado")
                ids.append(t["id"])
        return sorted(ids)

    def pegar_tarefa(self, unit_id, worker, versoes_funcao, versoes_pacote,
                     lease_segundos):
        prontas = sorted((t for t in self._orq()["tasks"]
                          if t["unit_id"] == unit_id
                          and t["status"] == "pronta"),
                         key=lambda t: (t["priority"], t["id"]))
        if not prontas:
            return None
        t = prontas[0]
        role_v = versoes_funcao.get(t["role"])
        if not role_v:
            raise ValueError(f"versao_da_funcao_ausente: {t['role']!r}")
        pack_v = None
        if t["pack"]:
            pack_v = versoes_pacote.get(t["pack"])
            if not pack_v:
                raise ValueError(f"versao_do_pacote_ausente: {t['pack']!r}")
        for v in (role_v, pack_v):
            if v is not None and v not in self._orq()["versoes"]:
                raise AssertionError(f"FK: role_version {v[:12]} ausente")
        task = self.transicionar_tarefa(t["id"], ("pronta",), "em_execucao",
                                        worker)
        runs = self._orq()["runs"]
        run = {"id": len(runs) + 1, "task_id": t["id"], "worker": worker,
               "role_version": role_v, "pack_version": pack_v, "model": "",
               "model_family": "", "prompt_sha256": None,
               "output_json": None, "output_valid": None,
               "validation_errors": [], "cost_usd": 0.0, "tokens_in": 0,
               "tokens_out": 0, "started_at": _agora(), "finished_at": None,
               "stop_reason": "",
               "lease_until": _agora() + timedelta(seconds=lease_segundos)}
        runs.append(run)
        return task, copy.deepcopy(run)

    def _run(self, run_id):
        runs = self._orq()["runs"]
        return runs[run_id - 1] if 0 < run_id <= len(runs) else None

    def renovar_lease(self, run_id, worker, lease_segundos):
        r = self._run(run_id)
        if r is None or r["worker"] != worker or r["finished_at"] is not None:
            raise TransicaoInvalida(f"run {run_id} fechado ou de outro worker")
        r["lease_until"] = _agora() + timedelta(seconds=lease_segundos)

    def fechar_run(self, run_id, worker, *, output_json, output_valid,
                   validation_errors, stop_reason, para, nota="", model="",
                   model_family="", prompt_sha256=None, tokens_in=0,
                   tokens_out=0, cost_usd=0.0):
        r = self._run(run_id)
        if r is None or r["worker"] != worker or r["finished_at"] is not None:
            raise TransicaoInvalida(
                f"run {run_id} já fechado (lease vencido?) ou de outro "
                f"worker")
        t = self.transicionar_tarefa(r["task_id"], ("em_execucao",), para,
                                     worker, nota)
        r.update(output_json=copy.deepcopy(output_json),
                 output_valid=output_valid,
                 validation_errors=list(validation_errors),
                 stop_reason=stop_reason, model=model,
                 model_family=model_family, prompt_sha256=prompt_sha256,
                 tokens_in=tokens_in, tokens_out=tokens_out,
                 cost_usd=float(cost_usd), finished_at=_agora())
        if cost_usd:
            self.registrar_custo(t["unit_id"], "tarefa", cost_usd,
                                 {"task_id": t["id"], "run_id": run_id,
                                  "role": t["role"]})
        return t

    def run(self, run_id):
        return copy.deepcopy(self._run(run_id))

    def runs_da_tarefa(self, task_id):
        return [copy.deepcopy(r) for r in self._orq()["runs"]
                if r["task_id"] == task_id]

    # --- claims da tarefa ---------------------------------------------------
    def vincular_claims(self, task_id, claim_ids):
        t = self._t(task_id)
        for cid in claim_ids:
            if not self.claim_existe(t["unit_id"], cid):
                raise ValueError(f"claim_fora_da_unit: {cid}")
        self._orq()["task_claims"].update((task_id, c) for c in claim_ids)

    def claims_da_tarefa(self, task_id):
        return sorted(c for t, c in self._orq()["task_claims"]
                      if t == task_id)

    # --- escalonamentos -----------------------------------------------------
    def abrir_escalonamento(self, unit_id, task_id, motivo, pergunta, opcoes):
        esc = self._orq()["escal"]
        esc.append({"id": len(esc) + 1, "unit_id": unit_id,
                    "task_id": task_id, "motivo": motivo,
                    "pergunta": pergunta, "opcoes": list(opcoes),
                    "resposta": "", "respondido_por": "",
                    "respondido_em": None, "created_at": _agora()})
        return esc[-1]["id"]

    def responder_escalonamento(self, escalation_id, resposta, por):
        esc = self._orq()["escal"]
        e = esc[escalation_id - 1] if 0 < escalation_id <= len(esc) else None
        if e is None or e["respondido_em"] is not None:
            raise TransicaoInvalida(
                f"escalonamento {escalation_id} inexistente ou já respondido")
        e.update(resposta=resposta, respondido_por=por,
                 respondido_em=_agora())

    def escalonamentos(self, unit_id, abertos=False):
        return [copy.deepcopy(e) for e in self._orq()["escal"]
                if e["unit_id"] == unit_id
                and (not abertos or e["respondido_em"] is None)]
