"""VS-D0 — testes de CONTRATO banco→API: valores da interface = valores do
Case File, sem inferência de logs. RepoFake injetado por dependency override."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.casefile import api
from tests.helpers_casefile import RepoFake, unit_de_teste

SHA = "b" * 64


@pytest.fixture
def cenario(tmp_path, monkeypatch):
    monkeypatch.delenv("CASEFILE_SIMULATION_MODE", raising=False)
    monkeypatch.setenv("CASEFILE_TETO_UNIT_USD", "25")
    repo = RepoFake()
    pasta = tmp_path / "JOSH T UNIT"
    (pasta / "FILES").mkdir(parents=True)
    unit = unit_de_teste(repo, pasta, "JOSH T UNIT")
    uid = unit["id"]
    repo.registrar_politica(uid, "simulation_mode", "true")
    repo.transicionar(uid, "INDICADA", "EXAMINANDO", "atalho", "teste")
    repo.registrar_source_file(SHA, 10)
    repo.registrar_sighting(1, uid, "c", "", "files/doc.pdf", "unit_files")
    sess = repo.abrir_sessao(uid, "exame.vs3", "claude-opus-5")
    repo.fechar_sessao(sess, "fim", 3, {}, 1.5, "x")
    cid = repo.inserir_claim(uid, "fact", "data de corte do exame",
                             {"data": "2026-06-16",
                              "benchmark_contamination": True,
                              "origem_evidencia": "entrega"},
                             SHA, "1", "trecho", "alta", "alta", sess)
    repo.registrar_verificacao(cid, "qual a data?", "concordancia",
                               "gpt-x", {"valor": "2026-06-16"}, {}, 0.02,
                               None)
    repo.atualizar_claim_ddr(uid, cid, ["Summary!B2"], "simulacao")
    for lease in ("0111111/001", "0111111/002"):
        repo.inserir_claim(uid, "lease_in_unit", f"lease {lease}",
                           {"lease_no": lease, "lessor": "F"}, SHA, "3",
                           "t", "alta", "alta", sess)
    from src.casefile import populacoes
    populacoes.recalcular(repo, unit)
    repo.registrar_custo(uid, "modelo", 17.14, {})
    repo.registrar_pergunta_vs2(uid, "[serie] confirmar?")
    repo.criar_collection_item(uid, "441.275.pdf", "courthousedirect",
                               {"book": "441", "page": "275",
                                "motivo": "Prior Lease"})
    repo.atualizar_collection_item(1, status="bloqueado_simulacao",
                                   note="required_in_production")
    repo.gravar_posicao(uid, "tract 1", "comprovada", [cid], "", sess)

    app_client = TestClient(api.app)
    api.app.dependency_overrides[api.get_repo] = lambda: repo
    yield app_client, repo, unit
    api.app.dependency_overrides.clear()


def test_portfolio_reflete_o_banco(cenario):
    client, repo, unit = cenario
    got = client.get("/api/units").json()
    assert len(got) == 1
    u = got[0]
    assert u["unit"] == "JOSH T UNIT"
    assert u["estado"] == "EXAMINANDO"
    assert u["modo"] == "SIMULATION"          # política no banco, sem env
    assert u["custo_portal"] == 0.0
    assert u["custo_ia"] == 17.14
    assert u["orcamento"] == 25.0
    assert u["decisoes_aguardando"] == 1
    assert u["blockers"] >= 1                 # bloqueado_simulacao + gates
    assert u["progresso"]["leases"]["exhibit_a"] == 2


def test_detalhe_gates_populacoes_custos(cenario):
    client, repo, unit = cenario
    got = client.get(f"/api/units/{unit['id']}").json()
    assert got["modo"] == "SIMULATION"
    assert got["custos"]["total"] == 17.14
    assert got["populacoes"]["dpu_exhibit_a"] == 2
    assert len(got["gates"]) == 6
    assert got["posicoes"][0]["classification"] == "comprovada"


def test_claim_com_verificacao_e_contaminacao(cenario):
    client, repo, unit = cenario
    claims = client.get(f"/api/units/{unit['id']}/claims").json()
    alvo = next(c for c in claims if c["tipo"] == "fact")
    assert alvo["benchmark_contamination"] is True
    assert alvo["verificacao"] == ["concordancia"]
    det = client.get(f"/api/claims/{alvo['id']}").json()
    assert det["documento"]["sha256"] == SHA
    assert det["celulas_candidatas_ddr"] == ["Summary!B2"]
    assert det["verificacoes"][0]["verdict"] == "concordancia"
    assert det["examinador"]["comando_versao_prompt"] == "exame.vs3"
    assert det["origem"] == "entrega"


def test_fila_timeline_documentos(cenario):
    client, repo, unit = cenario
    fila = client.get(f"/api/units/{unit['id']}/intervencoes").json()
    tipos = {f["criticidade"] for f in fila}
    assert "alta" in tipos and len(fila) == 2   # pergunta + bloqueado
    tl = client.get(f"/api/units/{unit['id']}/timeline").json()
    acoes = [e["acao"] for e in tl]
    assert "atalho" in acoes and "sessao exame.vs3" in acoes
    docs = client.get(f"/api/units/{unit['id']}/documentos").json()
    assert docs["censo_por_origem"]["unit_files"]["conteudos"] == 1
    assert docs["itens_coleta"][0]["status"] == "bloqueado_simulacao"


def test_unit_inexistente_404_e_home_serve_html(cenario):
    client, repo, unit = cenario
    assert client.get("/api/units/999").status_code == 404
    home = client.get("/")
    assert home.status_code == 200
    assert "Control Tower" in home.text