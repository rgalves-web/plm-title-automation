"""VS1 fim-a-fim roteirizado: indicar -> planejar -> plano -> aprovar.

Cliente roteirizado injetado nas duas sessões (triagem + Examinador); o lote
de claims traz um item inválido que volta como erro nomeado e é corrigido no
turno seguinte. Nenhuma asserção conclui title — só encanamento: linhas no
repo, transições, arquivo do plano, custo e logs.
"""
from __future__ import annotations

import json

import pytest

from src.casefile import cli
from tests.helpers_casefile import (ClientRoteirizado, RepoFake, Texto, Use)

XREF_NOME = "Lease to Well and Contract XREF 06-16-2026.xlsx"
XREF_LOGICO = f"referencias/{XREF_NOME.lower()}"


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    root = tmp_path / "BKV999TX - Projeto Teste"
    unit_dir = root / "SINTETICA A UNIT"
    (unit_dir / "FILES").mkdir(parents=True)
    (unit_dir / "FILES" / "dpu.txt").write_text(
        "DPU. Exhibit A: lease 0001 - Fulano de Tal", encoding="utf-8")
    (unit_dir / "FILES" / "l1.txt").write_text(
        "OGL lease 0001, Fulano de Tal, Lessor", encoding="utf-8")
    (root / XREF_NOME).write_bytes(b"xref-master-bytes")
    monkeypatch.setenv("CASEFILE_PROJECT_ROOT", str(root))
    monkeypatch.setattr(cli, "ULTIMA", tmp_path / "ultima")
    return root, unit_dir


def _roteiro():
    rotulos = [
        {"documento": "files/dpu.txt", "rotulo": "dpu",
         "resumo": "unit designation", "confianca": "alta"},
        {"documento": "files/l1.txt", "rotulo": "lease-ogl",
         "resumo": "lease 0001", "confianca": "alta"},
        {"documento": XREF_LOGICO, "rotulo": "planilha-projeto",
         "resumo": "xref do projeto", "confianca": "alta"},
    ]
    claim_ok = {"tipo": "lease_in_unit", "entidade": "lease 0001",
                "valor": {"lease_no": "0001", "lessor": "Fulano de Tal"},
                "documento": "files/dpu.txt", "pagina": "1",
                "trecho": "Exhibit A: lease 0001 - Fulano de Tal",
                "confianca": "alta", "materialidade": "alta"}
    claim_ruim = dict(claim_ok, tipo="chute")
    claim_corrigido = {"tipo": "divergence", "entidade": "xref x dpu",
                       "valor": {"fontes": ["dpu", "xref"]},
                       "documento": "files/dpu.txt", "pagina": "1",
                       "trecho": "Exhibit A: lease 0001",
                       "confianca": "media"}
    pesquisa = {"titulo": "Buscar lease 0001 no cartorio",
                "o_que": "OGL Book 531 Page 840", "metodo": "CourthouseDirect",
                "onde": "cartorio de Montague — CourthouseDirect",
                "claims_relacionados": [1]}
    return [
        # sessão 1: triagem
        [Use("rotular_documentos", {"rotulos": rotulos}, id="t1")],
        [Texto("triagem concluida")],
        # sessão 2: Examinador — lote com 1 inválido, depois correção
        [Use("registrar_claims", {"claims": [claim_ok, claim_ruim]},
             id="e1")],
        [Use("registrar_claims", {"claims": [claim_corrigido]}, id="e2"),
         Use("registrar_pesquisas", {"itens": [pesquisa]}, id="e3")],
        [Use("propor_plano", {
            "plano_markdown": "# Unit Investigation Plan — Sintetica A\n"
                              "1 lease, 1 divergencia, 1 pesquisa.",
            "resumo": {"leases": 1, "divergencias": 1, "pesquisas": 1}},
            id="e4")],
        [Texto("plano proposto")],
    ]


def test_vs1_fim_a_fim(ambiente, capsys):
    root, unit_dir = ambiente
    repo = RepoFake()
    cli.cmd_indicar("Sintetica A Unit", repo=repo)
    unit = repo.obter_unit_por_nome("SINTETICA A UNIT")
    assert repo.estado_da_unit(unit["id"]) == "INDICADA"

    antes = {p for p in unit_dir.rglob("*") if p.is_file()}
    cli.cmd_planejar("Sintetica A Unit", repo=repo,
                     client=ClientRoteirizado(_roteiro()))

    # estados: INDICADA -> PLANEJANDO -> AGUARDANDO_RENATO
    assert repo.estado_da_unit(unit["id"]) == "AGUARDANDO_RENATO"
    eventos = [t["event"] for t in repo.transicoes(unit["id"])]
    assert eventos == ["indicar", "planejar", "plano_proposto"]

    # claims: o inválido foi rejeitado, os 2 válidos entraram
    assert repo.contagens_claims(unit["id"]) == {"lease_in_unit": 1,
                                                 "divergence": 1}
    assert repo.contagem_pesquisas(unit["id"]) == 1
    assert repo.research_claims == [(1, 1)]

    # plano v1 gravado e renderizado em _casefile/
    pl = repo.plano(unit["id"])
    assert pl["version"] == 1 and pl["status"] == "proposto"
    plano_md = unit_dir / "_casefile" / "PLANO_INVESTIGACAO_v1.md"
    assert plano_md.exists()
    assert "Unit Investigation Plan" in plano_md.read_text(encoding="utf-8")

    # sessões fechadas com log salvo; custo lançado antes do fecho
    assert [s["command"] for s in repo.sessions] == \
        ["planejar.triagem", "planejar.examinador"]
    for s in repo.sessions:
        assert s["stop_reason"]
        log = json.loads((unit_dir / "_casefile" /
                          f"log_{s['command']}.json")
                         .read_text(encoding="utf-8"))
        assert log["turnos"] >= 1
    assert len(repo.costs) == 2
    assert repo.custo_acumulado(unit["id"]) > 0

    # a caneta: nada novo fora de _casefile/
    depois = {p for p in unit_dir.rglob("*") if p.is_file()}
    novos = depois - antes
    assert novos and all("_casefile" in p.parts for p in novos)

    # o erro nomeado voltou ao modelo no lote 1
    saida = capsys.readouterr().out
    assert "plano v1 proposto" in saida

    # aprovação do operador fecha o slice
    cli.cmd_aprovar("Sintetica A Unit", nota="ok", repo=repo)
    assert repo.estado_da_unit(unit["id"]) == "COLETANDO"
    assert repo.plano(unit["id"])["status"] == "aprovado"


def test_planejar_sem_propor_plano_avisa_e_permite_retomada(ambiente,
                                                            capsys):
    root, unit_dir = ambiente
    repo = RepoFake()
    cli.cmd_indicar("Sintetica A Unit", repo=repo)
    roteiro = [
        [Texto("triagem: nada a rotular")],       # triagem para sem rotular
        [Texto("sessao morreu sem plano")],       # examinador sem propor
    ]
    # triagem tem pendentes, então o 1º turno sem tool encerra a sessão dela
    cli.cmd_planejar("Sintetica A Unit", repo=repo,
                     client=ClientRoteirizado(roteiro))
    unit = repo.obter_unit_por_nome("SINTETICA A UNIT")
    assert repo.estado_da_unit(unit["id"]) == "PLANEJANDO"
    assert "SEM propor plano" in capsys.readouterr().out
    assert repo.plano(unit["id"]) is None
