"""Teto duro por unit — recusa limpa antes de gastar."""
from __future__ import annotations

import pytest

from src.casefile import custo
from tests.helpers_casefile import RepoFake, unit_de_teste


def test_orcamento_e_o_minimo_e_desconta_o_gasto(tmp_path, monkeypatch):
    monkeypatch.setenv("CASEFILE_TETO_UNIT_USD", "25")
    repo = RepoFake()
    (tmp_path / "U").mkdir()
    unit = unit_de_teste(repo, tmp_path / "U", "U UNIT")
    assert custo.orcamento(repo, unit, 40.0) == 25.0
    repo.registrar_custo(unit["id"], "modelo", 20.0, {})
    assert custo.orcamento(repo, unit, 40.0) == 5.0
    assert custo.orcamento(repo, unit, 3.0) == 3.0


def test_teto_batido_recusa_antes_de_gastar(tmp_path, monkeypatch):
    monkeypatch.setenv("CASEFILE_TETO_UNIT_USD", "10")
    repo = RepoFake()
    (tmp_path / "U").mkdir()
    unit = unit_de_teste(repo, tmp_path / "U", "U UNIT")
    repo.registrar_custo(unit["id"], "modelo", 10.0, {})
    with pytest.raises(SystemExit, match="TETO DA UNIDADE ATINGIDO"):
        custo.orcamento(repo, unit, 40.0)
    # nada foi gasto na recusa
    assert repo.custo_acumulado(unit["id"]) == 10.0
