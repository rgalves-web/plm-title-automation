"""Dois workers de verdade (duas conexões, duas threads) contra o mesmo
saldo da unit no Postgres de teste. A reserva no banco serializa pela linha
da unit: a soma das reservas nunca passa do saldo."""
import os
import threading

import pytest

from src.casefile import orquestracao as orq, worker as wk
from tests.helpers_casefile import (ClientRoteirizado, Texto, Use,
                                    conectar_pg_ou_skip, unit_de_teste)

pytestmark = pytest.mark.postgres
TETO = 25.0
PROJECAO = {"celulas": [], "brancos": []}


@pytest.fixture
def dois(tmp_path):
    from src.casefile.db import migrar
    from src.casefile.repo import Repo
    import psycopg
    from psycopg.rows import dict_row
    conn1, schema = conectar_pg_ou_skip()
    migrar(conn1)
    conn2 = psycopg.connect(os.environ["CASEFILE_TEST_DSN"], autocommit=True,
                            row_factory=dict_row)
    conn2.execute(f'SET search_path TO "{schema}"')
    r1, r2 = Repo(conn1), Repo(conn2)
    unit = unit_de_teste(r1, tmp_path / "UNIT")
    yield r1, r2, unit
    conn2.close()
    conn1.execute(f'DROP SCHEMA "{schema}" CASCADE')
    conn1.close()


def _planejar(repo, unit, saldo, budget, n=2):
    """Plano feito quando havia saldo; depois o saldo encolhe (outros
    gastos): é aí que dois runs podem disputar o mesmo dinheiro."""
    orq.planejar(repo, unit["id"], {"tarefas": [
        {"ref": f"t{i}", "role": "redator", "title": f"t{i}",
         "input_json": {}, "acceptance": "x", "depends_on": [],
         "budget_usd": budget, "priority": i, "justificativa": "teste"}
        for i in range(n)]}, criado_por="human:teste", teto=TETO)
    repo.registrar_custo(unit["id"], "vs3", TETO - saldo, {})


def test_reservas_simultaneas_nunca_somam_mais_que_o_saldo(dois):
    r1, r2, unit = dois
    _planejar(r1, unit, saldo=1.0, budget=0.8)
    _, run1 = orq.pegar(r1, unit["id"], "w1", teto=TETO)
    _, run2 = orq.pegar(r2, unit["id"], "w2", teto=TETO)
    for _ in range(20):
        r1.conn.execute("UPDATE task_runs SET reserved_usd = 0")
        barreira = threading.Barrier(2)
        got = {}

        def reservar(repo, run, w):
            barreira.wait()
            got[w] = repo.reservar_orcamento(run["id"], w, TETO)["reserva"]

        ts = [threading.Thread(target=reservar, args=(r1, run1, "w1")),
              threading.Thread(target=reservar, args=(r2, run2, "w2"))]
        for t in ts:
            t.start()
        for t in ts:
            t.join(10)
        assert sorted(got.values()) == [0.2, 0.8]
        assert sum(got.values()) <= 1.0


class Bloqueante(ClientRoteirizado):
    """Segura a 1ª chamada até o teste soltar: o run de w1 fica aberto,
    com a reserva feita, enquanto w2 tenta trabalhar."""

    def __init__(self, roteiro):
        super().__init__(roteiro)
        self.dentro, self.soltar = threading.Event(), threading.Event()

    def create(self, **kw):
        self.dentro.set()
        assert self.soltar.wait(20)
        return super().create(**kw)


class Registrador(ClientRoteirizado):
    def __init__(self):
        super().__init__([])
        self.chamadas = 0

    def create(self, **kw):
        self.chamadas += 1
        return super().create(**kw)


def test_duas_execucoes_concorrentes_nao_gastam_o_mesmo_saldo(dois):
    r1, r2, unit = dois
    _planejar(r1, unit, saldo=0.8, budget=0.8)
    c1 = Bloqueante([[Use("entregar_saida", {"saida": PROJECAO})],
                     [Texto("ok")]])
    res = {}
    t = threading.Thread(target=lambda: res.setdefault(
        "w1", wk.executar_uma(r1, unit["id"], "w1", teto=TETO, client=c1)))
    t.start()
    assert c1.dentro.wait(20)                  # w1 reservou e está chamando
    reservado = r2.conn.execute(
        "SELECT coalesce(sum(reserved_usd), 0) AS s FROM task_runs "
        "WHERE finished_at IS NULL").fetchone()["s"]
    assert float(reservado) == 0.8
    c2 = Registrador()
    r_w2 = wk.executar_uma(r2, unit["id"], "w2", teto=TETO, client=c2)
    assert c2.chamadas == 0                    # w2 não chamou o modelo
    assert r_w2["parada"] == "saldo_reservado_por_outros"
    assert r_w2["tarefa"]["status"] == "pronta"
    c1.soltar.set()
    t.join(30)
    assert res["w1"]["tarefa"]["status"] == "aguardando_operador"
    assert r1.conn.execute(
        "SELECT count(*) AS n FROM task_runs WHERE finished_at IS NULL "
        "AND reserved_usd > 0").fetchone()["n"] == 0   # reserva liberada
    assert r1.escalonamentos(unit["id"], abertos=True) == []


def test_saldo_zero_continua_bloqueando_sem_chamar(dois):
    r1, r2, unit = dois
    _planejar(r1, unit, saldo=0.8, budget=0.0, n=1)
    c = Registrador()
    r = wk.executar_uma(r2, unit["id"], "w2", teto=TETO, client=c)
    assert c.chamadas == 0 and r["tarefa"]["status"] == "bloqueada"
    assert r["parada"] == "sem_saldo"
