"""CLI do casefile — recusas nomeadas e leitura sem modelo."""
from __future__ import annotations

import pytest

from src.casefile import cli
from tests.helpers_casefile import RepoFake, unit_de_teste


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    root = tmp_path / "BKV999TX - Projeto Teste"
    (root / "JOSH B UNIT").mkdir(parents=True)
    (root / "WEBB B UNIT").mkdir()
    monkeypatch.setenv("CASEFILE_PROJECT_ROOT", str(root))
    monkeypatch.setattr(cli, "ULTIMA", tmp_path / "ultima")
    return root


def test_indicar_inexistente_lista_candidatas(ambiente):
    with pytest.raises(SystemExit, match="Candidatas") as exc:
        cli.cmd_indicar("Unidade Fantasma", repo=RepoFake())
    assert "JOSH B UNIT" in str(exc.value)


def test_indicar_e_idempotente(ambiente, capsys):
    repo = RepoFake()
    cli.cmd_indicar("Josh B Unit", repo=repo)
    cli.cmd_indicar("josh b unit", repo=repo)
    assert len(repo.units) == 1
    assert "ja indicada" in capsys.readouterr().out
    # transicao inicial registrada uma vez só
    assert [t["event"] for t in repo.transicoes(1)] == ["indicar"]


def test_aprovar_sem_plano_proposto_recusa(ambiente):
    repo = RepoFake()
    unit = unit_de_teste(repo, ambiente / "JOSH B UNIT", "JOSH B UNIT")
    with pytest.raises(SystemExit, match="nao tem plano PROPOSTO"):
        cli.cmd_aprovar("Josh B Unit", repo=repo)
    assert repo.estado_da_unit(unit["id"]) == "INDICADA"


def test_rejeitar_exige_motivo(ambiente):
    repo = RepoFake()
    unit_de_teste(repo, ambiente / "JOSH B UNIT", "JOSH B UNIT")
    with pytest.raises(SystemExit, match="motivo"):
        cli.cmd_rejeitar("Josh B Unit", "", repo=repo)


def test_plano_imprime_sem_modelo(ambiente, capsys):
    repo = RepoFake()
    unit = unit_de_teste(repo, ambiente / "JOSH B UNIT", "JOSH B UNIT")
    sid = repo.abrir_sessao(unit["id"], "planejar.examinador", "x")
    repo.propor_plano(unit["id"], "# Plano de teste", {"leases": 2}, sid)
    cli.cmd_plano("Josh B Unit", repo=repo)
    saida = capsys.readouterr().out
    assert "# Plano de teste" in saida
    assert "leases: 2 x 0  <- DIVERGE" in saida     # declarado x banco


def test_planejar_com_plano_pendente_aponta_o_gate(ambiente):
    repo = RepoFake()
    unit = unit_de_teste(repo, ambiente / "JOSH B UNIT", "JOSH B UNIT")
    repo.transicionar(unit["id"], "INDICADA", "PLANEJANDO", "planejar", "op")
    repo.transicionar(unit["id"], "PLANEJANDO", "AGUARDANDO_RENATO",
                      "plano_proposto", "modelo:x")
    with pytest.raises(SystemExit, match="aprovar"):
        cli.cmd_planejar("Josh B Unit", repo=repo)


def test_unit_desconhecida_aponta_o_indicar(ambiente):
    with pytest.raises(SystemExit, match="indicar"):
        cli.cmd_estado("Josh B Unit", repo=RepoFake())
