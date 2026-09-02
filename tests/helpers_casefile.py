"""Helpers dos testes do casefile — RepoFake em memória + cliente roteirizado.

RepoFake implementa a MESMA interface de src/casefile/repo.py::Repo sobre
dicts: os testes de encanamento não falam SQL. O cliente roteirizado é cópia
do padrão de tests/test_minorh_etapa_h.py (_ClientRoteirizado, _Msg, _Use,
_Texto, _Uso) — injetado em run_loop pelos comandos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# --- cliente roteirizado (padrão de test_minorh_etapa_h.py) -----------------


@dataclass
class _Uso:
    input_tokens: int = 10
    output_tokens: int = 5
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class Msg:
    content: list[Any]
    usage: _Uso = field(default_factory=_Uso)


@dataclass
class Use:
    name: str
    input: dict[str, Any]
    id: str = "u1"
    type: str = "tool_use"


@dataclass
class Texto:
    text: str
    type: str = "text"


class ClientRoteirizado:
    def __init__(self, roteiro: list[list[Any]]) -> None:
        self.roteiro = roteiro
        self.messages = self

    def create(self, **kw: Any) -> Msg:
        return Msg(content=self.roteiro.pop(0))


# --- seeds (espelho de 0002_seed_claim_types.sql, só os ativos) --------------

CLAIM_TYPES_ATIVOS: dict[str, list[str]] = {
    "unit_identity": ["fonte_autoridade"],
    "xref_row": ["lease_no", "record_type"],
    "lease_in_unit": ["lease_no", "lessor"],
    "tract": ["tract_no"],
    "legal_description": ["texto"],
    "seller_interest": ["party", "papel"],
    "title_opinion": ["to_id"],
    "to_coverage": ["to_id", "cobre"],
    "document_present": ["logical_name"],
    "document_missing": ["esperado", "exigido_por"],
    "divergence": ["fontes"],
    # ativado pela migração 0003 (leituras dirigidas do VS2)
    "fact": [],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar_pg_ou_skip():
    """Conexão ao Postgres de teste num schema temporário, ou skip visível.

    (conn, schema): quem chama dropa o schema no teardown. Sem
    CASEFILE_TEST_DSN alcançável, skip com motivo — nunca falso verde."""
    import os
    import uuid

    import pytest
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except Exception:
        pass
    dsn = os.environ.get("CASEFILE_TEST_DSN", "")
    if not dsn:
        pytest.skip("CASEFILE_TEST_DSN indisponivel (.env)")
    try:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row,
                               connect_timeout=3)
    except Exception as exc:
        pytest.skip(f"Postgres nao responde: {exc.__class__.__name__}")
    schema = f"casefile_t_{uuid.uuid4().hex[:8]}"
    conn.execute(f'CREATE SCHEMA "{schema}"')
    conn.execute(f'SET search_path TO "{schema}"')
    return conn, schema


class RepoFake:
    """A interface de Repo, em memória. Encanamento fiel, sem SQL."""

    def __init__(self) -> None:
        self.projects: list[dict[str, Any]] = []
        self.units: list[dict[str, Any]] = []
        self.transitions: list[dict[str, Any]] = []
        self.source_files: dict[str, dict[str, Any]] = {}   # sha -> row
        self.sightings: list[dict[str, Any]] = []
        self.labels: dict[tuple[int, int], dict[str, Any]] = {}
        self.claims: list[dict[str, Any]] = []
        self.research: list[dict[str, Any]] = []
        self.research_claims: list[tuple[int, int]] = []
        self.sessions: list[dict[str, Any]] = []
        self.costs: list[dict[str, Any]] = []
        self.plans: list[dict[str, Any]] = []
        # VS2
        self.decisions: list[dict[str, Any]] = []
        self.lookups: dict[tuple, int] = {}
        self.xrows: dict[tuple, dict[str, Any]] = {}
        self.members: dict[tuple, dict[str, Any]] = {}
        self.searches: list[dict[str, Any]] = []
        self.items: list[dict[str, Any]] = []
        self.delivs: dict[tuple, dict[str, Any]] = {}

    # --- projetos e units --------------------------------------------------
    def obter_ou_criar_projeto(self, engagement, name, root_path):
        for p in self.projects:
            if p["root_path"] == root_path:
                return p
        p = {"id": len(self.projects) + 1, "engagement": engagement,
             "name": name, "root_path": root_path}
        self.projects.append(p)
        return p

    def obter_ou_criar_unit(self, project_id, name_input, canonical_name,
                            folder_path):
        for u in self.units:
            if u["project_id"] == project_id and \
                    u["canonical_name"].upper() == canonical_name.upper():
                return u, False
        u = {"id": len(self.units) + 1, "project_id": project_id,
             "name_input": name_input, "canonical_name": canonical_name,
             "folder_path": folder_path, "state": "INDICADA"}
        self.units.append(u)
        return u, True

    def obter_unit_por_nome(self, nome):
        alvo = nome.strip().upper()
        for u in self.units:
            if u["canonical_name"].upper() == alvo:
                return u
        return None

    def listar_units(self):
        return list(self.units)

    # --- estados -----------------------------------------------------------
    def estado_da_unit(self, unit_id):
        return self._unit(unit_id)["state"]

    def transicionar(self, unit_id, from_state, to_state, event, actor,
                     note=""):
        unit = self._unit(unit_id)
        if from_state != "" and unit["state"] != from_state:
            raise AssertionError(
                f"transicao perdeu a corrida: unit {unit_id} nao esta mais "
                f"em {from_state}")
        unit["state"] = to_state
        self.transitions.append(
            {"unit_id": unit_id, "from_state": from_state,
             "to_state": to_state, "event": event, "actor": actor,
             "note": note, "at": _now()})

    def transicoes(self, unit_id):
        return [t for t in self.transitions if t["unit_id"] == unit_id]

    # --- fontes ------------------------------------------------------------
    def registrar_source_file(self, sha256, size_bytes):
        row = self.source_files.setdefault(
            sha256, {"id": len(self.source_files) + 1, "sha256": sha256,
                     "size_bytes": size_bytes})
        return row["id"]

    def registrar_sighting(self, source_file_id, unit_id, container_path,
                           zip_member, logical_name, origin, mtime=None):
        for s in self.sightings:
            if (s["source_file_id"], s["container_path"],
                    s["zip_member"]) == (source_file_id, container_path,
                                         zip_member):
                s.update(logical_name=logical_name, origin=origin)
                return
        self.sightings.append(
            {"source_file_id": source_file_id, "unit_id": unit_id,
             "container_path": container_path, "zip_member": zip_member,
             "logical_name": logical_name, "origin": origin, "mtime": mtime})

    def sha_por_nome(self, unit_id):
        por_id = {r["id"]: sha for sha, r in self.source_files.items()}
        out: dict[str, list[str]] = {}
        for s in self.sightings:
            if s["unit_id"] not in (unit_id, None):
                continue
            sha = por_id[s["source_file_id"]]
            hashes = out.setdefault(s["logical_name"], [])
            if sha not in hashes:
                hashes.append(sha)
        return out

    def sha_existe(self, sha256):
        return sha256 in self.source_files

    def nomes_por_origem(self, unit_id):
        out = {}
        for s in self.sightings:
            if s["unit_id"] in (unit_id, None):
                out.setdefault(s["logical_name"], set()).add(s["origin"])
        return out

    def origens_do_sha(self, sha256):
        row = self.source_files.get(sha256)
        if not row:
            return set()
        return {s["origin"] for s in self.sightings
                if s["source_file_id"] == row["id"]}

    def contagem_censo(self, unit_id):
        out: dict[str, dict[str, Any]] = {}
        for s in self.sightings:
            if s["unit_id"] not in (unit_id, None):
                continue
            d = out.setdefault(s["origin"],
                               {"sightings": 0, "_conteudos": set()})
            d["sightings"] += 1
            d["_conteudos"].add(s["source_file_id"])
        return {o: {"sightings": d["sightings"],
                    "conteudos": len(d["_conteudos"])}
                for o, d in out.items()}

    # --- triagem -----------------------------------------------------------
    def gravar_rotulo(self, source_file_id, unit_id, label, summary,
                      confidence, session_id):
        self.labels[(source_file_id, unit_id)] = {
            "label": label, "summary": summary, "confidence": confidence,
            "session_id": session_id}

    def rotulos(self, unit_id):
        por_id = {r["id"]: sha for sha, r in self.source_files.items()}
        return {por_id[sid]: {"rotulo": r["label"], "resumo": r["summary"],
                              "confianca": r["confidence"]}
                for (sid, uid), r in self.labels.items() if uid == unit_id}

    def source_file_id_por_sha(self, sha256):
        row = self.source_files.get(sha256)
        return row["id"] if row else None

    # --- claims ------------------------------------------------------------
    def tipos_de_claim(self):
        return {t: {"claim_type": t, "required_fields": campos,
                    "active": True}
                for t, campos in CLAIM_TYPES_ATIVOS.items()}

    def inserir_claim(self, unit_id, claim_type, entity, value,
                      source_sha256, page, evidence, confidence, materiality,
                      session_id):
        if source_sha256 not in self.source_files:
            raise AssertionError(f"FK: sha {source_sha256[:12]} sem source_file")
        row = {"id": len(self.claims) + 1, "unit_id": unit_id,
               "claim_type": claim_type, "entity": entity, "value": value,
               "source_sha256": source_sha256, "page": page,
               "evidence": evidence, "confidence": confidence,
               "materiality": materiality, "status": "ativo",
               "session_id": session_id}
        self.claims.append(row)
        return row["id"]

    def contagens_claims(self, unit_id):
        out: dict[str, int] = {}
        for c in self.claims:
            if c["unit_id"] == unit_id and c["status"] == "ativo":
                out[c["claim_type"]] = out.get(c["claim_type"], 0) + 1
        return out

    def claim_existe(self, unit_id, claim_id):
        return any(c["id"] == claim_id and c["unit_id"] == unit_id
                   for c in self.claims)

    # --- pesquisas ---------------------------------------------------------
    def inserir_pesquisa(self, unit_id, title, what, where, method,
                         session_id, claim_ids):
        row = {"id": len(self.research) + 1, "unit_id": unit_id,
               "title": title, "what": what, "where_": where,
               "method": method, "status": "aberta",
               "session_id": session_id}
        self.research.append(row)
        for cid in claim_ids:
            self.research_claims.append((row["id"], cid))
        return row["id"]

    def contagem_pesquisas(self, unit_id):
        return sum(1 for r in self.research
                   if r["unit_id"] == unit_id and r["status"] == "aberta")

    # --- sessões e custo ---------------------------------------------------
    def abrir_sessao(self, unit_id, command, model):
        row = {"id": len(self.sessions) + 1, "unit_id": unit_id,
               "command": command, "model": model, "stop_reason": "",
               "turns": 0, "usage": {}, "cost_usd": None, "log_path": ""}
        self.sessions.append(row)
        return row["id"]

    def fechar_sessao(self, session_id, stop_reason, turns, usage, cost_usd,
                      log_path):
        row = self.sessions[session_id - 1]
        row.update(stop_reason=stop_reason, turns=turns, usage=usage,
                   cost_usd=cost_usd, log_path=log_path)

    def registrar_custo(self, unit_id, category, amount_usd, detail):
        self.costs.append({"unit_id": unit_id, "category": category,
                           "amount_usd": float(amount_usd),
                           "detail": detail})

    def custo_acumulado(self, unit_id):
        return round(sum(c["amount_usd"] for c in self.costs
                         if c["unit_id"] == unit_id), 4)

    # --- planos ------------------------------------------------------------
    def propor_plano(self, unit_id, markdown, resumo, session_id):
        for p in self.plans:
            if p["unit_id"] == unit_id and p["status"] == "proposto":
                p["status"] = "substituido"
        versao = 1 + max((p["version"] for p in self.plans
                          if p["unit_id"] == unit_id), default=0)
        row = {"id": len(self.plans) + 1, "unit_id": unit_id,
               "version": versao, "markdown": markdown, "summary": resumo,
               "session_id": session_id, "status": "proposto",
               "decided_by": None, "decision_note": ""}
        self.plans.append(row)
        return {"id": row["id"], "version": versao}

    def plano(self, unit_id, versao=None):
        meus = [p for p in self.plans if p["unit_id"] == unit_id]
        if versao is not None:
            return next((p for p in meus if p["version"] == versao), None)
        return max(meus, key=lambda p: p["version"], default=None)

    def decidir_plano(self, plan_id, status, decided_by, note=""):
        row = self.plans[plan_id - 1]
        row.update(status=status, decided_by=decided_by,
                   decision_note=note)

    # --- VS2 ----------------------------------------------------------------
    def condicoes(self, unit_id):
        return [d for d in self.decisions
                if d["unit_id"] == unit_id
                and d["kind"] == "condicao_aprovacao"]

    def registrar_pergunta_vs2(self, unit_id, question, claim_id=None):
        row = {"id": len(self.decisions) + 1, "unit_id": unit_id,
               "kind": "pergunta_vs2", "question": question, "answer": "",
               "claim_id": claim_id}
        self.decisions.append(row)
        return row["id"]

    def perguntas_vs2_abertas(self, unit_id, assunto=""):
        return [d for d in self.decisions
                if d["unit_id"] == unit_id and d["kind"] == "pergunta_vs2"
                and not d["answer"]
                and assunto.lower() in d["question"].lower()]

    def registrar_xref_lookup(self, unit_id, source_sha256, key_kind,
                              key_value, rows_found):
        chave = (unit_id, source_sha256, key_kind, key_value)
        self.lookups[chave] = rows_found

    def registrar_xref_row(self, unit_id, source_sha256, sheet, row_number,
                           row, matched_keys):
        chave = (unit_id, source_sha256, sheet, row_number)
        self.xrows[chave] = {"unit_id": unit_id,
                             "source_sha256": source_sha256, "sheet": sheet,
                             "row_number": row_number, "row": row,
                             "matched_keys": matched_keys}

    def xref_lookups(self, unit_id):
        return [{"unit_id": k[0], "source_sha256": k[1], "key_kind": k[2],
                 "key_value": k[3], "rows_found": v}
                for k, v in self.lookups.items() if k[0] == unit_id]

    def xref_rows_da_unit(self, unit_id):
        return sorted((r for r in self.xrows.values()
                       if r["unit_id"] == unit_id),
                      key=lambda r: (r["source_sha256"], r["sheet"],
                                     r["row_number"]))

    def gravar_membro_populacao(self, unit_id, population, member,
                                origem="", note=""):
        self.members[(unit_id, population, member)] = {
            "unit_id": unit_id, "population": population, "member": member,
            "origem": origem, "note": note}

    def limpar_populacao(self, unit_id, population):
        for k in [k for k in self.members
                  if k[0] == unit_id and k[1] == population]:
            del self.members[k]

    def populacao(self, unit_id, population):
        return sorted((v for k, v in self.members.items()
                       if k[0] == unit_id and k[1] == population),
                      key=lambda v: v["member"])

    def populacoes_contagens(self, unit_id):
        out = {}
        for (uid, pop, _m) in self.members:
            if uid == unit_id:
                out[pop] = out.get(pop, 0) + 1
        return out

    def registrar_busca(self, unit_id, target, terms, scope, names_scanned,
                        hits, result="pendente_julgamento"):
        row = {"id": len(self.searches) + 1, "unit_id": unit_id,
               "target": target, "terms": terms, "scope": scope,
               "names_scanned": names_scanned, "hits": hits,
               "result": result, "evidence": "", "session_id": None}
        self.searches.append(row)
        return row["id"]

    def julgar_busca(self, search_id, result, evidence, session_id=None):
        row = self.searches[search_id - 1]
        row.update(result=result, evidence=evidence, session_id=session_id)

    def buscas(self, unit_id, target=None):
        return [b for b in self.searches
                if b["unit_id"] == unit_id
                and (target is None or b["target"] == target)]

    def criar_collection_item(self, unit_id, title, method, target,
                              research_item_id=None):
        for i in self.items:
            if i["unit_id"] == unit_id and i["title"] == title \
                    and i["status"] != "cancelado":
                return i["id"]
        row = {"id": len(self.items) + 1, "unit_id": unit_id,
               "title": title, "method": method, "target": target,
               "research_item_id": research_item_id, "status": "pendente",
               "staged_path": "", "promoted_path": "", "sha256": None,
               "provenance": {}, "cost_usd": 0, "note": ""}
        self.items.append(row)
        return row["id"]

    def atualizar_collection_item(self, item_id, **campos):
        permitidos = ("status", "staged_path", "promoted_path", "sha256",
                      "provenance", "cost_usd", "note")
        for chave in campos:
            if chave not in permitidos:
                raise ValueError(f"campo desconhecido: {chave}")
        self.items[item_id - 1].update(campos)

    def collection_items(self, unit_id, status=None):
        return [i for i in self.items
                if i["unit_id"] == unit_id
                and (status is None or i["status"] == status)]

    def custo_por_categoria(self, unit_id):
        out = {}
        for c in self.costs:
            if c["unit_id"] == unit_id:
                out[c["category"]] = round(
                    out.get(c["category"], 0) + c["amount_usd"], 4)
        return out

    def pesquisas(self, unit_id, status=None):
        return [r for r in self.research
                if r["unit_id"] == unit_id
                and (status is None or r["status"] == status)]

    def marcar_pesquisa(self, research_id, status):
        self.research[research_id - 1]["status"] = status

    def registrar_deliverable(self, unit_id, kind, version, path, sha256):
        self.delivs[(unit_id, kind, version)] = {
            "unit_id": unit_id, "kind": kind, "version": version,
            "path": path, "sha256": sha256}

    def deliverables(self, unit_id, kind):
        return sorted((v for k, v in self.delivs.items()
                       if k[0] == unit_id and k[1] == kind),
                      key=lambda v: v["version"])

    def claims_da_unit(self, unit_id, claim_type=None):
        return [c for c in self.claims
                if c["unit_id"] == unit_id and c["status"] == "ativo"
                and (claim_type is None or c["claim_type"] == claim_type)]

    # ----------------------------------------------------------------------
    def _unit(self, unit_id):
        return self.units[unit_id - 1]


def unit_de_teste(repo: RepoFake, pasta, nome: str = "UNIT SINTETICA"
                  ) -> dict[str, Any]:
    proj = repo.obter_ou_criar_projeto("TESTE", "Projeto Teste",
                                       str(pasta.parent))
    unit, _ = repo.obter_ou_criar_unit(proj["id"], nome, nome, str(pasta))
    repo.transicionar(unit["id"], "", "INDICADA", "indicar", "operador")
    return unit
