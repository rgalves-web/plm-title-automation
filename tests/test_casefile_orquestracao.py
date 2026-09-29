"""Etapa B da arquitetura agêntica: tarefas, runs, escalonamentos.
Plumbing (dependências, trava, orçamento, quarentena, versão das fichas),
a mesma bateria contra o RepoFake e contra o Postgres real."""
import pytest

from src.casefile import agentes, orquestracao as orq
from src.casefile.orquestracao_repo import TransicaoInvalida
from tests.helpers_casefile import RepoFake, conectar_pg_ou_skip, unit_de_teste

TETO = 25.0
PACOTE = "title-texas-surface"


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
    return unit_de_teste(repo, tmp_path / "UNIT")


# Função genérica dos testes de plumbing: o Verificador (verifica
# nao_aplicavel → aceita direto). O Coordenador não serve mais para isso:
# a saída dele nunca é aceita sem o operador (ESQUEMAS_COM_ACEITE_HUMANO).
VERIF = {"claim_id": 1, "question": "q", "verdict": "concordancia",
         "verifier_model": "gpt", "verifier_value": {},
         "source_sha256": "a" * 64, "page": "1", "prompt_sha256": "b" * 64,
         "raw_response": "{}", "request_id": "", "status": "valida"}


def _t(ref, role="verificador", deps=(), budget=1.0, prio=1, entrada=None):
    return {"ref": ref, "role": role, "title": f"tarefa {ref}",
            "input_json": entrada or {}, "acceptance": "saída no esquema",
            "depends_on": list(deps), "budget_usd": budget, "priority": prio,
            "gate": "G0", "justificativa": "gate 0 do pacote"}


def _planejar(repo, unit, *tarefas, teto=TETO):
    return orq.planejar(repo, unit["id"], {"tarefas": list(tarefas)},
                        criado_por="coordenador/teste", teto=teto,
                        pacote=PACOTE)


def _status(repo, unit):
    return {t["ref"]: t["status"] for t in repo.tarefas(unit["id"])}


def _rodar(repo, unit, worker="w1", saida=None, **meta):
    got = orq.pegar(repo, unit["id"], worker, teto=TETO)
    assert got is not None
    task, run = got
    res = orq.entregar(repo, run["id"], worker,
                       VERIF if saida is None else saida,
                       teto=TETO, **meta)
    return task, run, res


def _claim(repo, unit, n=1):
    sha = f"{n:064x}"
    repo.registrar_source_file(sha, 10)
    sessao = repo.abrir_sessao(unit["id"], "teste", "m")
    return repo.inserir_claim(unit["id"], "fact", f"Tract {n}",
                              {"tipo_resultado": "fato_documental",
                               "grantor": "John Roe"},
                              sha, "1", "John Roe grants", "alta", "alta",
                              sessao)


CLAIM_SAIDA = {"claims": [{
    "tipo": "fact", "entidade": "Tract 1",
    "valor": {"tipo_resultado": "fato_documental", "grantor": "John Roe"},
    "documento": "sha256:" + "0" * 63 + "1", "pagina": "1",
    "trecho": "John Roe grants", "confianca": "alta"}]}


# --- planejar ------------------------------------------------------------------

def test_plano_valido_cria_grafo_e_promove_sem_dependencia(repo, unit):
    criadas = _planejar(repo, unit, _t("a"), _t("b", deps=["a"]),
                        _t("ex", role="examinador", deps=["a"]),
                        _t("pq", role="pesquisador"))
    assert _status(repo, unit) == {"a": "pronta", "b": "planejada",
                                   "ex": "planejada", "pq": "pronta"}
    por_ref = {t["ref"]: t for t in criadas}
    assert por_ref["b"]["depends_on"] == [por_ref["a"]["id"]]
    assert por_ref["ex"]["output_schema"] == "claims"
    assert por_ref["a"]["verificacao"] == "nenhuma"
    assert por_ref["ex"]["verificacao"] == "obrigatoria"
    assert por_ref["pq"]["verificacao"] == "operador"   # amostral: conservador
    assert por_ref["a"]["pack"] == PACOTE
    assert por_ref["a"]["justificativa"] == "[G0] gate 0 do pacote"
    trilha = repo.transicoes_da_tarefa(por_ref["a"]["id"])
    assert [(x["from_status"], x["to_status"]) for x in trilha] == \
        [("", "planejada"), ("planejada", "pronta")]


def test_plano_fora_do_esquema_nao_cria_nada(repo, unit):
    ruim = _t("a")
    del ruim["acceptance"]
    with pytest.raises(orq.PlanoInvalido, match="fora do esquema"):
        _planejar(repo, unit, ruim)
    assert repo.tarefas(unit["id"]) == []


@pytest.mark.parametrize("tarefas,erro", [
    ([_t("a", deps=["b"]), _t("b", deps=["a"])], "ciclo_de_dependencias"),
    ([_t("a", deps=["a"])], "ciclo_de_dependencias"),
    ([_t("a", deps=["fantasma"])], "dependencia_inexistente"),
    ([_t("a"), _t("a")], "ref_duplicada"),
    ([_t("a", budget=20.0), _t("b", budget=6.0)],
     "orcamento_do_plano_excede_saldo"),
    ([_t("v", role="verificador",
         entrada={"tarefa_verificada": "x", "valor": "John Roe"})],
     "quarentena"),
])
def test_plano_recusado_com_erro_nomeado_e_tudo_ou_nada(repo, unit, tarefas,
                                                        erro):
    with pytest.raises(orq.PlanoInvalido, match=erro):
        _planejar(repo, unit, *tarefas)
    assert repo.tarefas(unit["id"]) == []


def test_replanejar_nao_recria_ref_existente_e_resolve_dependencia_antiga(
        repo, unit):
    _planejar(repo, unit, _t("a"))
    with pytest.raises(orq.PlanoInvalido, match="ref_duplicada"):
        _planejar(repo, unit, _t("a"))
    _planejar(repo, unit, _t("c", deps=["a"]))
    assert _status(repo, unit) == {"a": "pronta", "c": "planejada"}


def test_orcamento_do_plano_conta_o_que_ja_esta_em_aberto(repo, unit):
    _planejar(repo, unit, _t("a", budget=20.0))
    with pytest.raises(orq.PlanoInvalido, match="excede_saldo"):
        _planejar(repo, unit, _t("b", budget=6.0))
    repo.registrar_custo(unit["id"], "vs3", 4.0, {})
    with pytest.raises(orq.PlanoInvalido, match="excede_saldo"):
        _planejar(repo, unit, _t("b", budget=1.5))
    _planejar(repo, unit, _t("b", budget=1.0))


def test_pacote_inexistente_e_recusado(repo, unit):
    with pytest.raises(orq.PlanoInvalido, match="pacote_inexistente"):
        orq.planejar(repo, unit["id"], {"tarefas": [_t("a")]},
                     criado_por="x/y", teto=TETO, pacote="brasil-fundiario")


# --- regra 1: dependências ------------------------------------------------------

def test_so_fica_pronta_quando_todas_as_dependencias_estao_aceitas(repo, unit):
    _planejar(repo, unit, _t("a"), _t("b"), _t("c", deps=["a", "b"]))
    task, _, res = _rodar(repo, unit)
    assert task["ref"] == "a" and res["tarefa"]["status"] == "aceita"
    orq.pegar(repo, unit["id"], "w1", teto=TETO)   # pega b, não entrega
    assert _status(repo, unit)["c"] == "planejada"
    assert orq.pegar(repo, unit["id"], "w2", teto=TETO) is None


def test_verificador_sai_quando_a_tarefa_verificada_aguarda_verificacao(
        repo, unit):
    """Sem esta exceção a verificação nunca começa: o Examinador só é aceito
    depois do Verificador. Vale só para o Verificador."""
    ent = {"tarefa_verificada": "ex", "pergunta": "Quem é o grantor?"}
    _planejar(repo, unit, _t("ex", role="examinador"),
              _t("v", role="verificador", deps=["ex"], entrada=ent),
              _t("co", role="redator", deps=["ex"]))
    _rodar(repo, unit, saida=CLAIM_SAIDA)
    assert _status(repo, unit) == {"ex": "aguardando_verificacao",
                                   "v": "planejada", "co": "planejada"}
    repo.promover_prontas(unit["id"], "process:teste")
    assert _status(repo, unit) == {"ex": "aguardando_verificacao",
                                   "v": "pronta", "co": "planejada"}


def test_dependencia_recusada_nunca_libera(repo, unit):
    _planejar(repo, unit, _t("a"), _t("b", deps=["a"]))
    for _ in range(orq.MAX_RETENTATIVAS + 1):
        _rodar(repo, unit, saida={"nada": 1})
    assert _status(repo, unit) == {"a": "recusada", "b": "planejada"}
    assert orq.pegar(repo, unit["id"], "w1", teto=TETO) is None


def test_prioridade_menor_sai_primeiro(repo, unit):
    _planejar(repo, unit, _t("baixa", prio=5), _t("alta", prio=1),
              _t("media", prio=3))
    ordem = [orq.pegar(repo, unit["id"], f"w{i}", teto=TETO)[0]["ref"]
             for i in range(3)]
    assert ordem == ["alta", "media", "baixa"]


# --- regra 2: trava com expiração -------------------------------------------------

def test_queda_do_worker_libera_a_tarefa_sem_perda(repo, unit):
    _planejar(repo, unit, _t("a"))
    # w1 pega e "cai": a trava já nasce vencida
    t1, r1 = orq.pegar(repo, unit["id"], "w1", teto=TETO, lease_segundos=-1)
    t2, r2 = orq.pegar(repo, unit["id"], "w2", teto=TETO)
    assert t2["id"] == t1["id"] and r2["id"] != r1["id"]
    assert repo.run(r1["id"])["stop_reason"] == "lease_expirado"
    assert [x["note"] for x in repo.transicoes_da_tarefa(t1["id"])
            ].count("lease expirado") == 1
    with pytest.raises(TransicaoInvalida):
        orq.entregar(repo, r1["id"], "w1", VERIF, teto=TETO)
    res = orq.entregar(repo, r2["id"], "w2", VERIF, teto=TETO)
    assert res["tarefa"]["status"] == "aceita"


def test_trava_viva_nao_e_roubada_e_renovacao_e_do_dono(repo, unit):
    _planejar(repo, unit, _t("a"))
    _, run = orq.pegar(repo, unit["id"], "w1", teto=TETO)
    assert orq.pegar(repo, unit["id"], "w2", teto=TETO) is None
    repo.renovar_lease(run["id"], "w1", 600)
    with pytest.raises(TransicaoInvalida):
        repo.renovar_lease(run["id"], "w2", 600)
    with pytest.raises(TransicaoInvalida):
        orq.entregar(repo, run["id"], "w2", VERIF, teto=TETO)


# --- regra 3: saída contra o esquema ------------------------------------------

def test_saida_invalida_volta_com_erro_nomeado_ate_duas_vezes(repo, unit):
    _planejar(repo, unit, _t("a"))
    for n in (1, 2):
        task, run, res = _rodar(repo, unit, saida={"tarefas": "nao-lista"})
        assert res["tarefa"]["status"] == "pronta"
        assert res["erros"] and "required property" in res["erros"][0]
        fechado = repo.run(run["id"])
        assert fechado["output_valid"] is False
        assert fechado["stop_reason"] == "saida_invalida"
        assert fechado["validation_errors"] == res["erros"]
    task, run, res = _rodar(repo, unit, saida={})
    assert res["tarefa"]["status"] == "recusada"
    notas = [x["note"] for x in repo.transicoes_da_tarefa(task["id"])]
    assert any("saida_fora_do_esquema (3/3)" in n for n in notas)
    assert orq.pegar(repo, unit["id"], "w1", teto=TETO) is None


def test_saida_valida_segue_o_modo_de_verificacao(repo, unit):
    _planejar(repo, unit, _t("co"), _t("ex", role="examinador", prio=2),
              _t("pq", role="pesquisador", prio=3))
    _, _, res = _rodar(repo, unit)
    assert res["tarefa"]["status"] == "aceita"
    _, _, res = _rodar(repo, unit, saida=CLAIM_SAIDA)
    assert res["tarefa"]["status"] == "aguardando_verificacao"
    _, _, res = _rodar(repo, unit, saida={
        "fonte": "CountyRecords", "encontrados": [], "busca_negativa": [],
        "pedidos_de_captura": []})
    assert res["tarefa"]["status"] == "aguardando_operador"


# --- regra 4: verificação obrigatória ---------------------------------------------

def _examinador_aguardando(repo, unit):
    _planejar(repo, unit, _t("ex", role="examinador"))
    task, _, res = _rodar(repo, unit, saida=CLAIM_SAIDA)
    assert res["tarefa"]["status"] == "aguardando_verificacao"
    return task


def _verif(repo, cid, verdict):
    return repo.registrar_verificacao(cid, "q", verdict, "b", {}, {}, 0.0)


def test_aceite_exige_verificacao_valida_e_concordante_de_cada_claim(
        repo, unit):
    task = _examinador_aguardando(repo, unit)
    with pytest.raises(orq.DecisaoInvalida, match="sem_claims_vinculados"):
        orq.aceitar_por_verificacao(repo, task["id"])
    c1, c2 = _claim(repo, unit, 1), _claim(repo, unit, 2)
    repo.vincular_claims(task["id"], [c1, c2])
    got = orq.aceitar_por_verificacao(repo, task["id"])
    assert not got["aceita"] and got["sem_verificacao"] == [c1, c2]
    _verif(repo, c1, "concordancia")
    v2 = _verif(repo, c2, "divergencia")
    got = orq.aceitar_por_verificacao(repo, task["id"])
    assert not got["aceita"] and got["nao_concordantes"] == {
        c2: "divergencia"}
    repo.invalidar_verificacao(v2, "página errada")
    _verif(repo, c2, "evidencia_insuficiente")
    got = orq.aceitar_por_verificacao(repo, task["id"])
    assert got["nao_concordantes"] == {c2: "evidencia_insuficiente"}
    _verif(repo, c2, "concordancia")
    got = orq.aceitar_por_verificacao(repo, task["id"])
    assert got["aceita"] and got["tarefa"]["status"] == "aceita"


def test_claim_de_outra_unit_nao_se_vincula(repo, unit, tmp_path):
    task = _examinador_aguardando(repo, unit)
    outra = unit_de_teste(repo, tmp_path / "OUTRA", "OUTRA UNIT")
    with pytest.raises(ValueError, match="claim_fora_da_unit"):
        repo.vincular_claims(task["id"], [_claim(repo, outra, 7)])


def test_decisao_do_operador_e_do_arbitro(repo, unit):
    task = _examinador_aguardando(repo, unit)
    with pytest.raises(orq.DecisaoInvalida, match="nota_ausente"):
        orq.decidir(repo, task["id"], aceitar=True, ator="human:renato",
                    nota=" ")
    with pytest.raises(orq.DecisaoInvalida, match="ator_invalido"):
        orq.decidir(repo, task["id"], aceitar=True, ator="renato", nota="ok")
    _planejar(repo, unit, _t("arb", role="arbitro"))
    arb = repo.tarefa_por_ref(unit["id"], "arb")
    with pytest.raises(orq.DecisaoInvalida, match="ator_invalido"):
        orq.decidir(repo, task["id"], aceitar=True, ator=f"tarefa:{arb['id']}",
                    nota="árbitro ainda não aceito")
    orq.pegar(repo, unit["id"], "w1", teto=TETO)
    repo.transicionar_tarefa(arb["id"], ("em_execucao",), "aceita",
                             "human:renato", "teste")
    got = orq.decidir(repo, task["id"], aceitar=True,
                      ator=f"tarefa:{arb['id']}", nota="mantido com trecho")
    assert got["status"] == "aceita"
    assert repo.transicoes_da_tarefa(task["id"])[-1]["actor"] == \
        f"tarefa:{arb['id']}"


def test_arbitro_nao_substitui_aceite_do_operador(repo, unit):
    _planejar(repo, unit, _t("pq", role="pesquisador"),
              _t("arb", role="arbitro", prio=2))
    task, _, _ = _rodar(repo, unit, saida={
        "fonte": "x", "encontrados": [], "busca_negativa": [],
        "pedidos_de_captura": []})
    arb, run = orq.pegar(repo, unit["id"], "w1", teto=TETO)
    repo.transicionar_tarefa(arb["id"], ("em_execucao",), "aceita",
                             "human:renato", "teste")
    with pytest.raises(orq.DecisaoInvalida, match="arbitro_nao_substitui"):
        orq.decidir(repo, task["id"], aceitar=True,
                    ator=f"tarefa:{arb['id']}", nota="x")
    got = orq.decidir(repo, task["id"], aceitar=False, ator="human:renato",
                      nota="busca negativa sem população")
    assert got["status"] == "recusada"


# --- regra 5: orçamento ------------------------------------------------------------

def test_teto_bloqueia_pendentes_e_avisa_o_operador_uma_vez(repo, unit):
    _planejar(repo, unit, _t("a", budget=1.0), _t("b", budget=1.0, prio=2),
              _t("c", deps=["b"], budget=1.0))
    repo.registrar_custo(unit["id"], "vs3", 24.0, {})
    _, run, res = _rodar(repo, unit, cost_usd=1.25, tokens_in=100,
                         tokens_out=10, model="claude-sonnet-5",
                         model_family="A")
    assert res["teto_atingido"] and res["tarefa"]["status"] == "aceita"
    assert repo.custo_acumulado(unit["id"]) == 25.25
    assert repo.run(run["id"])["cost_usd"] == 1.25
    assert _status(repo, unit) == {"a": "aceita", "b": "bloqueada",
                                   "c": "bloqueada"}
    with pytest.raises(orq.TetoAtingido):
        orq.pegar(repo, unit["id"], "w1", teto=TETO)
    abertos = repo.escalonamentos(unit["id"], abertos=True)
    assert [e["motivo"] for e in abertos] == ["orcamento"]
    with pytest.raises(orq.DecisaoInvalida):
        orq.desbloquear(repo, unit["id"], ator="process:x", teto=30.0)
    with pytest.raises(orq.TetoAtingido):
        orq.desbloquear(repo, unit["id"], ator="human:renato", teto=TETO)
    assert orq.desbloquear(repo, unit["id"], ator="human:renato",
                           teto=30.0)
    assert _status(repo, unit) == {"a": "aceita", "b": "pronta",
                                   "c": "planejada"}
    repo.responder_escalonamento(abertos[0]["id"], "elevar o teto",
                                 "human:renato")
    assert repo.escalonamentos(unit["id"], abertos=True) == []
    with pytest.raises(TransicaoInvalida):
        repo.responder_escalonamento(abertos[0]["id"], "de novo",
                                     "human:renato")


# --- regra 6: quarentena do verificador ------------------------------------------

def test_quarentena_recusa_campo_extra_e_pergunta_com_resposta():
    saida = CLAIM_SAIDA
    orq.afirmar_quarentena({"tarefa_verificada": "ex", "claim_id": 1,
                            "pergunta": "Quem é o grantor do Tract 1?",
                            "pagina": "1"}, saida)
    with pytest.raises(orq.QuarentenaViolada, match="campos_fora"):
        orq.afirmar_quarentena({"pergunta": "?", "output_json": saida}, saida)
    with pytest.raises(orq.QuarentenaViolada, match="pergunta_contem_resposta"):
        orq.afirmar_quarentena(
            {"pergunta": "O grantor é JOHN ROE, confirme."}, saida)
    with pytest.raises(orq.QuarentenaViolada, match="trecho"):
        orq.afirmar_quarentena(
            {"pergunta": "Onde está 'John Roe grants'?"},
            {"claims": [{"trecho": "John Roe grants"}]})


def test_entrada_do_verificador_passa_pela_quarentena(repo, unit):
    _planejar(repo, unit, _t("ex", role="examinador"),
              _t("v", role="verificador", deps=[],
                 entrada={"tarefa_verificada": "ex", "claim_id": 1,
                          "pergunta": "O grantor é John Roe?"}),
              _t("v2", role="verificador",
                 entrada={"tarefa_verificada": "ex", "claim_id": 1,
                          "pergunta": "Quem é o grantor?"}))
    v = repo.tarefa_por_ref(unit["id"], "v")
    with pytest.raises(orq.QuarentenaViolada, match="sem saída válida"):
        orq.entrada_do_verificador(repo, v)
    _rodar(repo, unit, saida=CLAIM_SAIDA)
    with pytest.raises(orq.QuarentenaViolada, match="pergunta_contem"):
        orq.entrada_do_verificador(repo, v)
    v2 = repo.tarefa_por_ref(unit["id"], "v2")
    assert orq.entrada_do_verificador(repo, v2)["pergunta"] == \
        "Quem é o grantor?"


# --- regra 7: versão das fichas -------------------------------------------------

def test_todo_run_registra_versao_da_funcao_e_do_pacote(repo, unit):
    _planejar(repo, unit, _t("ex", role="examinador"))
    _, run = orq.pegar(repo, unit["id"], "w1", teto=TETO)
    raiz = agentes.RAIZ_PADRAO
    assert run["role_version"] == agentes.versao(raiz / "nucleo/examinador.md")
    assert run["pack_version"] == agentes.versao(
        raiz / "pacotes" / PACOTE / "index.md")
    gravada = repo.versao_ficha(run["role_version"])
    assert gravada["name"] == "examinador" and gravada["kind"] == "Role"
    assert "Examinador" in gravada["content"]


def test_fichas_invalidas_nao_rodam(repo, unit, tmp_path):
    _planejar(repo, unit, _t("a"))
    raiz = tmp_path / "agentes"
    (raiz / "nucleo").mkdir(parents=True)
    (raiz / "index.md").write_text('---\nokf_version: "0.2"\n---\n',
                                   encoding="utf-8")
    (raiz / "nucleo" / "coordenador.md").write_text(
        "---\ntype: Role\nstatus: draft\n---\n", encoding="utf-8")
    with pytest.raises(orq.FichasInvalidas):
        orq.pegar(repo, unit["id"], "w1", teto=TETO, raiz=raiz)
    assert _status(repo, unit) == {"a": "pronta"}


def test_modo_verificacao_mapeia_e_cai_no_conservador():
    assert orq.modo_verificacao("obrigatoria") == "obrigatoria"
    assert orq.modo_verificacao("nao") == "nenhuma"
    assert orq.modo_verificacao("obrigatoria_e_operador") == \
        "obrigatoria_e_operador"
    for v in ("amostral", "gate_de_captura", "operador_em_material", "", None):
        assert orq.modo_verificacao(v) == "operador"


def test_saida_do_coordenador_nunca_e_aceita_sem_o_operador(repo, unit):
    """A ficha do Coordenador diz `verifica: nao`; ainda assim um grafo de
    tarefas espera o operador (regra de código, não de ficha)."""
    _planejar(repo, unit, _t("co", role="coordenador"))
    _, _, res = _rodar(repo, unit, saida={"tarefas": []})
    assert res["tarefa"]["verificacao"] == "nenhuma"
    assert res["tarefa"]["status"] == "aguardando_operador"
