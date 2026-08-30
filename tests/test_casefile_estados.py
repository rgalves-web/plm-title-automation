"""Máquina de estados do Case File — encanamento de processo, sem julgamento."""
from __future__ import annotations

import pytest

from src.casefile import estados
from tests.helpers_casefile import RepoFake, unit_de_teste


def _unit(tmp_path):
    repo = RepoFake()
    (tmp_path / "U").mkdir()
    return repo, unit_de_teste(repo, tmp_path / "U", "U UNIT")


def test_cadeia_feliz_do_vs1(tmp_path):
    repo, unit = _unit(tmp_path)
    assert estados.transicionar(repo, unit, "planejar", "operador") == \
        "PLANEJANDO"
    assert estados.transicionar(repo, unit, "plano_proposto",
                                "modelo:x") == "AGUARDANDO_RENATO"
    assert estados.transicionar(repo, unit, "aprovar_plano", "operador") == \
        "COLETANDO"
    eventos = [t["event"] for t in repo.transicoes(unit["id"])]
    assert eventos == ["indicar", "planejar", "plano_proposto",
                       "aprovar_plano"]


def test_rejeitar_regride_com_registro(tmp_path):
    repo, unit = _unit(tmp_path)
    estados.transicionar(repo, unit, "planejar", "operador")
    estados.transicionar(repo, unit, "plano_proposto", "modelo:x")
    got = estados.transicionar(repo, unit, "rejeitar_plano", "operador",
                               nota="faltou a DPU")
    assert got == "PLANEJANDO"
    ultima = repo.transicoes(unit["id"])[-1]
    assert ultima["note"] == "faltou a DPU"
    assert ultima["from_state"] == "AGUARDANDO_RENATO"


def test_evento_fora_de_ordem_e_erro_nomeado(tmp_path):
    repo, unit = _unit(tmp_path)
    with pytest.raises(estados.TransicaoInvalida, match="exige estado"):
        estados.transicionar(repo, unit, "aprovar_plano", "operador")
    with pytest.raises(estados.TransicaoInvalida, match="desconhecido"):
        estados.transicionar(repo, unit, "voar", "operador")
    assert repo.estado_da_unit(unit["id"]) == "INDICADA"


def test_bloquear_de_qualquer_estado_e_desbloquear_volta(tmp_path):
    repo, unit = _unit(tmp_path)
    estados.transicionar(repo, unit, "planejar", "operador")
    assert estados.transicionar(repo, unit, "bloquear", "sistema",
                                nota="teto") == "BLOQUEADA"
    assert estados.transicionar(repo, unit, "desbloquear", "operador") == \
        "PLANEJANDO"
    with pytest.raises(estados.TransicaoInvalida, match="BLOQUEADA"):
        estados.transicionar(repo, unit, "desbloquear", "operador")


def test_matriz_cobre_o_fluxo_cto_completo(tmp_path):
    repo, unit = _unit(tmp_path)
    for evento in ("planejar", "plano_proposto", "aprovar_plano",
                   "coleta_concluida", "exame_concluido",
                   "verificacao_concluida", "preenchimento_concluido",
                   "auditoria_concluida", "liberar"):
        estados.transicionar(repo, unit, evento, "sistema")
    assert repo.estado_da_unit(unit["id"]) == "LIBERADA"
