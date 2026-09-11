"""O DAO do Case File — uma função nomeada por operação, SQL à vista.

Esta é a interface que `tests/helpers_casefile.py::RepoFake` implementa em
memória: todo código do casefile fala com o banco SÓ por aqui. Nenhum método
julga title — inserem-se fatos, contam-se linhas, confere-se identidade.
"""
from __future__ import annotations

from typing import Any
from src.casefile.training_repo import TrainingRepo


def _json(valor: Any) -> Any:
    from psycopg.types.json import Json
    return Json(valor)


class Repo(TrainingRepo):
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

    def nomes_por_origem(self, unit_id: int) -> dict[str, set[str]]:
        rows = self.conn.execute(
            "SELECT logical_name, origin FROM file_sightings "
            "WHERE unit_id = %s OR unit_id IS NULL", (unit_id,)).fetchall()
        out: dict[str, set[str]] = {}
        for r in rows:
            out.setdefault(r["logical_name"], set()).add(r["origin"])
        return out

    def origens_do_sha(self, sha256: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT s.origin FROM file_sightings s "
            "JOIN source_files f ON f.id = s.source_file_id "
            "WHERE f.sha256 = %s", (sha256,)).fetchall()
        return {r["origin"] for r in rows}

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

    # --- VS2: condições da aprovação -----------------------------------------
    def condicoes(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM operator_decisions WHERE unit_id = %s "
            "AND kind = 'condicao_aprovacao' ORDER BY id",
            (unit_id,)).fetchall()

    def politica(self, unit_id: int, chave: str) -> str | None:
        got = self.conn.execute(
            "SELECT answer FROM operator_decisions WHERE unit_id = %s AND "
            "kind = 'politica' AND question = %s ORDER BY id DESC LIMIT 1",
            (unit_id, f"[{chave}]")).fetchone()
        return got["answer"] if got else None

    def registrar_politica(self, unit_id: int, chave: str,
                           valor: str) -> None:
        self.conn.execute(
            "INSERT INTO operator_decisions (unit_id, kind, question, "
            "answer, decided_at) VALUES (%s, 'politica', %s, %s, now())",
            (unit_id, f"[{chave}]", valor))

    def registrar_pergunta_vs2(self, unit_id: int, question: str,
                               claim_id: int | None = None) -> int:
        return self.conn.execute(
            "INSERT INTO operator_decisions (unit_id, kind, question, "
            "claim_id) VALUES (%s, 'pergunta_vs2', %s, %s) RETURNING id",
            (unit_id, question, claim_id)).fetchone()["id"]

    def perguntas_vs2_abertas(self, unit_id: int,
                              assunto: str = "") -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM operator_decisions WHERE unit_id = %s AND kind = "
            "'pergunta_vs2' AND answer = '' AND lower(question) LIKE %s "
            "ORDER BY id", (unit_id, f"%{assunto.lower()}%")).fetchall()

    # --- VS2: índice local de workbooks --------------------------------------
    def registrar_xref_lookup(self, unit_id: int, source_sha256: str,
                              key_kind: str, key_value: str,
                              rows_found: int) -> None:
        self.conn.execute(
            "INSERT INTO xref_lookups (unit_id, source_sha256, key_kind, "
            "key_value, rows_found) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (unit_id, source_sha256, key_kind, key_value) "
            "DO UPDATE SET rows_found = EXCLUDED.rows_found, at = now()",
            (unit_id, source_sha256, key_kind, key_value, rows_found))

    def registrar_xref_row(self, unit_id: int, source_sha256: str,
                           sheet: str, row_number: int, row: dict[str, Any],
                           matched_keys: list[str]) -> None:
        self.conn.execute(
            "INSERT INTO xref_rows (unit_id, source_sha256, sheet, "
            "row_number, row, matched_keys) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (unit_id, source_sha256, sheet, row_number) "
            "DO UPDATE SET row = EXCLUDED.row, matched_keys = "
            "EXCLUDED.matched_keys",
            (unit_id, source_sha256, sheet, row_number, _json(row),
             matched_keys))

    def xref_lookups(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM xref_lookups WHERE unit_id = %s ORDER BY id",
            (unit_id,)).fetchall()

    def xref_rows_da_unit(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM xref_rows WHERE unit_id = %s "
            "ORDER BY source_sha256, sheet, row_number",
            (unit_id,)).fetchall()

    # --- VS2: populações ------------------------------------------------------
    def gravar_membro_populacao(self, unit_id: int, population: str,
                                member: str, origem: str = "",
                                note: str = "") -> None:
        self.conn.execute(
            "INSERT INTO population_members (unit_id, population, member, "
            "origem, note) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (unit_id, population, member) DO UPDATE SET "
            "origem = EXCLUDED.origem, note = EXCLUDED.note",
            (unit_id, population, member, origem, note))

    def limpar_populacao(self, unit_id: int, population: str) -> None:
        self.conn.execute(
            "DELETE FROM population_members WHERE unit_id = %s "
            "AND population = %s", (unit_id, population))

    def populacao(self, unit_id: int, population: str
                  ) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM population_members WHERE unit_id = %s "
            "AND population = %s ORDER BY member",
            (unit_id, population)).fetchall()

    def populacoes_contagens(self, unit_id: int) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT population, count(*) AS n FROM population_members "
            "WHERE unit_id = %s GROUP BY population", (unit_id,)).fetchall()
        return {r["population"]: r["n"] for r in rows}

    # --- VS2: buscas negativas ------------------------------------------------
    def registrar_busca(self, unit_id: int, target: str,
                        terms: list[str], scope: str, names_scanned: int,
                        hits: list[dict[str, Any]],
                        result: str = "pendente_julgamento") -> int:
        return self.conn.execute(
            "INSERT INTO negative_searches (unit_id, target, terms, scope, "
            "names_scanned, hits, result) VALUES (%s, %s, %s, %s, %s, %s, "
            "%s) RETURNING id",
            (unit_id, target, _json(terms), scope, names_scanned,
             _json(hits), result)).fetchone()["id"]

    def julgar_busca(self, search_id: int, result: str, evidence: str,
                     session_id: int | None = None) -> None:
        self.conn.execute(
            "UPDATE negative_searches SET result = %s, evidence = %s, "
            "session_id = %s WHERE id = %s",
            (result, evidence, session_id, search_id))

    def buscas(self, unit_id: int, target: str | None = None
               ) -> list[dict[str, Any]]:
        if target is not None:
            return self.conn.execute(
                "SELECT * FROM negative_searches WHERE unit_id = %s "
                "AND target = %s ORDER BY id", (unit_id, target)).fetchall()
        return self.conn.execute(
            "SELECT * FROM negative_searches WHERE unit_id = %s ORDER BY id",
            (unit_id,)).fetchall()

    # --- VS2: itens de coleta -------------------------------------------------
    def criar_collection_item(self, unit_id: int, title: str, method: str,
                              target: dict[str, Any],
                              research_item_id: int | None = None) -> int:
        got = self.conn.execute(
            "SELECT id FROM collection_items WHERE unit_id = %s "
            "AND title = %s AND status != 'cancelado'",
            (unit_id, title)).fetchone()
        if got:
            return got["id"]
        return self.conn.execute(
            "INSERT INTO collection_items (unit_id, title, method, target, "
            "research_item_id) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (unit_id, title, method, _json(target),
             research_item_id)).fetchone()["id"]

    def atualizar_collection_item(self, item_id: int, **campos: Any) -> None:
        permitidos = ("status", "staged_path", "promoted_path", "sha256",
                      "provenance", "cost_usd", "note")
        sets, valores = [], []
        for chave, valor in campos.items():
            if chave not in permitidos:
                raise ValueError(f"campo desconhecido: {chave}")
            sets.append(f"{chave} = %s")
            valores.append(_json(valor) if chave == "provenance" else valor)
        if not sets:
            return
        sets.append("updated_at = now()")
        self.conn.execute(
            f"UPDATE collection_items SET {', '.join(sets)} WHERE id = %s",
            (*valores, item_id))

    def collection_items(self, unit_id: int, status: str | None = None
                         ) -> list[dict[str, Any]]:
        if status is not None:
            return self.conn.execute(
                "SELECT * FROM collection_items WHERE unit_id = %s "
                "AND status = %s ORDER BY id", (unit_id, status)).fetchall()
        return self.conn.execute(
            "SELECT * FROM collection_items WHERE unit_id = %s ORDER BY id",
            (unit_id,)).fetchall()

    def custo_por_categoria(self, unit_id: int) -> dict[str, float]:
        rows = self.conn.execute(
            "SELECT category, round(sum(amount_usd), 4) AS total "
            "FROM cost_entries WHERE unit_id = %s GROUP BY category",
            (unit_id,)).fetchall()
        return {r["category"]: float(r["total"]) for r in rows}

    # --- VS2: pesquisas -------------------------------------------------------
    def pesquisas(self, unit_id: int, status: str | None = None
                  ) -> list[dict[str, Any]]:
        if status is not None:
            return self.conn.execute(
                "SELECT * FROM research_items WHERE unit_id = %s "
                "AND status = %s ORDER BY id", (unit_id, status)).fetchall()
        return self.conn.execute(
            "SELECT * FROM research_items WHERE unit_id = %s ORDER BY id",
            (unit_id,)).fetchall()

    def marcar_pesquisa(self, research_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE research_items SET status = %s, executed_at = "
            "CASE WHEN %s = 'executada' THEN now() ELSE executed_at END "
            "WHERE id = %s", (status, status, research_id))

    # --- VS3: verificação cega e posições ------------------------------------
    def registrar_verificacao(self, claim_id: int, question: str,
                              verdict: str, verifier_model: str,
                              verifier_value: dict[str, Any],
                              comparison: dict[str, Any], cost_usd: float,
                              session_id: int | None = None,
                              rastreio: dict[str, Any] | None = None) -> int:
        r = rastreio or {}
        return self.conn.execute(
            "INSERT INTO verifications (claim_id, question, verdict, "
            "verifier_model, verifier_value, comparison, cost_usd, "
            "session_id, source_sha256, page, evidence_payload_sha256, "
            "prompt_sha256, raw_response, request_id, model_params) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s) RETURNING id",
            (claim_id, question, verdict, verifier_model,
             _json(verifier_value), _json(comparison), cost_usd, session_id,
             r.get("source_sha256"), r.get("page", ""),
             r.get("evidence_payload_sha256"), r.get("prompt_sha256"),
             r.get("raw_response", "")[:20000], r.get("request_id", ""),
             _json(r.get("model_params", {})))).fetchone()["id"]

    def invalidar_verificacao(self, verification_id: int,
                              reason: str) -> None:
        self.conn.execute(
            "UPDATE verifications SET status = 'invalidada', "
            "invalidation_reason = %s WHERE id = %s",
            (reason, verification_id))

    def atualizar_claim_status(self, unit_id: int, claim_id: int,
                               status: str, superseded_by: int | None = None,
                               nota: str = "") -> None:
        got = self.conn.execute(
            "UPDATE claims SET status = %s, superseded_by = %s, "
            "limitations = CASE WHEN %s != '' THEN %s ELSE limitations END "
            "WHERE id = %s AND unit_id = %s RETURNING id",
            (status, superseded_by, nota, nota, claim_id,
             unit_id)).fetchone()
        if got is None:
            raise ValueError(f"claim {claim_id} nao e da unit {unit_id}")

    def responder_pergunta_vs2(self, decision_id: int, answer: str) -> None:
        self.conn.execute(
            "UPDATE operator_decisions SET answer = %s, decided_at = now() "
            "WHERE id = %s AND kind = 'pergunta_vs2'", (answer, decision_id))

    def verificacoes(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT v.* FROM verifications v JOIN claims c ON "
            "c.id = v.claim_id WHERE c.unit_id = %s ORDER BY v.id",
            (unit_id,)).fetchall()

    def verificacoes_do_claim(self, claim_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM verifications WHERE claim_id = %s ORDER BY id",
            (claim_id,)).fetchall()

    def gravar_posicao(self, unit_id: int, population_item: str,
                       classification: str, claim_ids: list[int],
                       note: str, session_id: int | None) -> None:
        self.conn.execute(
            "INSERT INTO population_positions (unit_id, population_item, "
            "classification, claim_ids, note, session_id) VALUES "
            "(%s, %s, %s, %s, %s, %s) ON CONFLICT (unit_id, "
            "population_item) DO UPDATE SET classification = "
            "EXCLUDED.classification, claim_ids = EXCLUDED.claim_ids, "
            "note = EXCLUDED.note, session_id = EXCLUDED.session_id, "
            "at = now()",
            (unit_id, population_item, classification, claim_ids, note,
             session_id))

    def posicoes(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM population_positions WHERE unit_id = %s "
            "ORDER BY population_item", (unit_id,)).fetchall()

    def atualizar_claim_ddr(self, unit_id: int, claim_id: int,
                            ddr_candidates: list[Any],
                            limitations: str) -> None:
        got = self.conn.execute(
            "UPDATE claims SET ddr_candidates = %s, limitations = %s "
            "WHERE id = %s AND unit_id = %s RETURNING id",
            (_json(ddr_candidates), limitations, claim_id,
             unit_id)).fetchone()
        if got is None:
            raise ValueError(f"claim {claim_id} nao e da unit {unit_id}")

    def sessoes_da_unit(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM model_sessions WHERE unit_id = %s ORDER BY id",
            (unit_id,)).fetchall()

    def decisoes_da_unit(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM operator_decisions WHERE unit_id = %s "
            "ORDER BY id", (unit_id,)).fetchall()

    def custos_da_unit(self, unit_id: int) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM cost_entries WHERE unit_id = %s ORDER BY id",
            (unit_id,)).fetchall()

    def claim(self, claim_id: int) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM claims WHERE id = %s", (claim_id,)).fetchone()

    def registrar_deliverable(self, unit_id: int, kind: str, version: int,
                              path: str, sha256: str,
                              lifecycle: str = "final") -> None:
        self.conn.execute(
            "INSERT INTO deliverable_versions (unit_id, kind, version, "
            "path, sha256, lifecycle) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (unit_id, kind, version) DO UPDATE SET "
            "path = EXCLUDED.path, sha256 = EXCLUDED.sha256, "
            "lifecycle = EXCLUDED.lifecycle",
            (unit_id, kind, version, path, sha256, lifecycle))

    def deliverables(self, unit_id: int, kind: str) -> list[dict[str, Any]]:
        return self.conn.execute(
            "SELECT * FROM deliverable_versions WHERE unit_id = %s "
            "AND kind = %s ORDER BY version", (unit_id, kind)).fetchall()

    def claims_da_unit(self, unit_id: int, claim_type: str | None = None
                       ) -> list[dict[str, Any]]:
        if claim_type is not None:
            return self.conn.execute(
                "SELECT * FROM claims WHERE unit_id = %s AND claim_type = %s"
                " AND status = 'ativo' ORDER BY id",
                (unit_id, claim_type)).fetchall()
        return self.conn.execute(
            "SELECT * FROM claims WHERE unit_id = %s AND status = 'ativo' "
            "ORDER BY id", (unit_id,)).fetchall()
