"""Replay isolado da etapa D: snapshot de leitura → schema temporário →
Coordenador roteirizado → proposta, cobertura, recusa e aprovação simuladas.
Aqui a "produção" é um schema sintético do Postgres de teste."""
import os

import pytest

from src.casefile import replay_coordenador as rp
from tests.helpers_casefile import conectar_pg_ou_skip, unit_de_teste

pytestmark = pytest.mark.postgres


@pytest.fixture
def origem(tmp_path):
    from src.casefile.db import migrar
    from src.casefile.repo import Repo
    conn, schema = conectar_pg_ou_skip()
    migrar(conn)
    repo = Repo(conn)
    unit = unit_de_teste(repo, tmp_path / "ORIGEM A UNIT", "ORIGEM A UNIT")
    s1 = repo.abrir_sessao(unit["id"], "planejar", "m")
    ids = [repo.inserir_pesquisa(unit["id"], f"pesquisa {n}", f"o que {n}",
                                 "cartorio", "vol/pg", s1, [])
           for n in range(1, 6)]
    repo.marcar_pesquisa(ids[1], "cancelada")
    plano = repo.propor_plano(unit["id"], "# plano v1", {"n": 5}, s1)
    repo.decidir_plano(plano["id"], "aprovado", "human:renato", "ok")
    sha = "ab" * 32
    fid = repo.registrar_source_file(sha, 1)
    repo.registrar_sighting(fid, unit["id"], "x/dpu.pdf", "", "dpu.pdf",
                            "unit_files")
    c1 = repo.inserir_claim(unit["id"], "tract", "Tract 1", {"tract_no": "1"},
                            sha, "6", "TRACT 1", "alta", "alta", s1)
    c2 = repo.inserir_claim(unit["id"], "tract", "Tract 1", {"tract_no": "1"},
                            sha, "6", "TRACT 1", "alta", "alta", s1)
    repo.atualizar_claim_status(unit["id"], c1, "substituido", c2)
    repo.registrar_pergunta_vs2(unit["id"], "Série X conta acres?", c2)
    repo.registrar_custo(unit["id"], "vs1", 19.5, {"s": 1})
    yield conn, unit, ids, schema
    conn.execute("SET default_transaction_read_only = off")
    conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
    conn.close()


def _destino():
    """Mesmo banco de teste, outra conexão: só o núcleo `_replay` aceita
    (a entrada pública recusa — ver os testes da guarda abaixo)."""
    return rp._conectar(os.environ["CASEFILE_TEST_DSN"],
                        somente_leitura=False)


def _schemas_replay(conn):
    return {r["nspname"] for r in conn.execute(
        "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'replay_d_%'"
    ).fetchall()}


def _contar(conn, tabela):
    return conn.execute(f"SELECT count(*) AS n FROM {tabela}").fetchone()["n"]


def test_replay_demonstra_entrada_alvos_proposta_e_decisoes(origem, tmp_path):
    conn, unit, ids, _ = origem
    antes = {t: _contar(conn, t) for t in ("research_items", "claims",
                                           "tasks", "plan_proposals",
                                           "cost_entries")}
    rel = rp._replay(conn, _destino(), unit["canonical_name"],
                     tmp_path / "saida", teto=25.0, orcamento=1.5,
                     pacote=rp.PACOTE_PADRAO)
    abertas = [f"pesquisa:{i}" for i in ids if i != ids[1]]
    assert rel["alvos"]["alvos"] == abertas
    assert rel["alvos"]["canceladas"] == [f"pesquisa:{ids[1]}"]
    assert rel["snapshot"]["claims"] == 2 and rel["snapshot"]["units"] == 1
    assert rel["gasto_da_unit_no_snapshot"] == 19.5
    e = rel["entrada"]
    assert e["pendencias_abertas"] == abertas
    assert e["ferramentas_expostas"] == ["entregar_saida", "ler_case_file"]
    assert "manifesto" in e and e["orcamento_usd"]["gasto"] == 19.5
    r1 = rel["rodada_1"]
    assert r1["consulta_ler_case_file"] == 5
    assert "cobertura_incompleta: 1 de 4" in r1["erro_da_entrega_parcial"][
        "erros"][0]
    assert r1["status_do_coordenador"] == "aguardando_operador"
    assert r1["tarefas_criadas_antes_da_decisao"] == []
    assert rel["proposta_1"]["cobertura"]["completa"]
    rec = rel["recusa_simulada"]
    assert rec["status"] == "recusada" and rec["plano_preservado"] == 4
    assert rec["decidido_por"] == rp.ATOR_SIMULADO and rec["decidido_em"]
    assert rec["tarefas_criadas"] == [] and rec["status_coordenador"] == \
        "recusada"
    ap = rel["aprovacao_simulada"]
    assert ap["status"] == "aprovada" and ap["cobertura"]["completa"]
    assert set(ap["tarefas_criadas"].values()) == {"pronta"}
    assert len(ap["tarefas_criadas"]) == 4
    assert ap["status_coordenador"] == "aceita"
    assert [p["status"] for p in rel["historico_de_propostas"]] == \
        ["recusada", "aprovada"]
    assert rel["chamadas_de_api"] == 0 and rel["custo_total_do_replay_usd"] \
        == 0.0
    # origem intocada e schema temporário removido
    assert {t: _contar(conn, t) for t in antes} == antes
    assert conn.execute(
        "SELECT count(*) AS n FROM pg_namespace WHERE nspname = %s",
        (rel["schema_temporario"],)).fetchone()["n"] == 0
    md = (tmp_path / "saida" / "replay_etapa_d.md").read_text("utf-8")
    assert "O que só um modelo real pode demonstrar" in md
    assert "4 pesquisas abertas" in md
    assert (tmp_path / "saida" / "replay_etapa_d.json").exists()


def test_origem_fica_somente_leitura(origem, tmp_path):
    conn, unit, _, _ = origem
    rp._replay(conn, _destino(), unit["canonical_name"], tmp_path / "s",
               teto=25.0, orcamento=1.5, pacote=rp.PACOTE_PADRAO)
    import psycopg
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        conn.execute("INSERT INTO cost_entries (unit_id, category, "
                     "amount_usd) VALUES (%s, 'x', 1)", (unit["id"],))


def test_saida_dentro_do_repo_e_recusada(origem):
    conn, unit, _, _ = origem
    with pytest.raises(SystemExit, match="invariante 8"):
        rp.executar_replay(conn, os.environ["CASEFILE_TEST_DSN"],
                           unit["canonical_name"], rp.REPO_ROOT / "saida",
                           teto=25.0)


def test_proposta_roteirizada_e_marcada_como_roteiro():
    class R:
        def pesquisas(self, uid):
            return [{"id": 1, "title": "t1"}, {"id": 2, "title": "t2"}]
    p = rp.proposta_roteirizada(R(), 1, ["pesquisa:1", "pesquisa:2"],
                                saldo=1.0, omitir_ultimo=True)
    [t] = p["tarefas"]
    assert t["pendencias"] == ["pesquisa:1"]
    assert t["title"].startswith("[ROTEIRO DO REPLAY]")
    assert "não é saída de modelo" in t["justificativa"]


# --- guarda: destino no mesmo banco da origem é recusado ----------------------

def test_destino_no_mesmo_banco_da_origem_e_recusado(origem, tmp_path):
    conn, unit, _, _ = origem
    antes = _schemas_replay(conn)
    with pytest.raises(rp.DestinoIgualOrigem, match="destino_igual_a_origem"):
        rp.executar_replay(conn, os.environ["CASEFILE_TEST_DSN"],
                           unit["canonical_name"], tmp_path / "s", teto=25.0)
    assert _schemas_replay(conn) == antes          # nenhum schema criado
    assert not (tmp_path / "s").exists()           # nenhum relatório


def test_mesmo_banco_com_host_escrito_diferente_e_recusado(origem, tmp_path):
    """localhost × 127.0.0.1: a identidade é do servidor, não do texto."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    conn, unit, _, _ = origem
    d = conninfo_to_dict(os.environ["CASEFILE_TEST_DSN"])
    outro = "127.0.0.1" if d.get("host") in ("localhost", None, "")         else "localhost"
    dsn = make_conninfo(**{**d, "host": outro})
    with pytest.raises(rp.DestinoIgualOrigem):
        rp.executar_replay(conn, dsn, unit["canonical_name"], tmp_path / "s",
                           teto=25.0)


def test_bancos_distintos_passam_a_guarda(origem, tmp_path, monkeypatch):
    conn, unit, _, _ = origem
    ids = iter([("plm_casefile", "5432", "t0"),
                ("plm_casefile_test", "5432", "t0")])
    monkeypatch.setattr(rp, "identidade_do_banco", lambda c: next(ids))
    chamado = {}
    monkeypatch.setattr(rp, "_replay", lambda *a, **k: chamado.setdefault(
        "ok", True))
    assert rp.executar_replay(conn, os.environ["CASEFILE_TEST_DSN"],
                              unit["canonical_name"], tmp_path / "s",
                              teto=25.0)
    assert chamado == {"ok": True}


def test_identidade_distingue_bancos_do_mesmo_servidor(origem):
    conn, _, _, _ = origem
    a = rp.identidade_do_banco(conn)
    assert a[0] == conn.execute("SELECT current_database() AS d"
                                ).fetchone()["d"]
    assert len(a) == 3 and all(a)
