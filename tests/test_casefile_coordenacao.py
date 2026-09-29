"""Etapa D da arquitetura agêntica: Coordenador gera o grafo de tarefas.
Replay com cliente roteirizado (sem modelo pago), fake + Postgres. A
cobertura do plano de investigação é contagem de referências declaradas
pelo próprio Coordenador — nunca julgamento do código."""
import pytest

from src.casefile import cli, coordenacao as co, orquestracao as orq, worker as wk
from tests.helpers_casefile import (ClientRoteirizado, RepoFake, Texto, Use,
                                    conectar_pg_ou_skip, unit_de_teste)

TETO = 25.0
PACOTE = "title-texas-oil-gas-dd"


@pytest.fixture(params=["fake", pytest.param("pg", marks=pytest.mark.postgres)])
def repo(request):
    if request.param == "fake":
        yield RepoFake()
        return
    from src.casefile.db import migrar
    from src.casefile.repo import Repo
    conn, schema = conectar_pg_ou_skip()
    migrar(conn)
    yield Repo(conn)
    conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
    conn.close()


@pytest.fixture
def caso(repo, tmp_path):
    """Unit com plano v1 (3 pesquisas: 2 abertas, 1 cancelada), uma pesquisa
    posterior de outra sessão e uma pergunta ao operador."""
    unit = unit_de_teste(repo, tmp_path / "SINTETICA A UNIT")
    s1 = repo.abrir_sessao(unit["id"], "planejar", "m")
    ids = [repo.inserir_pesquisa(unit["id"], f"pesquisa {n}", f"o que {n}",
                                 "cartorio", "vol/pg", s1, [])
           for n in (1, 2, 3)]
    repo.marcar_pesquisa(ids[2], "cancelada")
    repo.propor_plano(unit["id"], "# plano v1", {"pesquisas": 3}, s1)
    s2 = repo.abrir_sessao(unit["id"], "coletar", "m")
    posterior = repo.inserir_pesquisa(unit["id"], "pesquisa 4", "o que 4",
                                      "acervo", "leitura", s2, [])
    pergunta = repo.registrar_pergunta_vs2(unit["id"], "Série X conta acres?")
    return {"unit": unit, "p": ids, "posterior": posterior,
            "pergunta": pergunta}


class Cliente(ClientRoteirizado):
    def __init__(self, roteiro):
        super().__init__(roteiro)
        self.chamadas = []

    def create(self, **kw):
        self.chamadas.append(dict(kw, messages=list(kw["messages"])))
        return super().create(**kw)


def _t(ref, role, pend, deps=(), budget=0.5):
    return {"ref": ref, "role": role, "title": f"tarefa {ref}",
            "input_json": {"alvo": ref}, "acceptance": "no esquema",
            "depends_on": list(deps), "budget_usd": budget, "priority": 1,
            "gate": "2 Coleta", "pendencias": pend,
            "justificativa": "gate 2 e pendência registrada"}


def _plano(caso):
    p1, p2, _ = caso["p"]
    return {"tarefas": [
        _t("pq-1", "pesquisador", [f"pesquisa:{p1}"]),
        _t("pq-2", "pesquisador", [f"pesquisa:{p2}",
                                   f"pesquisa:{caso['posterior']}"]),
        _t("ex-1", "examinador", [f"pesquisa:{p1}"], deps=["pq-1"]),
    ]}


def _entrega(saida, uid="u1"):
    return [Use("entregar_saida", {"saida": saida}, id=uid)]


# --- entrada e alvos ---------------------------------------------------------------

def test_entrada_do_coordenador_e_copia_do_case_file(repo, caso):
    unit = caso["unit"]
    repo.registrar_custo(unit["id"], "vs1", 4.0, {})
    e = co.entrada_do_coordenador(repo, unit, teto=TETO)
    p1, p2, p3 = caso["p"]
    assert [p["id"] for p in e["pendencias_abertas"]] == [
        f"pesquisa:{p1}", f"pesquisa:{p2}", f"pesquisa:{caso['posterior']}"]
    assert e["pendencias_abertas"][0]["o_que"] == "o que 1"
    assert e["decisoes_do_operador"][0]["id"] == f"decisao:{caso['pergunta']}"
    assert e["orcamento_usd"]["saldo_para_novas_tarefas"] == 21.0
    assert e["plano_de_investigacao"]["versao"] == 1
    assert e["unit"] == unit["canonical_name"]


def test_alvos_do_plano_sao_as_abertas_da_sessao_do_plano(repo, caso):
    p1, p2, p3 = caso["p"]
    alvos = co.alvos_do_plano(repo, caso["unit"]["id"])
    assert alvos["alvos"] == [f"pesquisa:{p1}", f"pesquisa:{p2}"]
    assert alvos["canceladas"] == [f"pesquisa:{p3}"]


def test_cobertura_conta_referencias():
    alvos = {"alvos": ["pesquisa:1", "pesquisa:2"],
             "canceladas": ["pesquisa:3"], "executadas": []}
    validas = {"pesquisa:1", "pesquisa:2", "pesquisa:3", "decisao:9"}
    c = co.cobertura([{"ref": "a", "pendencias": ["pesquisa:1", "pesquisa:3"]},
                      {"ref": "b", "pendencias": ["pesquisa:77"]},
                      {"ref": "c", "pendencias": []}], alvos, validas)
    assert c["cobertos"] == {"pesquisa:1": ["a"]}
    assert c["faltando"] == ["pesquisa:2"] and not c["completa"]
    assert c["inexistentes"] == ["pesquisa:77"]
    assert c["citam_cancelada"] == ["pesquisa:3"]
    assert c["tarefas_sem_pendencia"] == ["c"]


# --- o replay do Coordenador -------------------------------------------------------

def test_replay_coordenador_gera_grafo_que_cobre_o_plano(repo, caso):
    unit = caso["unit"]
    semente = co.semear_coordenador(repo, unit, pacote=PACOTE, teto=TETO,
                                    orcamento_usd=2.0,
                                    criado_por="human:renato")
    assert semente["status"] == "pronta" and semente["role"] == "coordenador"
    ciclo = _plano(caso)
    ciclo["tarefas"][0]["depends_on"] = ["ex-1"]
    cliente = Cliente([_entrega(ciclo), _entrega(_plano(caso), "u2"),
                       [Texto("plano entregue")]])
    r = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)

    # o erro de forma voltou ao modelo, que corrigiu no mesmo run
    volta = cliente.chamadas[1]["messages"][-1]["content"][0]["content"]
    assert "ciclo_de_dependencias" in volta
    assert r["erros"] == [] and r["entregas"] == 2
    assert r["tarefa"]["status"] == "aceita" and r["modelo"] == "claude-opus-5"
    assert len(r["gravados"]) == 3

    # a entrada do Coordenador chegou ao modelo com os ids das pendências
    tarefa_msg = cliente.chamadas[0]["messages"][0]["content"][0]["text"]
    assert f"pesquisa:{caso['p'][0]}" in tarefa_msg
    assert "title-texas-oil-gas-dd" in cliente.chamadas[0]["system"][0]["text"]

    tarefas = {t["ref"]: t for t in repo.tarefas(unit["id"])}
    assert tarefas["ex-1"]["status"] == "planejada"
    assert tarefas["pq-1"]["status"] == "pronta"
    assert tarefas["pq-1"]["created_by"] == \
        f"coordenador/tarefa:{semente['id']}"
    assert tarefas["pq-2"]["pendencias"] == [
        f"pesquisa:{caso['p'][1]}", f"pesquisa:{caso['posterior']}"]
    assert tarefas["ex-1"]["output_schema"] == "claims"
    assert tarefas["pq-1"]["pack"] == PACOTE

    alvos = co.alvos_do_plano(repo, unit["id"])
    c = co.cobertura([t for t in tarefas.values()
                      if t["role"] != "coordenador"], alvos,
                     co.pendencias_validas(repo, unit["id"]))
    assert c["completa"] and c["inexistentes"] == []


def test_plano_acima_do_saldo_volta_ao_coordenador(repo, caso):
    unit = caso["unit"]
    co.semear_coordenador(repo, unit, pacote=PACOTE, teto=TETO,
                          orcamento_usd=2.0, criado_por="human:renato")
    caro = _plano(caso)
    caro["tarefas"][0]["budget_usd"] = 30.0
    cliente = Cliente([_entrega(caro), [Texto("desisto")]])
    r = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    assert any("orcamento_do_plano_excede_saldo" in e for e in r["erros"])
    assert r["tarefa"]["status"] == "pronta"
    assert [t["ref"] for t in repo.tarefas(unit["id"])] == ["coordenador-1"]


def test_plano_valido_que_nao_grava_volta_ao_operador(repo, caso,
                                                      monkeypatch):
    unit = caso["unit"]
    co.semear_coordenador(repo, unit, pacote=PACOTE, teto=TETO,
                          orcamento_usd=2.0, criado_por="human:renato")

    def falha(*a, **k):
        raise orq.PlanoInvalido("ref_duplicada: criada por outro caminho")

    monkeypatch.setattr(orq, "planejar", falha)
    cliente = Cliente([_entrega(_plano(caso)), [Texto("ok")]])
    r = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    assert r["tarefa"]["status"] == "aguardando_operador"
    assert r["erros"][0].startswith("saida_valida_nao_gravada")
    [e] = repo.escalonamentos(unit["id"], abertos=True)
    assert e["motivo"] == "gravacao"


def test_pendencia_mal_formada_e_erro_de_esquema(repo, caso):
    ruim = _plano(caso)
    ruim["tarefas"][0]["pendencias"] = ["pesquisa um"]
    erros = orq.checar_plano(repo, caso["unit"]["id"], ruim, teto=TETO,
                             pacote=PACOTE)
    assert erros and "fora do esquema" in erros[0]


# --- CLI ------------------------------------------------------------------------

def test_cli_coordenar_trabalhar_cobertura(repo, caso, capsys, monkeypatch):
    unit = caso["unit"]
    nome = unit["canonical_name"]
    monkeypatch.setenv("CASEFILE_TETO_UNIT_USD", str(TETO))
    cli.cmd_coordenar(nome, PACOTE, 2.0, repo=repo)
    assert "tarefa coordenador-1 (pronta)" in capsys.readouterr().out
    cliente = Cliente([_entrega(_plano(caso)), [Texto("ok")]])
    cli.cmd_trabalhar(nome, 1, repo=repo, client=cliente)
    saida = capsys.readouterr().out
    assert "coordenador-1" in saida and "3 gravado(s)" in saida
    assert "limite de 1 tarefas" in saida
    cli.cmd_cobertura(nome, None, repo=repo)
    saida = capsys.readouterr().out
    assert "2/2" in saida and "COMPLETA" in saida
    assert "canceladas pelo operador" in saida
    cli.cmd_coordenar(nome, PACOTE, 2.0, repo=repo)
    assert "coordenador-2" in capsys.readouterr().out
