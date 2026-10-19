"""Migrações do Case File — schema temporário no Postgres real, ou skip."""
from __future__ import annotations

import pytest

from src.casefile.db import (MigracaoAlterada, _statements,
                             estado_migracoes, migrar)
from tests.helpers_casefile import conectar_pg_ou_skip


@pytest.fixture
def pg():
    conn, schema = conectar_pg_ou_skip()
    yield conn
    conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
    conn.close()


def test_divisor_de_statements_respeita_strings_e_comentarios():
    sql = ("-- comentario; com ponto e virgula\n"
           "CREATE TABLE a (x text DEFAULT 'a;b');\n"
           "INSERT INTO a VALUES ('it''s;fine');")
    got = _statements(sql)
    assert len(got) == 2
    assert "a;b" in got[0] and "it''s;fine" in got[1]


@pytest.mark.postgres
def test_migrar_aplica_reaplicar_e_noop_e_seeds_presentes(pg):
    novas = migrar(pg)
    assert novas == ["0001_fundacao", "0002_seed_claim_types",
                     "0003_vs2_coleta", "0004_semantica_vs2",
                     "0005_simulacao", "0006_vs3_exame",
                     "0007_auditoria_verificacao", "0008_training_suite",
                     "0009_orquestracao", "0010_operacao_visual", "0011_limite_compartilhado", "0012_registro_conhecimento", "0013_terminal_execucao",
                     "0014_function_output_files", "0015_function_input_files",
                     "0016_case_records", "0017_round_turn_cap",
                     "0018_round_focus", "0019_attempts_count_launched_calls",
                     "0020_autonomous_operation", "0021_autonomy_hardening",
                     "0022_lot_case_superseded"]
    assert migrar(pg) == []                      # reaplicar é no-op
    assert [m["version"] for m in estado_migracoes(pg)] == list(range(1,23))
    # 11 do VS1 + `fact` ativado pela 0003 (leituras dirigidas do VS2)
    ativos = pg.execute(
        "SELECT count(*) AS n FROM claim_types WHERE active").fetchone()["n"]
    assert ativos == 12
    total = pg.execute(
        "SELECT count(*) AS n FROM claim_types").fetchone()["n"]
    assert total == 17
    for tabela in ("xref_lookups", "xref_rows", "population_members",
                   "negative_searches", "collection_items"):
        assert pg.execute(f"SELECT count(*) AS n FROM {tabela}"
                          ).fetchone()["n"] == 0


@pytest.mark.postgres
def test_checksum_divergente_falha_nomeado(pg):
    migrar(pg)
    pg.execute("UPDATE schema_migrations SET checksum = 'x' "
               "WHERE version = 1")
    with pytest.raises(MigracaoAlterada, match="0001_fundacao"):
        migrar(pg)


@pytest.mark.postgres
def test_views_de_projecao_existem(pg):
    migrar(pg)
    for view in ("vw_unit_leases", "vw_unit_tracts", "vw_unit_tos",
                 "vw_unit_sellers", "vw_unit_cost"):
        assert pg.execute(f"SELECT * FROM {view}").fetchall() == []
