"""DAO do Case File contra o Postgres real — round-trips e FKs de evidência."""
from __future__ import annotations

import pytest

from src.casefile.db import migrar
from src.casefile.repo import Repo
from tests.helpers_casefile import conectar_pg_ou_skip

SHA_A = "a" * 64
SHA_B = "b" * 64


@pytest.fixture
def repo():
    conn, schema = conectar_pg_ou_skip()
    migrar(conn)
    yield Repo(conn)
    conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
    conn.close()


def _unit(repo):
    proj = repo.obter_ou_criar_projeto("BKV999TX", "Teste", r"C:\tmp\proj")
    unit, criada = repo.obter_ou_criar_unit(proj["id"], "Josh B Unit",
                                            "JOSH B UNIT", r"C:\tmp\u")
    if criada:
        repo.transicionar(unit["id"], "", "INDICADA", "indicar", "operador")
    return unit


@pytest.mark.postgres
def test_projeto_unit_e_transicoes(repo):
    unit = _unit(repo)
    assert repo.estado_da_unit(unit["id"]) == "INDICADA"
    # get-or-create é idempotente, case-insensitive
    de_novo, criada = repo.obter_ou_criar_unit(
        unit["project_id"], "josh b", "josh b unit", r"C:\tmp\u")
    assert not criada and de_novo["id"] == unit["id"]
    assert repo.obter_unit_por_nome("josh b unit")["id"] == unit["id"]
    repo.transicionar(unit["id"], "INDICADA", "PLANEJANDO", "planejar",
                      "operador", "vamos")
    # corrida perdida: o estado exigido já não é o atual
    with pytest.raises(AssertionError, match="corrida"):
        repo.transicionar(unit["id"], "INDICADA", "PLANEJANDO", "planejar",
                          "operador")
    assert [t["event"] for t in repo.transicoes(unit["id"])] == \
        ["indicar", "planejar"]


@pytest.mark.postgres
def test_fontes_sightings_e_upsert(repo):
    unit = _unit(repo)
    sid = repo.registrar_source_file(SHA_A, 10)
    assert repo.registrar_source_file(SHA_A, 10) == sid     # upsert
    repo.registrar_sighting(sid, unit["id"], r"C:\u\FILES\a.zip", "x/a.pdf",
                            "files/x/a.pdf", "unit_files")
    repo.registrar_sighting(sid, unit["id"], r"C:\u\FILES\a.zip", "x/a.pdf",
                            "files/x/a.pdf", "unit_files")  # mesmo caminho
    repo.registrar_sighting(sid, None, r"C:\p\xref.xlsx", "",
                            "referencias/xref.xlsx", "project_reference")
    shas = repo.sha_por_nome(unit["id"])
    assert shas == {"files/x/a.pdf": [SHA_A],
                    "referencias/xref.xlsx": [SHA_A]}
    censo = repo.contagem_censo(unit["id"])
    assert censo["unit_files"] == {"sightings": 1, "conteudos": 1}
    assert repo.sha_existe(SHA_A) and not repo.sha_existe(SHA_B)


@pytest.mark.postgres
def test_claim_exige_evidencia_no_censo(repo):
    unit = _unit(repo)
    sess = repo.abrir_sessao(unit["id"], "planejar.examinador", "modelo-x")
    repo.registrar_source_file(SHA_A, 10)
    cid = repo.inserir_claim(unit["id"], "lease_in_unit", "lease 0001",
                             {"lease_no": "0001", "lessor": "F"}, SHA_A,
                             "1", "trecho literal", "alta", "alta", sess)
    assert repo.claim_existe(unit["id"], cid)
    assert repo.contagens_claims(unit["id"]) == {"lease_in_unit": 1}
    # FK: evidência que não está em source_files é recusada pelo banco
    with pytest.raises(Exception):
        repo.inserir_claim(unit["id"], "lease_in_unit", "lease 0002",
                           {"lease_no": "0002", "lessor": "G"}, SHA_B,
                           "1", "trecho", "alta", "media", sess)
    rid = repo.inserir_pesquisa(unit["id"], "buscar", "doc", "cartorio",
                                "CourthouseDirect", sess, [cid])
    assert rid and repo.contagem_pesquisas(unit["id"]) == 1


@pytest.mark.postgres
def test_planos_versionam_e_substituem(repo):
    unit = _unit(repo)
    sess = repo.abrir_sessao(unit["id"], "planejar.examinador", "modelo-x")
    v1 = repo.propor_plano(unit["id"], "# v1", {"leases": 1}, sess)
    v2 = repo.propor_plano(unit["id"], "# v2", {"leases": 2}, sess)
    assert (v1["version"], v2["version"]) == (1, 2)
    assert repo.plano(unit["id"])["version"] == 2
    assert repo.plano(unit["id"], 1)["status"] == "substituido"
    repo.decidir_plano(v2["id"], "aprovado", "operador", "ok")
    assert repo.plano(unit["id"])["status"] == "aprovado"


@pytest.mark.postgres
def test_sessao_custo_e_rotulos(repo):
    unit = _unit(repo)
    sess = repo.abrir_sessao(unit["id"], "planejar.triagem", "haiku")
    repo.fechar_sessao(sess, "parou", 3, {"custo_usd": 0.5}, 0.5, "x.json")
    repo.registrar_custo(unit["id"], "modelo", 0.5, {"session_id": sess})
    repo.registrar_custo(unit["id"], "modelo", 0.25, {})
    assert repo.custo_acumulado(unit["id"]) == 0.75
    sid = repo.registrar_source_file(SHA_A, 10)
    repo.gravar_rotulo(sid, unit["id"], "lease-ogl", "resumo", "alta", sess)
    repo.gravar_rotulo(sid, unit["id"], "dpu", "novo resumo", "media", sess)
    assert repo.rotulos(unit["id"]) == {
        SHA_A: {"rotulo": "dpu", "resumo": "novo resumo",
                "confianca": "media"}}
    assert repo.source_file_id_por_sha(SHA_A) == sid
