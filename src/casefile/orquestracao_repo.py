"""DAO mixin da orquestração (migração 0009): tarefas, runs, versões de
fichas, escalonamentos. SQL à vista; `tests/helpers_orquestracao.py`
implementa a mesma interface em memória.

Só primitivas atômicas: inserir, transicionar com compare-and-set, pegar
com trava. As regras (quando uma tarefa fica pronta, o que acontece com uma
saída inválida, o teto) vivem em `orquestracao.py` e valem igual para o
banco e para o fake.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

PENDENTES = ("planejada", "pronta")
VERIFICADOR = "verificador"


class TransicaoInvalida(AssertionError):
    """A tarefa (ou o run) não está no estado que a operação exige."""


def _num(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: float(v) if isinstance(v, Decimal) else v
            for k, v in row.items()}


class OrquestracaoRepo:
    # --- versões das fichas ------------------------------------------------
    def registrar_versao_ficha(self, sha256: str, path: str, kind: str,
                               name: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO role_versions (sha256, path, kind, name, content) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (sha256) DO NOTHING",
            (sha256, path, kind, name, content))

    def versao_ficha(self, sha256: str) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM role_versions WHERE sha256 = %s",
            (sha256,)).fetchone()

    # --- tarefas -----------------------------------------------------------
    def criar_tarefas(self, unit_id: int, tarefas: list[dict[str, Any]],
                      created_by: str) -> list[dict[str, Any]]:
        """Insere em ordem; `depends_on_refs` resolve contra as tarefas do
        próprio lote ou já existentes na unit. Tudo ou nada."""
        from src.casefile.repo import _json
        criadas: list[dict[str, Any]] = []
        with self.conn.transaction():
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
                row = self.conn.execute(
                    "INSERT INTO tasks (unit_id, parent_id, ref, role, pack, "
                    "title, input_json, output_schema, acceptance, "
                    "depends_on, budget_usd, priority, verificacao, "
                    "justificativa, pendencias, created_by) VALUES (%s, %s, "
                    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "RETURNING *",
                    (unit_id, t.get("parent_id"), t["ref"], t["role"],
                     t.get("pack", ""), t["title"],
                     _json(t.get("input_json", {})), t["output_schema"],
                     t["acceptance"], deps, t.get("budget_usd", 0),
                     t.get("priority", 0), t["verificacao"],
                     t.get("justificativa", ""),
                     list(t.get("pendencias", [])), created_by)).fetchone()
                self._log_tarefa(row["id"], "", "planejada", created_by, "")
                criadas.append(_num(row))
        return criadas

    def tarefa(self, task_id: int) -> dict[str, Any] | None:
        return _num(self.conn.execute(
            "SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone())

    def tarefa_por_ref(self, unit_id: int, ref: str) -> dict[str, Any] | None:
        return _num(self.conn.execute(
            "SELECT * FROM tasks WHERE unit_id = %s AND ref = %s",
            (unit_id, ref)).fetchone())

    def tarefas(self, unit_id: int, status: str | None = None
                ) -> list[dict[str, Any]]:
        if status is None:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE unit_id = %s ORDER BY id",
                (unit_id,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE unit_id = %s AND status = %s "
                "ORDER BY id", (unit_id, status)).fetchall()
        return [_num(r) for r in rows]

    def _log_tarefa(self, task_id: int, de: str, para: str, actor: str,
                    note: str) -> None:
        self.conn.execute(
            "INSERT INTO task_transitions (task_id, from_status, to_status, "
            "actor, note) VALUES (%s, %s, %s, %s, %s)",
            (task_id, de, para, actor, note))

    def transicionar_tarefa(self, task_id: int, de: tuple[str, ...],
                            para: str, actor: str, note: str = ""
                            ) -> dict[str, Any]:
        with self.conn.transaction():
            atual = self.conn.execute(
                "SELECT status FROM tasks WHERE id = %s FOR UPDATE",
                (task_id,)).fetchone()
            if atual is None:
                raise TransicaoInvalida(f"tarefa {task_id} inexistente")
            if atual["status"] not in de:
                raise TransicaoInvalida(
                    f"tarefa {task_id} está em {atual['status']!r}; "
                    f"{para!r} exige {list(de)}")
            row = self.conn.execute(
                "UPDATE tasks SET status = %s, updated_at = now() "
                "WHERE id = %s RETURNING *", (para, task_id)).fetchone()
            self._log_tarefa(task_id, atual["status"], para, actor, note)
        return _num(row)

    def transicoes_da_tarefa(self, task_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM task_transitions WHERE task_id = %s ORDER BY id",
            (task_id,)).fetchall()

    def promover_prontas(self, unit_id: int, actor: str) -> list[int]:
        """planejada → pronta quando TODAS as dependências estão aceitas.
        Exceção única: para o Verificador, dependência em
        aguardando_verificacao basta — é a tarefa que ele vai verificar, e
        ela só é aceita depois dele."""
        with self.conn.transaction():
            rows = self.conn.execute(
                "UPDATE tasks t SET status = 'pronta', updated_at = now() "
                "WHERE t.unit_id = %s AND t.status = 'planejada' "
                "AND NOT EXISTS (SELECT 1 FROM tasks d "
                "  WHERE d.id = ANY(t.depends_on) AND d.status <> 'aceita' "
                "  AND NOT (t.role = %s AND d.status = %s)) "
                "RETURNING t.id",
                (unit_id, VERIFICADOR, "aguardando_verificacao")).fetchall()
            ids = sorted(r["id"] for r in rows)
            for i in ids:
                self._log_tarefa(i, "planejada", "pronta", actor,
                                 "dependências aceitas")
        return ids

    def bloquear_pendentes(self, unit_id: int, actor: str,
                           note: str) -> list[int]:
        with self.conn.transaction():
            rows = self.conn.execute(
                "UPDATE tasks t SET status = 'bloqueada', updated_at = now() "
                "FROM tasks old WHERE old.id = t.id AND t.unit_id = %s "
                "AND t.status = ANY(%s) RETURNING t.id, old.status AS de",
                (unit_id, list(PENDENTES))).fetchall()
            for r in rows:
                self._log_tarefa(r["id"], r["de"], "bloqueada", actor, note)
        return sorted(r["id"] for r in rows)

    # --- runs e trava ------------------------------------------------------
    def liberar_leases_vencidos(self, unit_id: int, actor: str) -> list[int]:
        with self.conn.transaction():
            rows = self.conn.execute(
                "UPDATE task_runs r SET finished_at = now(), "
                "stop_reason = 'lease_expirado' FROM tasks t "
                "WHERE r.task_id = t.id AND t.unit_id = %s "
                "AND r.finished_at IS NULL AND r.lease_until < now() "
                "RETURNING r.task_id", (unit_id,)).fetchall()
            ids = sorted(r["task_id"] for r in rows)
            for i in ids:
                self.transicionar_tarefa(i, ("em_execucao",), "pronta", actor,
                                         "lease expirado")
        return ids

    def pegar_tarefa(self, unit_id: int, worker: str,
                     versoes_funcao: dict[str, str],
                     versoes_pacote: dict[str, str],
                     lease_segundos: int,
                     excluir_roles: tuple[str, ...] = ()
                     ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        with self.conn.transaction():
            t = self.conn.execute(
                "SELECT * FROM tasks WHERE unit_id = %s AND status = 'pronta' "
                "AND NOT (role = ANY(%s)) "
                "ORDER BY priority, id LIMIT 1 FOR UPDATE SKIP LOCKED",
                (unit_id, list(excluir_roles))).fetchone()
            if t is None:
                return None
            role_v = versoes_funcao.get(t["role"])
            if not role_v:
                raise ValueError(f"versao_da_funcao_ausente: {t['role']!r}")
            pack_v = None
            if t["pack"]:
                pack_v = versoes_pacote.get(t["pack"])
                if not pack_v:
                    raise ValueError(
                        f"versao_do_pacote_ausente: {t['pack']!r}")
            task = self.conn.execute(
                "UPDATE tasks SET status = 'em_execucao', updated_at = now() "
                "WHERE id = %s RETURNING *", (t["id"],)).fetchone()
            self._log_tarefa(t["id"], "pronta", "em_execucao", worker, "")
            run = self.conn.execute(
                "INSERT INTO task_runs (task_id, worker, role_version, "
                "pack_version, lease_until) VALUES (%s, %s, %s, %s, "
                "now() + make_interval(secs => %s)) RETURNING *",
                (t["id"], worker, role_v, pack_v, lease_segundos)).fetchone()
        return _num(task), _num(run)

    def renovar_lease(self, run_id: int, worker: str,
                      lease_segundos: int) -> None:
        got = self.conn.execute(
            "UPDATE task_runs SET lease_until = now() + make_interval("
            "secs => %s) WHERE id = %s AND worker = %s AND finished_at IS NULL "
            "RETURNING id", (lease_segundos, run_id, worker)).fetchone()
        if got is None:
            raise TransicaoInvalida(
                f"run {run_id} fechado ou de outro worker")

    def fechar_run(self, run_id: int, worker: str, *, output_json: Any,
                   output_valid: bool, validation_errors: list[str],
                   stop_reason: str, para: str, nota: str = "",
                   model: str = "", model_family: str = "",
                   prompt_sha256: str | None = None, tokens_in: int = 0,
                   tokens_out: int = 0, cost_usd: float = 0.0
                   ) -> dict[str, Any]:
        """Fecha o run do próprio worker e leva a tarefa de em_execucao a
        `para` na MESMA transação; devolve a tarefa (queda no meio não deixa tarefa órfã).
        Custo entra também em cost_entries (categoria `tarefa`), o mesmo
        livro do teto da unit."""
        from src.casefile.repo import _json
        with self.conn.transaction():
            run = self.conn.execute(
                "UPDATE task_runs SET output_json = %s, output_valid = %s, "
                "validation_errors = %s, stop_reason = %s, model = %s, "
                "model_family = %s, prompt_sha256 = %s, tokens_in = %s, "
                "tokens_out = %s, cost_usd = %s, finished_at = now() "
                "WHERE id = %s AND worker = %s AND finished_at IS NULL "
                "RETURNING *",
                (_json(output_json), output_valid, _json(validation_errors),
                 stop_reason, model, model_family, prompt_sha256, tokens_in,
                 tokens_out, cost_usd, run_id, worker)).fetchone()
            if run is None:
                raise TransicaoInvalida(
                    f"run {run_id} já fechado (lease vencido?) ou de outro "
                    f"worker")
            t = self.transicionar_tarefa(run["task_id"], ("em_execucao",),
                                         para, worker, nota)
            if cost_usd:
                self.registrar_custo(
                    t["unit_id"], "tarefa", cost_usd,
                    {"task_id": t["id"], "run_id": run_id, "role": t["role"]})
        return t

    def run(self, run_id: int) -> dict[str, Any] | None:
        return _num(self.conn.execute(
            "SELECT * FROM task_runs WHERE id = %s", (run_id,)).fetchone())

    def runs_da_tarefa(self, task_id: int) -> list[dict[str, Any]]:
        return [_num(r) for r in self.conn.execute(
            "SELECT * FROM task_runs WHERE task_id = %s ORDER BY id",
            (task_id,)).fetchall()]

    # --- claims da tarefa ----------------------------------------------------
    def vincular_claims(self, task_id: int, claim_ids: list[int]) -> None:
        t = self.tarefa(task_id)
        with self.conn.transaction():
            for cid in claim_ids:
                if not self.claim_existe(t["unit_id"], cid):
                    raise ValueError(f"claim_fora_da_unit: {cid}")
                self.conn.execute(
                    "INSERT INTO task_claims (task_id, claim_id) VALUES "
                    "(%s, %s) ON CONFLICT DO NOTHING", (task_id, cid))

    def claims_da_tarefa(self, task_id: int) -> list[int]:
        return [r["claim_id"] for r in self.conn.execute(
            "SELECT claim_id FROM task_claims WHERE task_id = %s "
            "ORDER BY claim_id", (task_id,)).fetchall()]

    # --- propostas de grafo do Coordenador ---------------------------------
    def registrar_proposta(self, unit_id: int, task_id: int,
                           run_id: int | None, pack: str, plan: Any,
                           targets: Any, coverage: Any) -> int:
        """Grava a proposta; propostas ainda abertas da unit viram
        `substituida` (preservadas, nunca apagadas)."""
        from src.casefile.repo import _json
        with self.conn.transaction():
            self.conn.execute(
                "UPDATE plan_proposals SET status = 'substituida' "
                "WHERE unit_id = %s AND status = 'proposta'", (unit_id,))
            return self.conn.execute(
                "INSERT INTO plan_proposals (unit_id, task_id, run_id, pack, "
                "plan, targets, coverage) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (unit_id, task_id, run_id, pack, _json(plan), _json(targets),
                 _json(coverage))).fetchone()["id"]

    def proposta(self, proposal_id: int) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM plan_proposals WHERE id = %s",
            (proposal_id,)).fetchone()

    def propostas(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM plan_proposals WHERE unit_id = %s ORDER BY id",
            (unit_id,)).fetchall()

    def aprovar_proposta(self, proposal_id: int,
                         linhas: list[dict[str, Any]], criado_por: str,
                         decidido_por: str, nota: str) -> list[dict[str, Any]]:
        """proposta → aprovada e criação das tarefas na MESMA transação."""
        with self.conn.transaction():
            got = self.conn.execute(
                "SELECT unit_id, status FROM plan_proposals WHERE id = %s "
                "FOR UPDATE", (proposal_id,)).fetchone()
            if got is None or got["status"] != "proposta":
                raise TransicaoInvalida(
                    f"proposta {proposal_id} não está aberta "
                    f"({got and got['status']!r})")
            criadas = self.criar_tarefas(got["unit_id"], linhas, criado_por)
            self.conn.execute(
                "UPDATE plan_proposals SET status = 'aprovada', "
                "decided_by = %s, decided_at = now(), decision_note = %s, "
                "applied_task_ids = %s WHERE id = %s",
                (decidido_por, nota, [t["id"] for t in criadas],
                 proposal_id))
        return criadas

    def recusar_proposta(self, proposal_id: int, decidido_por: str,
                         nota: str) -> None:
        got = self.conn.execute(
            "UPDATE plan_proposals SET status = 'recusada', decided_by = %s, "
            "decided_at = now(), decision_note = %s WHERE id = %s "
            "AND status = 'proposta' RETURNING id",
            (decidido_por, nota, proposal_id)).fetchone()
        if got is None:
            raise TransicaoInvalida(f"proposta {proposal_id} não está aberta")

    # --- escalonamentos ------------------------------------------------------
    def abrir_escalonamento(self, unit_id: int, task_id: int | None,
                            motivo: str, pergunta: str,
                            opcoes: list[str]) -> int:
        from src.casefile.repo import _json
        return self.conn.execute(
            "INSERT INTO escalations (unit_id, task_id, motivo, pergunta, "
            "opcoes) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (unit_id, task_id, motivo, pergunta, _json(opcoes))
        ).fetchone()["id"]

    def responder_escalonamento(self, escalation_id: int, resposta: str,
                                por: str) -> None:
        got = self.conn.execute(
            "UPDATE escalations SET resposta = %s, respondido_por = %s, "
            "respondido_em = now() WHERE id = %s AND respondido_em IS NULL "
            "RETURNING id", (resposta, por, escalation_id)).fetchone()
        if got is None:
            raise TransicaoInvalida(
                f"escalonamento {escalation_id} inexistente ou já respondido")

    def escalonamentos(self, unit_id: int, abertos: bool = False
                       ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM escalations WHERE unit_id = %s"
        if abertos:
            sql += " AND respondido_em IS NULL"
        return self.conn.execute(sql + " ORDER BY id", (unit_id,)).fetchall()
