"""O DAO do Case File — uma função nomeada por operação, SQL à vista.

Esta é a interface que `tests/helpers_casefile.py::RepoFake` implementa em
memória: todo código do casefile fala com o banco SÓ por aqui. Nenhum método
julga title — inserem-se fatos, contam-se linhas, confere-se identidade.
"""
from __future__ import annotations

from typing import Any


def _json(valor: Any) -> Any:
    from psycopg.types.json import Json
    return Json(valor)


class Repo:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    # --- projetos e units --------------------------------------------------
    def obter_ou_criar_projeto(self, engagement: str, name: str,
                               root_path: str) -> dict[str, Any]:
        got = self.conn.execute(
            "SELECT * FROM projects WHERE root_path = %s",
            (root_path,)).fetchone()
        if got:
            return got
        return self.conn.execute(
            "INSERT INTO projects (engagement, name, root_path) "
            "VALUES (%s, %s, %s) RETURNING *",
            (engagement, name, root_path)).fetchone()

    def obter_ou_criar_unit(self, project_id: int, name_input: str,
                            canonical_name: str, folder_path: str
                            ) -> tuple[dict[str, Any], bool]:
        got = self.conn.execute(
            "SELECT * FROM units WHERE project_id = %s "
            "AND upper(canonical_name) = upper(%s)",
            (project_id, canonical_name)).fetchone()
        if got:
            return got, False
        unit = self.conn.execute(
            "INSERT INTO units (project_id, name_input, canonical_name, "
            "folder_path) VALUES (%s, %s, %s, %s) RETURNING *",
            (project_id, name_input, canonical_name, folder_path)).fetchone()
        return unit, True

    def obter_unit_por_nome(self, nome: str) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM units WHERE upper(canonical_name) = upper(%s) "
            "ORDER BY id LIMIT 1", (nome.strip(),)).fetchone()

    def listar_units(self) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT u.*, p.engagement FROM units u "
            "JOIN projects p ON p.id = u.project_id ORDER BY u.id").fetchall()

    # --- estados -----------------------------------------------------------
    def estado_da_unit(self, unit_id: int) -> str:
        return self.conn.execute(
            "SELECT state FROM units WHERE id = %s",
            (unit_id,)).fetchone()["state"]

    def transicionar(self, unit_id: int, from_state: str, to_state: str,
                     event: str, actor: str, note: str = "") -> None:
        # Atômico: o UPDATE condicionado ao estado atual é a prova de que
        # ninguém transicionou no meio; 0 linhas afetadas é erro, não warning.
        with self.conn.transaction():
            got = self.conn.execute(
                "UPDATE units SET state = %s WHERE id = %s AND state = %s "
                "RETURNING id", (to_state, unit_id, from_state)).fetchone()
            if got is None and from_state != "":
                raise AssertionError(
                    f"transicao perdeu a corrida: unit {unit_id} nao esta "
                    f"mais em {from_state}")
            self.conn.execute(
                "INSERT INTO unit_state_transitions "
                "(unit_id, from_state, to_state, event, actor, note) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (unit_id, from_state, to_state, event, actor, note))

    def transicoes(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM unit_state_transitions WHERE unit_id = %s "
            "ORDER BY id", (unit_id,)).fetchall()

    # --- fontes ------------------------------------------------------------
    def registrar_source_file(self, sha256: str, size_bytes: int) -> int:
        got = self.conn.execute(
            "INSERT INTO source_files (sha256, size_bytes) VALUES (%s, %s) "
            "ON CONFLICT (sha256) DO UPDATE SET size_bytes = "
            "source_files.size_bytes RETURNING id",
            (sha256, size_bytes)).fetchone()
        return got["id"]

    def registrar_sighting(self, source_file_id: int, unit_id: int | None,
                           container_path: str, zip_member: str,
                           logical_name: str, origin: str,
                           mtime: Any = None) -> None:
        self.conn.execute(
            "INSERT INTO file_sightings (source_file_id, unit_id, "
            "container_path, zip_member, logical_name, origin, mtime) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (source_file_id, container_path, zip_member) "
            "DO UPDATE SET logical_name = EXCLUDED.logical_name, "
            "origin = EXCLUDED.origin, seen_at = now()",
            (source_file_id, unit_id, container_path, zip_member,
             logical_name, origin, mtime))

    def sha_por_nome(self, unit_id: int) -> dict[str, list[str]]:
        """logical_name -> hashes distintos. Mais de um hash para o mesmo nome
        é a armadilha do XREF homônimo — fato exposto, nunca resolvido aqui."""
        rows = self.conn.execute(
            "SELECT s.logical_name, f.sha256 FROM file_sightings s "
            "JOIN source_files f ON f.id = s.source_file_id "
            "WHERE s.unit_id = %s OR s.unit_id IS NULL", (unit_id,)).fetchall()
        out: dict[str, list[str]] = {}
        for r in rows:
            hashes = out.setdefault(r["logical_name"], [])
            if r["sha256"] not in hashes:
                hashes.append(r["sha256"])
        return out

    def sha_existe(self, sha256: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM source_files WHERE sha256 = %s",
            (sha256,)).fetchone() is not None

    def contagem_censo(self, unit_id: int) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT s.origin, count(*) AS sightings, "
            "count(DISTINCT s.source_file_id) AS conteudos "
            "FROM file_sightings s WHERE s.unit_id = %s OR s.unit_id IS NULL "
            "GROUP BY s.origin ORDER BY s.origin", (unit_id,)).fetchall()
        return {r["origin"]: {"sightings": r["sightings"],
                              "conteudos": r["conteudos"]} for r in rows}

    # --- triagem -----------------------------------------------------------
    def gravar_rotulo(self, source_file_id: int, unit_id: int, label: str,
                      summary: str, confidence: str,
                      session_id: int | None) -> None:
        self.conn.execute(
            "INSERT INTO triage_labels (source_file_id, unit_id, label, "
            "summary, confidence, session_id) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (source_file_id, unit_id) DO UPDATE SET "
            "label = EXCLUDED.label, summary = EXCLUDED.summary, "
            "confidence = EXCLUDED.confidence, session_id = EXCLUDED.session_id",
            (source_file_id, unit_id, label, summary, confidence, session_id))

    def rotulos(self, unit_id: int) -> dict[str, dict[str, str]]:
        """sha256 -> rótulo da triagem."""
        rows = self.conn.execute(
            "SELECT f.sha256, t.label, t.summary, t.confidence "
            "FROM triage_labels t JOIN source_files f "
            "ON f.id = t.source_file_id WHERE t.unit_id = %s",
            (unit_id,)).fetchall()
        return {r["sha256"]: {"rotulo": r["label"], "resumo": r["summary"],
                              "confianca": r["confidence"]} for r in rows}

    def source_file_id_por_sha(self, sha256: str) -> int | None:
        got = self.conn.execute(
            "SELECT id FROM source_files WHERE sha256 = %s",
            (sha256,)).fetchone()
        return got["id"] if got else None

    # --- claims ------------------------------------------------------------
    def tipos_de_claim(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM claim_types WHERE active").fetchall()
        return {r["claim_type"]: r for r in rows}

    def inserir_claim(self, unit_id: int, claim_type: str, entity: str,
                      value: dict[str, Any], source_sha256: str, page: str,
                      evidence: str, confidence: str, materiality: str,
                      session_id: int) -> int:
        got = self.conn.execute(
            "INSERT INTO claims (unit_id, claim_type, entity, value, "
            "source_sha256, page, evidence, confidence, materiality, "
            "session_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "RETURNING id",
            (unit_id, claim_type, entity, _json(value), source_sha256, page,
             evidence, confidence, materiality, session_id)).fetchone()
        return got["id"]

    def contagens_claims(self, unit_id: int) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT claim_type, count(*) AS n FROM claims "
            "WHERE unit_id = %s AND status = 'ativo' GROUP BY claim_type",
            (unit_id,)).fetchall()
        return {r["claim_type"]: r["n"] for r in rows}

    def claim_existe(self, unit_id: int, claim_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM claims WHERE id = %s AND unit_id = %s",
            (claim_id, unit_id)).fetchone() is not None

    # --- pesquisas ---------------------------------------------------------
    def inserir_pesquisa(self, unit_id: int, title: str, what: str,
                         where: str, method: str, session_id: int,
                         claim_ids: list[int]) -> int:
        with self.conn.transaction():
            got = self.conn.execute(
                "INSERT INTO research_items (unit_id, title, what, where_, "
                "method, session_id) VALUES (%s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (unit_id, title, what, where, method, session_id)).fetchone()
            for cid in claim_ids:
                self.conn.execute(
                    "INSERT INTO research_item_claims (research_item_id, "
                    "claim_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (got["id"], cid))
        return got["id"]

    def contagem_pesquisas(self, unit_id: int) -> int:
        return self.conn.execute(
            "SELECT count(*) AS n FROM research_items "
            "WHERE unit_id = %s AND status = 'aberta'",
            (unit_id,)).fetchone()["n"]

    # --- sessões e custo ---------------------------------------------------
    def abrir_sessao(self, unit_id: int, command: str, model: str) -> int:
        return self.conn.execute(
            "INSERT INTO model_sessions (unit_id, command, model) "
            "VALUES (%s, %s, %s) RETURNING id",
            (unit_id, command, model)).fetchone()["id"]

    def fechar_sessao(self, session_id: int, stop_reason: str, turns: int,
                      usage: dict[str, Any], cost_usd: float | None,
                      log_path: str) -> None:
        self.conn.execute(
            "UPDATE model_sessions SET ended_at = now(), stop_reason = %s, "
            "turns = %s, usage = %s, cost_usd = %s, log_path = %s "
            "WHERE id = %s",
            (stop_reason, turns, _json(usage), cost_usd, log_path, session_id))

    def registrar_custo(self, unit_id: int, category: str, amount_usd: float,
                        detail: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO cost_entries (unit_id, category, amount_usd, detail)"
            " VALUES (%s, %s, %s, %s)",
            (unit_id, category, amount_usd, _json(detail)))

    def custo_acumulado(self, unit_id: int) -> float:
        got = self.conn.execute(
            "SELECT coalesce(sum(amount_usd), 0) AS total FROM cost_entries "
            "WHERE unit_id = %s", (unit_id,)).fetchone()
        return round(float(got["total"]), 4)

    # --- planos ------------------------------------------------------------
    def propor_plano(self, unit_id: int, markdown: str,
                     resumo: dict[str, Any], session_id: int
                     ) -> dict[str, Any]:
        with self.conn.transaction():
            self.conn.execute(
                "UPDATE investigation_plans SET status = 'substituido' "
                "WHERE unit_id = %s AND status = 'proposto'", (unit_id,))
            versao = self.conn.execute(
                "SELECT coalesce(max(version), 0) + 1 AS v "
                "FROM investigation_plans WHERE unit_id = %s",
                (unit_id,)).fetchone()["v"]
            return self.conn.execute(
                "INSERT INTO investigation_plans (unit_id, version, markdown,"
                " summary, session_id) VALUES (%s, %s, %s, %s, %s) "
                "RETURNING id, version",
                (unit_id, versao, markdown, _json(resumo),
                 session_id)).fetchone()

    def plano(self, unit_id: int, versao: int | None = None
              ) -> dict[str, Any] | None:
        if versao is not None:
            return self.conn.execute(
                "SELECT * FROM investigation_plans WHERE unit_id = %s "
                "AND version = %s", (unit_id, versao)).fetchone()
        return self.conn.execute(
            "SELECT * FROM investigation_plans WHERE unit_id = %s "
            "ORDER BY version DESC LIMIT 1", (unit_id,)).fetchone()

    def decidir_plano(self, plan_id: int, status: str, decided_by: str,
                      note: str = "") -> None:
        self.conn.execute(
            "UPDATE investigation_plans SET status = %s, decided_by = %s, "
            "decided_at = now(), decision_note = %s WHERE id = %s",
            (status, decided_by, note, plan_id))
