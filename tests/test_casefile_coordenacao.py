"""Etapa D (corrigida): Coordenador PROPÕE o grafo; o operador aprova.
Replay com cliente roteirizado (sem modelo pago), fake + Postgres.
A cobertura é conferência de IDs e estados das pesquisas citadas pelo
próprio Coordenador — nunca julgamento de que a tarefa resolve a pesquisa."""
import hashlib

import pytest

from src.casefile import (cli, coordenacao as co, orquestracao as orq,
                          project_profile, worker as wk)
from src.casefile.orquestracao_repo import TransicaoInvalida
from tests.helpers_casefile import (ClientRoteirizado, RepoFake, Texto, Use,
                                    conectar_pg_ou_skip, unit_de_teste)

TETO = 25.0
PACOTE = "title-texas-oil-gas-dd"
SHA = "ef" * 32


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


def _montar(repo, pasta, aprovar=True):
    """Unit com plano v1 (3 pesquisas: 2 abertas, 1 cancelada), uma pesquisa
    posterior de outra sessão, uma pergunta ao operador, um claim e um
    documento visto só na entrega."""
    unit = unit_de_teste(repo, pasta)
    s1 = repo.abrir_sessao(unit["id"], "planejar", "m")
    longo = "o que 1 " + "x" * 1500
    ids = [repo.inserir_pesquisa(unit["id"], f"pesquisa {n}",
                                 longo if n == 1 else f"o que {n}",
                                 "cartorio", "vol/pg", s1, [])
           for n in (1, 2, 3)]
    repo.marcar_pesquisa(ids[2], "cancelada")
    plano = repo.propor_plano(unit["id"], "# plano v1", {"pesquisas": 3}, s1)
    if aprovar:
        repo.decidir_plano(plano["id"], "aprovado", "human:renato", "ok")
    s2 = repo.abrir_sessao(unit["id"], "coletar", "m")
    posterior = repo.inserir_pesquisa(unit["id"], "pesquisa 4", "o que 4",
                                      "acervo", "leitura", s2, [])
    pergunta = repo.registrar_pergunta_vs2(unit["id"], "Série X conta acres?")
    fid = repo.registrar_source_file(SHA, 10)
    repo.registrar_sighting(fid, unit["id"], str(pasta / "dpu.pdf"), "",
                            "dpu.pdf", "unit_files")
    fid2 = repo.registrar_source_file("12" * 32, 10)
    repo.registrar_sighting(fid2, unit["id"], str(pasta / "entrega.pdf"), "",
                            "gabarito entrega.pdf", "entrega")
    claim = repo.inserir_claim(unit["id"], "lease_in_unit", "Lease 0220604/002",
                               {"lease_no": "0220604/002", "lessor": "Roe"},
                               SHA, "3", "T" * 900, "alta", "alta", s1)
    return {"unit": unit, "p": ids, "posterior": posterior,
            "pergunta": pergunta, "claim": claim}


@pytest.fixture
def caso(repo, tmp_path):
    return _montar(repo, tmp_path / "SINTETICA A UNIT")


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
        _t("ex-1", "examinador", [f"pesquisa:{p1}",
                                  f"decisao:{caso['pergunta']}"],
           deps=["pq-1"]),
    ]}


def _entrega(saida, uid="u1"):
    return [Use("entregar_saida", {"saida": saida}, id=uid)]


def _semear(repo, caso, orcamento=2.0):
    return co.semear_coordenador(repo, caso["unit"], pacote=PACOTE, teto=TETO,
                                 orcamento_usd=orcamento,
                                 criado_por="human:renato")


def _propor(repo, caso, plano=None):
    """Semeia e roda o Coordenador (roteiro) até a proposta."""
    _semear(repo, caso)
    cliente = Cliente([_entrega(plano or _plano(caso)), [Texto("ok")]])
    return wk.executar_uma(repo, caso["unit"]["id"], "w1", teto=TETO,
                           client=cliente)


# --- 1. cobertura antes da gravação --------------------------------------------

def _erros(repo, caso, plano):
    return orq.checar_plano(repo, caso["unit"]["id"], plano, teto=TETO,
                            pacote=PACOTE) or \
        co.checar_proposta(repo, caso["unit"]["id"], plano, teto=TETO,
                           pacote=PACOTE)


def test_proposta_completa_passa(repo, caso):
    assert _erros(repo, caso, _plano(caso)) == []


def test_plano_vazio_nao_cobre_nada(repo, caso):
    [erro] = _erros(repo, caso, {"tarefas": []})
    p1, p2, _ = caso["p"]
    assert erro.startswith("cobertura_incompleta: 2 de 2")
    assert f"pesquisa:{p1}" in erro and f"pesquisa:{p2}" in erro


def test_cobertura_parcial_e_recusada(repo, caso):
    plano = _plano(caso)
    plano["tarefas"][1]["pendencias"] = [f"pesquisa:{caso['posterior']}"]
    [erro] = _erros(repo, caso, plano)
    assert erro.startswith("cobertura_incompleta: 1 de 2")
    assert f"pesquisa:{caso['p'][1]}" in erro


@pytest.mark.parametrize("citacao,codigo", [
    ("pesquisa:999", "pendencia_inexistente"),
    ("decisao:999", "pendencia_inexistente"),
    ("claim:1", "pendencia_inexistente"),
])
def test_pendencia_inexistente_e_recusada(repo, caso, citacao, codigo):
    plano = _plano(caso)
    plano["tarefas"][0]["pendencias"].append(citacao)
    erros = _erros(repo, caso, plano)
    assert len(erros) == 1 and erros[0].startswith(codigo)
    assert citacao in erros[0]


def test_pesquisa_cancelada_citada_e_recusada(repo, caso):
    plano = _plano(caso)
    plano["tarefas"][0]["pendencias"].append(f"pesquisa:{caso['p'][2]}")
    [erro] = _erros(repo, caso, plano)
    assert erro.startswith("pendencia_cancelada")


def test_sem_plano_aprovado_nao_ha_proposta(repo, tmp_path):
    caso = _montar(repo, tmp_path / "SEM PLANO", aprovar=False)
    assert co.checar_proposta(repo, caso["unit"]["id"], _plano(caso),
                              teto=TETO, pacote=PACOTE) == \
        [f"sem_plano_aprovado: unit {caso['unit']['id']}"]
    with pytest.raises(ValueError, match="sem_plano_aprovado"):
        _semear(repo, caso)


def test_erro_de_cobertura_volta_ao_modelo_no_mesmo_run(repo, caso):
    _semear(repo, caso)
    parcial = _plano(caso)
    parcial["tarefas"] = parcial["tarefas"][:1]
    cliente = Cliente([_entrega(parcial), _entrega(_plano(caso), "u2"),
                       [Texto("ok")]])
    r = wk.executar_uma(repo, caso["unit"]["id"], "w1", teto=TETO,
                        client=cliente)
    volta = cliente.chamadas[1]["messages"][-1]["content"][0]["content"]
    assert "cobertura_incompleta" in volta
    assert r["erros"] == [] and r["entregas"] == 2 and r["proposta_id"]


def test_proposta_que_nunca_cobre_nao_vira_proposta(repo, caso):
    _semear(repo, caso)
    cliente = Cliente([_entrega({"tarefas": []}), [Texto("desisto")]])
    r = wk.executar_uma(repo, caso["unit"]["id"], "w1", teto=TETO,
                        client=cliente)
    assert r["proposta_id"] is None and r["tarefa"]["status"] == "pronta"
    assert any("cobertura_incompleta" in e for e in r["erros"])
    assert repo.propostas(caso["unit"]["id"]) == []


# --- 2. proposta e aceite humano ------------------------------------------------

def test_saida_valida_vira_proposta_sem_criar_tarefas(repo, caso):
    r = _propor(repo, caso)
    uid = caso["unit"]["id"]
    assert r["tarefa"]["status"] == "aguardando_operador"
    assert [t["ref"] for t in repo.tarefas(uid)] == ["coordenador-1"]
    [p] = repo.propostas(uid)
    assert p["id"] == r["proposta_id"] and p["status"] == "proposta"
    assert p["task_id"] == r["tarefa"]["id"] and p["run_id"] == r["run_id"]
    assert p["coverage"]["completa"] and p["coverage"]["alvos"] == 2
    assert p["targets"]["alvos"] == [f"pesquisa:{i}" for i in caso["p"][:2]]
    assert p["decided_by"] == "" and p["decided_at"] is None
    # nada executável antes da aprovação
    assert wk.executar_uma(repo, uid, "w1", teto=TETO,
                           client=Cliente([])) is None


def test_aprovacao_explicita_cria_tarefas_e_registra_decisao(repo, caso):
    r = _propor(repo, caso)
    pid, uid = r["proposta_id"], caso["unit"]["id"]
    with pytest.raises(orq.DecisaoInvalida, match="ator_invalido"):
        co.aprovar_proposta(repo, pid, ator="process:auto", nota="x",
                            teto=TETO)
    with pytest.raises(orq.DecisaoInvalida, match="nota_ausente"):
        co.aprovar_proposta(repo, pid, ator="human:renato", nota=" ",
                            teto=TETO)
    assert [t["ref"] for t in repo.tarefas(uid)] == ["coordenador-1"]
    criadas = co.aprovar_proposta(repo, pid, ator="human:renato",
                                  nota="grafo conferido", teto=TETO)
    assert {t["ref"]: t["status"] for t in criadas} == {
        "pq-1": "pronta", "pq-2": "pronta", "ex-1": "planejada"}
    p = repo.proposta(pid)
    assert p["status"] == "aprovada" and p["decided_by"] == "human:renato"
    assert p["decided_at"] is not None and p["decision_note"] == \
        "grafo conferido"
    assert sorted(p["applied_task_ids"]) == sorted(t["id"] for t in criadas)
    assert criadas[0]["created_by"] == f"coordenador/tarefa:{p['task_id']}"
    coord = repo.tarefa(p["task_id"])
    assert coord["status"] == "aceita"
    assert repo.transicoes_da_tarefa(coord["id"])[-1]["actor"] == \
        "human:renato"
    with pytest.raises(TransicaoInvalida):
        co.aprovar_proposta(repo, pid, ator="human:renato", nota="de novo",
                            teto=TETO)


def test_recusa_preserva_a_proposta(repo, caso):
    r = _propor(repo, caso)
    pid, uid = r["proposta_id"], caso["unit"]["id"]
    co.recusar_proposta(repo, pid, ator="human:renato",
                        nota="pq-2 mistura duas sentadas")
    p = repo.proposta(pid)
    assert p["status"] == "recusada" and p["plan"] == _plano(caso)
    assert p["decided_by"] == "human:renato" and p["decided_at"]
    assert repo.tarefa(p["task_id"])["status"] == "recusada"
    assert [t["ref"] for t in repo.tarefas(uid)] == ["coordenador-1"]
    with pytest.raises(TransicaoInvalida):
        co.aprovar_proposta(repo, pid, ator="human:renato", nota="x",
                            teto=TETO)


def test_aprovacao_recheca_o_estado_atual(repo, caso):
    r = _propor(repo, caso)
    repo.marcar_pesquisa(caso["p"][1], "cancelada")   # mudou depois
    with pytest.raises(co.PropostaInvalida, match="pendencia_cancelada"):
        co.aprovar_proposta(repo, r["proposta_id"], ator="human:renato",
                            nota="ok", teto=TETO)
    assert repo.proposta(r["proposta_id"])["status"] == "proposta"
    assert [t["ref"] for t in repo.tarefas(caso["unit"]["id"])] == \
        ["coordenador-1"]


def test_nova_proposta_substitui_a_aberta_sem_apagar(repo, caso):
    r1 = _propor(repo, caso)
    co.semear_coordenador(repo, caso["unit"], pacote=PACOTE, teto=TETO,
                          orcamento_usd=2.0, criado_por="human:renato",
                          ref="coordenador-2")
    cliente = Cliente([_entrega(_plano(caso)), [Texto("ok")]])
    r2 = wk.executar_uma(repo, caso["unit"]["id"], "w1", teto=TETO,
                         client=cliente)
    assert [p["status"] for p in repo.propostas(caso["unit"]["id"])] == \
        ["substituida", "proposta"]
    with pytest.raises(TransicaoInvalida):
        co.aprovar_proposta(repo, r1["proposta_id"], ator="human:renato",
                            nota="velha", teto=TETO)
    assert r2["proposta_id"] != r1["proposta_id"]


# --- 3. entrada honesta ---------------------------------------------------------

def test_entrada_declara_o_que_e_integral_resumo_e_truncado(repo, caso):
    unit = caso["unit"]
    repo.registrar_custo(unit["id"], "vs1", 4.0, {})
    longa = repo.registrar_pergunta_vs2(unit["id"], "Q" * 5000)
    e = co.entrada_do_coordenador(repo, unit, teto=TETO)
    m = e["manifesto"]
    assert "somente_contagem" in m and "consultar_pela_ferramenta" in m
    assert m["truncado"]["decisoes_truncadas"] == [f"decisao:{longa}"]
    assert "ler_case_file" in m["consultar_pela_ferramenta"]
    # pendências abertas vão INTEGRAIS (a 1 tem 1.508 caracteres)
    p1 = next(p for p in e["pendencias_abertas"]
              if p["id"] == f"pesquisa:{caso['p'][0]}")
    assert len(p1["o_que"]) == 1508
    pi = e["plano_de_investigacao"]
    assert pi["pesquisas_abertas_a_cobrir"] == [
        f"pesquisa:{i}" for i in caso["p"][:2]]
    assert pi["pesquisas_canceladas_nao_citar"] == [f"pesquisa:{caso['p'][2]}"]
    assert e["orcamento_usd"]["saldo_para_novas_tarefas"] == 21.0
    assert e["censo"] and e["claims_ativos_por_tipo"] == {"lease_in_unit": 1}
    com_reserva = co.entrada_do_coordenador(repo, unit, teto=TETO,
                                            reserva_coordenador=1.5)
    assert com_reserva["orcamento_usd"]["saldo_para_novas_tarefas"] == 19.5


def test_saldo_declarado_ao_coordenador_e_o_que_a_checagem_aceita(repo,
                                                                   caso):
    """O saldo que a entrada anuncia cabe exatamente na checagem do plano
    (a tarefa do Coordenador já conta como comprometida)."""
    t = _semear(repo, caso, orcamento=2.0)
    saldo = t["input_json"]["orcamento_usd"]["saldo_para_novas_tarefas"]
    assert saldo == TETO - 2.0
    plano = _plano(caso)
    for x in plano["tarefas"]:
        x["budget_usd"] = int(saldo / 3 * 10_000) / 10_000   # para baixo
    orq.pegar(repo, caso["unit"]["id"], "w1", teto=TETO)   # em execução
    assert co.checar_proposta(repo, caso["unit"]["id"], plano, teto=TETO,
                              pacote=PACOTE) == []
    plano["tarefas"][0]["budget_usd"] += 0.01
    [erro] = co.checar_proposta(repo, caso["unit"]["id"], plano, teto=TETO,
                                pacote=PACOTE)
    assert erro.startswith("orcamento_do_plano_excede_saldo")


def test_ler_case_file_consulta_com_proveniencia_e_quarentena(repo, caso):
    ler = co.ler_case_file(repo, caso["unit"]["id"])
    [c] = ler("claims")["itens"]
    assert c["id"] == f"claim:{caso['claim']}"
    assert c["documento"] == f"sha256:{SHA}" and c["pagina"] == "3"
    assert "truncado" in c["trecho"] and len(c["trecho"]) < 500
    assert ler("claims", tipo="tract")["total"] == 0
    assert ler("claims", filtro="0220604")["total"] == 1
    docs = ler("documentos")
    assert [d["nome"] for d in docs["itens"]] == ["dpu.pdf"]  # entrega fora
    pesq = ler("pesquisas", limite=2)
    assert pesq["total"] == 4 and pesq["proximo_offset"] == 2
    assert {p["status"] for p in ler("pesquisas")["itens"]} == \
        {"aberta", "cancelada"}
    assert ler("pesquisas", offset=2, limite=2)["proximo_offset"] is None
    assert ler("decisoes")["itens"][0]["id"] == f"decisao:{caso['pergunta']}"
    with pytest.raises(ValueError, match="secao_desconhecida"):
        ler("gabarito")


def test_coordenador_consulta_o_case_file_no_run(repo, caso):
    _semear(repo, caso)
    cliente = Cliente([
        [Use("ler_case_file", {"secao": "claims"})],
        _entrega(_plano(caso), "u2"), [Texto("ok")]])
    r = wk.executar_uma(repo, caso["unit"]["id"], "w1", teto=TETO,
                        client=cliente)
    nomes = [t["name"] for t in cliente.chamadas[0]["tools"]]
    assert nomes == ["entregar_saida", "ler_case_file"]
    assert "ler_case_file" not in r["indisponiveis"]
    volta = cliente.chamadas[1]["messages"][-1]["content"][0]["content"]
    assert f"claim:{caso['claim']}" in volta and f"sha256:{SHA}" in volta
    assert r["proposta_id"]


# --- 5. perfil Cibola: nada contorna o bloqueio ---------------------------------

@pytest.fixture
def cibola(repo, tmp_path):
    root = tmp_path / "Cibola"
    root.mkdir()
    fonte = root / "metodo.txt"
    fonte.write_text("metodologia sintetica", encoding="utf-8")
    caso = _montar(repo, root / "TRACT-1")
    perfil = dict(schema=1, name="cibola sintetico", work_type="surface_title",
                  project_root=str(root), planning_system="Sistema surface",
                  planning_task="Planejar o tract de surface",
                  sources=[dict(path=str(fonte), sha256=hashlib.sha256(
                      fonte.read_bytes()).hexdigest())])
    project_profile.configure(repo, caso["unit"], perfil, "fixture", "teste")
    return caso


def test_cibola_coordenar_e_trabalhar_recusados(repo, cibola, monkeypatch):
    unit = cibola["unit"]
    estado = repo.estado_da_unit(unit["id"])
    monkeypatch.setenv("CASEFILE_TETO_UNIT_USD", str(TETO))
    with pytest.raises(ValueError, match="surface_title_stage_not_ready:coordenar"):
        _semear(repo, cibola)
    with pytest.raises(ValueError, match="surface_title_stage_not_ready:coordenar"):
        cli.cmd_coordenar(unit["canonical_name"], "title-texas-surface", 2.0,
                          repo=repo)
    with pytest.raises(ValueError, match="surface_title_stage_not_ready:trabalhar"):
        cli.cmd_trabalhar(unit["canonical_name"], 1, repo=repo,
                          client=Cliente([]))
    with pytest.raises(ValueError, match="surface_title_stage_not_ready:trabalhar"):
        wk.executar_uma(repo, unit["id"], "w1", teto=TETO, client=Cliente([]))
    assert repo.tarefas(unit["id"]) == []
    assert repo.estado_da_unit(unit["id"]) == estado


def test_cibola_tarefa_semeada_antes_do_perfil_nao_roda(repo, tmp_path):
    """Perfil configurado depois: nem worker nem aprovação passam."""
    caso = _montar(repo, tmp_path / "Cibola" / "TRACT-2")
    r = _propor(repo, caso)
    fonte = tmp_path / "Cibola" / "m.txt"
    fonte.parent.mkdir(parents=True, exist_ok=True)
    fonte.write_text("m", encoding="utf-8")
    project_profile.configure(repo, caso["unit"], dict(
        schema=1, name="c", work_type="surface_title",
        project_root=str(tmp_path / "Cibola"), planning_system="s",
        planning_task="t", sources=[dict(path=str(fonte), sha256=hashlib.sha256(
            fonte.read_bytes()).hexdigest())]), "fixture", "teste")
    with pytest.raises(ValueError, match="surface_title_stage_not_ready"):
        co.aprovar_proposta(repo, r["proposta_id"], ator="human:renato",
                            nota="ok", teto=TETO)
    assert repo.proposta(r["proposta_id"])["status"] == "proposta"


@pytest.mark.parametrize("comando", ["cmd_coletar", "cmd_reconciliar",
                                     "cmd_examinar", "cmd_avancar"])
def test_cibola_coleta_exame_entrega_seguem_recusados(repo, cibola, comando):
    unit = cibola["unit"]
    with pytest.raises(ValueError, match="surface_title_stage_not_ready"):
        getattr(cli, comando)(unit["canonical_name"], repo=repo)


def test_cibola_planejamento_suportado_continua_permitido(repo, cibola):
    unit = cibola["unit"]
    project_profile.require_supported(repo, unit, "planning")   # não recusa
    task = cli._task_planejar(repo, unit, {}, {"conteudos": 0})
    assert "Planejar o tract de surface" in task
    assert "Lease-to-Well" not in task                            # sem Emirates


# --- CLI ------------------------------------------------------------------------

def test_cli_proposta_aprovar_recusar_cobertura(repo, caso, capsys,
                                                monkeypatch):
    unit = caso["unit"]
    nome = unit["canonical_name"]
    monkeypatch.setenv("CASEFILE_TETO_UNIT_USD", str(TETO))
    cli.cmd_coordenar(nome, PACOTE, 2.0, repo=repo)
    assert "PROPOSTA" in capsys.readouterr().out
    cli.cmd_trabalhar(nome, 1, repo=repo,
                      client=Cliente([_entrega(_plano(caso)), [Texto("ok")]]))
    saida = capsys.readouterr().out
    assert "PROPOSTA #1 aguarda aprovação" in saida
    cli.cmd_cobertura(nome, None, repo=repo, proposta=1)
    saida = capsys.readouterr().out
    assert "proposta #1" in saida and "2/2" in saida and "COMPLETA" in saida
    cli.cmd_cobertura(nome, None, repo=repo)
    assert "0/2" in capsys.readouterr().out              # nada criado ainda
    cli.cmd_decidir_proposta(1, True, "renato", "grafo conferido", repo=repo)
    assert "APROVADA por human:renato: 3 tarefa(s)" in capsys.readouterr().out
    cli.cmd_propostas(nome, repo=repo)
    assert "aprovada" in capsys.readouterr().out
    cli.cmd_cobertura(nome, None, repo=repo)
    assert "2/2" in capsys.readouterr().out


# --- atomicidade da decisão (falhas injetadas) ------------------------------------

class Falha(RuntimeError):
    pass


def _estado(repo, uid, pid):
    p = repo.proposta(pid)
    return {"tarefas": sorted((t["ref"], t["status"])
                              for t in repo.tarefas(uid)),
            "proposta": {k: p[k] for k in ("status", "decided_by",
                                           "decided_at", "decision_note",
                                           "applied_task_ids")},
            "transicoes": {t["ref"]: len(repo.transicoes_da_tarefa(t["id"]))
                           for t in repo.tarefas(uid)},
            "propostas": [q["status"] for q in repo.propostas(uid)]}


def _injetar(repo, monkeypatch, ponto):
    def boom(*a, **k):
        raise Falha(f"falha injetada em {ponto}")
    if ponto == "decidir":
        monkeypatch.setattr(orq, "decidir", boom)
    elif ponto in ("criar_tarefas", "recusar_proposta"):
        original = getattr(repo, ponto)

        def depois(*a, **k):                 # a operação ACONTECE, depois falha
            original(*a, **k)
            raise Falha(f"falha injetada depois de {ponto}")
        monkeypatch.setattr(repo, ponto, depois)
    else:
        monkeypatch.setattr(repo, ponto, boom)


@pytest.mark.parametrize("ponto", ["criar_tarefas", "promover_prontas",
                                   "decidir"])
def test_aprovacao_com_falha_injetada_nao_deixa_estado_parcial(
        repo, caso, monkeypatch, ponto):
    r = _propor(repo, caso)
    pid, uid = r["proposta_id"], caso["unit"]["id"]
    antes = _estado(repo, uid, pid)
    _injetar(repo, monkeypatch, ponto)
    with pytest.raises(Falha):
        co.aprovar_proposta(repo, pid, ator="human:renato", nota="ok",
                            teto=TETO)
    depois = _estado(repo, uid, pid)
    assert depois == antes
    assert depois["proposta"]["status"] == "proposta"
    assert depois["tarefas"] == [("coordenador-1", "aguardando_operador")]
    monkeypatch.undo()
    criadas = co.aprovar_proposta(repo, pid, ator="human:renato", nota="ok",
                                  teto=TETO)
    assert len(criadas) == 3 and repo.proposta(pid)["status"] == "aprovada"


@pytest.mark.parametrize("ponto", ["recusar_proposta", "decidir"])
def test_recusa_com_falha_injetada_nao_deixa_estado_parcial(
        repo, caso, monkeypatch, ponto):
    r = _propor(repo, caso)
    pid, uid = r["proposta_id"], caso["unit"]["id"]
    antes = _estado(repo, uid, pid)
    _injetar(repo, monkeypatch, ponto)
    with pytest.raises(Falha):
        co.recusar_proposta(repo, pid, ator="human:renato", nota="não")
    assert _estado(repo, uid, pid) == antes
    monkeypatch.undo()
    co.recusar_proposta(repo, pid, ator="human:renato", nota="não")
    assert repo.proposta(pid)["status"] == "recusada"
    assert repo.tarefa(r["tarefa"]["id"])["status"] == "recusada"


def test_decisao_exige_coordenador_aguardando(repo, caso):
    r = _propor(repo, caso)
    repo.transicionar_tarefa(r["tarefa"]["id"], ("aguardando_operador",),
                             "recusada", "human:renato", "fora do fluxo")
    with pytest.raises(TransicaoInvalida, match="não aguarda o operador"):
        co.aprovar_proposta(repo, r["proposta_id"], ator="human:renato",
                            nota="ok", teto=TETO)
    assert repo.proposta(r["proposta_id"])["status"] == "proposta"
    assert [t["ref"] for t in repo.tarefas(caso["unit"]["id"])] == \
        ["coordenador-1"]
