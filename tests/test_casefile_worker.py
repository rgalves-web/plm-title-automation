"""Etapa C da arquitetura agêntica: worker genérico em replay sintético.
Cliente roteirizado no lugar do modelo — nenhuma chamada paga. A mesma
bateria contra o RepoFake e contra o Postgres real."""
import pytest

from src.casefile import agentes, orquestracao as orq, worker as wk
from src.casefile.orquestracao_repo import TransicaoInvalida
from src.examinador.loop import RATES
from tests.helpers_casefile import (ClientRoteirizado, RepoFake, Texto, Use,
                                    conectar_pg_ou_skip, unit_de_teste)

TETO = 25.0
PACOTE = "title-texas-surface"
SHA = "ab" * 32


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
def unit(repo, tmp_path):
    u = unit_de_teste(repo, tmp_path / "TRACT-1")
    fid = repo.registrar_source_file(SHA, 100)
    repo.registrar_sighting(fid, u["id"], str(tmp_path / "deed.pdf"), "",
                            "deed.pdf", "unit_files")
    return u


class Cliente(ClientRoteirizado):
    """Roteiro + registro do que o worker mandou ao "modelo"."""

    def __init__(self, roteiro):
        super().__init__(roteiro)
        self.chamadas = []

    def create(self, **kw):
        # retrato: o laço muta a mesma lista de mensagens a cada turno
        self.chamadas.append(dict(kw, messages=list(kw["messages"])))
        return super().create(**kw)


def _t(ref, role, deps=(), budget=2.0, prio=1, entrada=None):
    return {"ref": ref, "role": role, "title": f"tarefa {ref}",
            "input_json": entrada or {"tract": "BBT-SNN-TESTE"},
            "acceptance": "saída no esquema", "depends_on": list(deps),
            "budget_usd": budget, "priority": prio, "gate": "G2",
            "justificativa": "gate 2 do pacote"}


def _planejar(repo, unit, *tarefas):
    return orq.planejar(repo, unit["id"], {"tarefas": list(tarefas)},
                        criado_por="coordenador/teste", teto=TETO,
                        pacote=PACOTE)


def _entrega(saida, uid="u1"):
    return [Use("entregar_saida", {"saida": saida}, id=uid)]


PESQUISA = {"fonte": "CountyRecords", "encontrados": [{
    "referencia_registro": "OR 50/611", "tipo": "deed",
    "localizador": "Terrell OR 50/611"}], "busca_negativa": [{
        "target": "releases", "terms": ["ROE, JOHN"], "scope": "grantor",
        "populacao": "índice de grantor", "tipos_documentais": ["release"],
        "intervalo": {"de": "1966-01-01", "ate": "2026-09-01"},
        "cobertura_fonte": "1966+"}], "pedidos_de_captura": []}

CLAIM = {"tipo": "fact", "entidade": "Tract 1",
         "valor": {"tipo_resultado": "fato_documental", "grantor": "John Roe"},
         "documento": f"sha256:{SHA}", "pagina": "1",
         "trecho": "John Roe grants, sells and conveys", "confianca": "alta",
         "materialidade": "alta", "celulas_candidatas": ["Surface!B7"]}


# --- o replay ---------------------------------------------------------------

def test_replay_pesquisa_exame_verificacao_ate_aceite(repo, unit):
    _planejar(repo, unit, _t("pq", "pesquisador"),
              _t("ex", "examinador", deps=["pq"]),
              _t("v", "verificador", deps=["ex"],
                 entrada={"tarefa_verificada": "ex", "claim_id": 1,
                          "pergunta": "Quem é o grantor?"}))
    fora_do_censo = dict(CLAIM, documento="sha256:" + "cd" * 32)
    cliente = Cliente([
        _entrega(PESQUISA), [Texto("entregue")],                # pq
        _entrega({"claims": [fora_do_censo]}),                  # ex: erro
        _entrega({"claims": [CLAIM]}, "u2"), [Texto("ok")],     # ex: corrige
    ])
    r1 = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    assert r1["tarefa"]["ref"] == "pq"
    assert r1["tarefa"]["status"] == "aguardando_operador"   # amostral
    assert r1["modelo"] == "claude-sonnet-5" and r1["erros"] == []
    assert wk.executar_uma(repo, unit["id"], "w1", teto=TETO,
                           client=cliente) is None       # ex espera pq
    orq.decidir(repo, r1["tarefa"]["id"], aceitar=True, ator="human:renato",
                nota="busca negativa com população declarada")

    r2 = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    assert r2["tarefa"]["ref"] == "ex" and r2["modelo"] == "claude-opus-5"
    assert r2["entregas"] == 2 and r2["erros"] == []
    assert r2["tarefa"]["status"] == "aguardando_verificacao"
    # o modelo viu o erro nomeado da primeira entrega e corrigiu
    resposta = cliente.chamadas[3]["messages"][-1]["content"][0]["content"]
    assert "nao esta no censo" in resposta
    [cid] = r2["gravados"]
    assert repo.claims_da_tarefa(r2["tarefa"]["id"]) == [cid]
    claim = repo.claim(cid)
    assert claim["source_sha256"] == SHA and claim["session_id"]
    assert claim["ddr_candidates"] == ["Surface!B7"]

    # Verificador não roda no worker genérico: fica pronta, intocada
    assert wk.executar_uma(repo, unit["id"], "w1", teto=TETO,
                           client=cliente) is None
    v = repo.tarefa_por_ref(unit["id"], "v")
    assert v["status"] == "pronta" and repo.runs_da_tarefa(v["id"]) == []
    assert orq.entrada_do_verificador(repo, v)["pergunta"] == \
        "Quem é o grantor?"

    repo.registrar_verificacao(cid, "Quem é o grantor?", "concordancia",
                               "gpt", {}, {}, 0.0)
    got = orq.aceitar_por_verificacao(repo, r2["tarefa"]["id"])
    assert got["aceita"]
    assert cliente.roteiro == []


def test_contexto_vem_das_fichas_e_do_esquema(repo, unit):
    _planejar(repo, unit, _t("ex", "examinador"))
    cliente = Cliente([_entrega({"claims": [CLAIM]}), [Texto("ok")]])
    r = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    sistema = cliente.chamadas[0]["system"][0]["text"]
    tarefa = cliente.chamadas[0]["messages"][0]["content"][0]["text"]
    raiz = agentes.RAIZ_PADRAO
    assert agentes.versao(raiz / "nucleo/examinador.md")[:12] in sistema
    assert "Não se autoverifica" in sistema               # corpo da ficha
    assert "## Pacote de dominio `title-texas-surface`" in sistema
    # lições draft nunca entram (as 3 de surface são draft)
    assert "Licao publicada" not in sistema and r["licoes"] == []
    assert "rrc-gis" not in sistema
    assert "BBT-SNN-TESTE" in tarefa                      # entrada da tarefa
    assert '"tipo_resultado"' in tarefa                   # esquema claims
    assert "ler_pagina" in tarefa and "indisponiveis" in tarefa
    assert set(r["indisponiveis"]) == {
        "ler_pagina", "buscar_no_acervo", "consultar_conhecimento_publicado",
        "registrar_claims", "abrir_escalonamento"}
    nomes = [t["name"] for t in cliente.chamadas[0]["tools"]]
    assert nomes == ["entregar_saida"]


def test_esquema_referenciado_vai_junto(repo, unit):
    _planejar(repo, unit, _t("arb", "arbitro"))
    cliente = Cliente([[Texto("nada")]] * 3)
    wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    tarefa = cliente.chamadas[0]["messages"][0]["content"][0]["text"]
    assert "### adjudicacao.json" in tarefa and "### claims.json" in tarefa


def test_ficha_e_a_lista_de_permissao_de_ferramentas(repo, unit):
    chamadas = []

    def ler_pagina(documento, pagina):
        chamadas.append((documento, pagina))
        return {"texto": "John Roe grants, sells and conveys"}

    schema = {"name": "ler_pagina", "description": "lê",
              "input_schema": {"type": "object", "properties": {
                  "documento": {"type": "string"},
                  "pagina": {"type": "string"}}}}
    fora = {"name": "comprar_copia", "description": "paga",
            "input_schema": {"type": "object", "properties": {}}}
    _planejar(repo, unit, _t("ex", "examinador"))
    cliente = Cliente([
        [Use("ler_pagina", {"documento": "deed.pdf", "pagina": "1"})],
        _entrega({"claims": [CLAIM]}, "u2"), [Texto("ok")]])
    r = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente,
                        ferramentas={"ler_pagina": (schema, ler_pagina),
                                     "comprar_copia": (fora, lambda: 1)})
    assert chamadas == [("deed.pdf", "1")]
    nomes = [t["name"] for t in cliente.chamadas[0]["tools"]]
    assert nomes == ["entregar_saida", "ler_pagina"]   # comprar: fora da ficha
    assert "ler_pagina" not in r["indisponiveis"]
    assert r["tarefa"]["status"] == "aguardando_verificacao"


# --- falhas viram estado, nunca silêncio -------------------------------------------

def test_sem_entrega_tres_vezes_vira_recusada(repo, unit):
    _planejar(repo, unit, _t("co", "coordenador"))
    cliente = Cliente([[Texto("pensei, mas não entreguei")]] * 3)
    for n in (1, 2, 3):
        r = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
        run = repo.run(r["run_id"])
        assert run["stop_reason"] == "sem_entrega" and not run["output_valid"]
    assert r["tarefa"]["status"] == "recusada"


def test_entrega_invalida_nao_grava_claims(repo, unit):
    _planejar(repo, unit, _t("ex", "examinador"))
    ruim = dict(CLAIM, documento="sha256:" + "cd" * 32)
    cliente = Cliente([_entrega({"claims": [ruim]}), [Texto("fim")]])
    r = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    assert r["tarefa"]["status"] == "pronta" and r["gravados"] == []
    assert any("nao esta no censo" in e for e in r["erros"])
    assert repo.claims_da_unit(unit["id"]) == []


def test_erro_do_modelo_fecha_o_run_e_conta_o_gasto(repo, unit):
    _planejar(repo, unit, _t("co", "coordenador"))

    class Quebra(Cliente):
        def create(self, **kw):
            if len(self.chamadas) == 1:
                self.chamadas.append(kw)
                raise RuntimeError("sem conexão")
            return super().create(**kw)

    cliente = Quebra([[Use("ferramenta_inexistente", {})]])
    r = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    run = repo.run(r["run_id"])
    assert run["stop_reason"] == "erro_do_modelo"
    assert r["parada"].startswith("erro_do_modelo: RuntimeError")
    esperado = round((10 * 5.0 + 5 * 25.0) / 1e6, 4)     # 1 turno de opus
    assert run["cost_usd"] == esperado == r["custo_usd"]
    assert r["tarefa"]["status"] == "pronta"


def test_custo_por_tarifa_da_tabela_e_no_livro_da_unit(repo, unit):
    _planejar(repo, unit, _t("co", "coordenador"))
    cliente = Cliente([_entrega({"tarefas": []}), [Texto("ok")]])
    r = wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    rate = RATES["claude-opus-5"]
    esperado = round((20 * rate["input"] + 10 * rate["output"]) / 1e6, 4)
    run = repo.run(r["run_id"])
    assert run["cost_usd"] == esperado and run["model_family"] == "A"
    assert run["tokens_in"] == 20 and run["tokens_out"] == 10
    assert len(run["prompt_sha256"]) == 64
    assert repo.custo_acumulado(unit["id"]) == esperado
    assert r["tarefa"]["status"] == "aceita"


def test_trava_perdida_no_meio_nao_vale_mas_o_gasto_conta(repo, unit):
    _planejar(repo, unit, _t("co", "coordenador"))
    cliente = Cliente([[Use("entregar_saida", {"saida": {"tarefas": []}})],
                       [Texto("ok")]])

    real = repo.renovar_lease

    def roubada(run_id, worker, segundos):
        # outro worker retomou a tarefa depois que a trava venceu
        real(run_id, worker, -1)
        orq.pegar(repo, unit["id"], "w2", teto=TETO)
        real(run_id, worker, segundos)

    repo.renovar_lease = roubada
    with pytest.raises(TransicaoInvalida):
        wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=cliente)
    repo.renovar_lease = real
    perdidos = [c for c in repo.custos_da_unit(unit["id"])
                if (c["detail"] or {}).get("run_perdido")]
    assert len(perdidos) == 1 and float(perdidos[0]["amount_usd"]) > 0
    t = repo.tarefa_por_ref(unit["id"], "co")
    assert t["status"] == "em_execucao"                  # agora é do w2
    assert repo.runs_da_tarefa(t["id"])[-1]["worker"] == "w2"


def test_teto_para_o_replay(repo, unit):
    _planejar(repo, unit, _t("a", "coordenador"), _t("b", "coordenador"))
    repo.registrar_custo(unit["id"], "vs3", TETO, {})
    got = wk.executar_ate_parar(repo, unit["id"], "w1", teto=TETO,
                                client=Cliente([]))
    assert got["execucoes"] == [] and got["parada"].startswith("teto")
    assert {t["status"] for t in repo.tarefas(unit["id"])} == {"bloqueada"}


def test_executar_ate_parar_roda_a_cadeia(repo, unit):
    _planejar(repo, unit, _t("a", "coordenador"),
              _t("b", "coordenador", deps=["a"]),
              _t("c", "coordenador", deps=["b"]))
    cliente = Cliente([_entrega({"tarefas": []}), [Texto("ok")]] * 3)
    got = wk.executar_ate_parar(repo, unit["id"], "w1", teto=TETO,
                                client=cliente)
    assert [e["tarefa"]["ref"] for e in got["execucoes"]] == ["a", "b", "c"]
    assert got["parada"] == "sem tarefa pronta para este worker"
    assert {t["status"] for t in repo.tarefas(unit["id"])} == {"aceita"}
    assert got["custo_usd"] == round(
        sum(e["custo_usd"] for e in got["execucoes"]), 4)


def test_modelo_sem_tarifa_nao_roda(repo, unit):
    _planejar(repo, unit, _t("co", "coordenador"))
    with pytest.raises(ValueError, match="modelo_sem_tarifa"):
        wk.executar_uma(repo, unit["id"], "w1", teto=TETO,
                        client=Cliente([]),
                        modelos={"forte": "modelo-desconhecido"})


def test_modelo_por_nivel_segue_a_decisao_do_operador():
    assert wk.MODELO_POR_NIVEL["forte"].startswith("claude-opus")
    assert wk.MODELO_POR_NIVEL["medio"].startswith("claude-sonnet")
    assert wk.MODELO_POR_NIVEL["barato"].startswith("claude-haiku")
    assert set(wk.MODELO_POR_NIVEL) == set(agentes.NIVEIS_MODELO)
    assert all(m in RATES for m in wk.MODELO_POR_NIVEL.values())


def test_cli_tarefas_lista_o_grafo(repo, unit, capsys, monkeypatch):
    from src.casefile import cli
    _planejar(repo, unit, _t("a", "coordenador"),
              _t("b", "coordenador", deps=["a"]))
    cli.cmd_tarefas(unit["canonical_name"], repo=repo)
    saida = capsys.readouterr().out
    assert "2 tarefa(s)" in saida
    assert "depende de a" in saida and "pronta" in saida
