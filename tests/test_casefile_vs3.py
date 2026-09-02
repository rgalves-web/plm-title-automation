"""VS3 — encanamento: verificação cega, grafo/posições, reconciliação."""
from __future__ import annotations

import json

import pytest

from src.casefile import exame_vs3, verificador, vs3_entregaveis
from tests.helpers_casefile import RepoFake, unit_de_teste

SHA_A = "a" * 64


def _unit(tmp_path):
    repo = RepoFake()
    pasta = tmp_path / "U UNIT"
    (pasta / "FILES").mkdir(parents=True)
    unit = unit_de_teste(repo, pasta, "U UNIT")
    repo.registrar_source_file(SHA_A, 9)
    repo.registrar_sighting(1, unit["id"], "c", "", "files/doc.pdf",
                            "unit_files")
    return repo, unit, pasta


def _claim(repo, unit, tipo="fact", entidade="x", valor=None):
    sess = repo.abrir_sessao(unit["id"], "exame.vs3", "opus")
    return repo.inserir_claim(unit["id"], tipo, entidade, valor or {},
                              SHA_A, "1", "trecho", "alta", "alta", sess)


# --- normalização e comparação ----------------------------------------------

def test_normalizar_datas_e_strings():
    assert verificador.normalizar("2010-03-03") == "2010-03-03"
    assert verificador.normalizar("03/03/2010") == "2010-03-03"
    assert verificador.normalizar(" A-811 ") == "a-811"
    got = verificador.comparar("2010-03-03", "03/03/2010")
    assert got["igual"]
    assert not verificador.comparar("611/526", "611/999")["igual"]


# --- verificação cega -------------------------------------------------------

def test_verificar_pergunta_e_cega_e_compara_deterministicamente(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    cid = _claim(repo, unit, valor={"certification_date": "2010-03-03"})
    prompts = []

    def chamar_fake(prompt, png=None):
        prompts.append(prompt)
        class U:  # usage
            prompt_tokens, completion_tokens = 1000, 50
        return ('{"valor": "March 3, 2010 -> 2010-03-03", '
                '"trecho": "as of March 3, 2010", '
                '"evidencia_suficiente": true}', U())

    custo = verificador._CustoB()
    got = verificador.verificar_pergunta(
        repo=repo, claim=repo.claim(cid), pergunta="Qual a data as of?",
        campo_do_claim="2010-03-03", evidencia_texto="as of March 3, 2010",
        chamar=chamar_fake, custo=custo)
    assert got["verdict"] == "concordancia"
    # CEGO: o prompt nunca contem o valor do examinador
    assert "2010-03-03" not in prompts[0]
    assert custo.total > 0
    v = repo.verificacoes_do_claim(cid)[0]
    assert v["verdict"] == "concordancia"


def test_verificar_divergencia_e_insuficiente(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    cid = _claim(repo, unit, valor={"certification_date": "2010-03-03"})

    def discorda(prompt, png=None):
        class U:
            prompt_tokens, completion_tokens = 10, 10
        return ('{"valor": "2011-01-01", "trecho": "x", '
                '"evidencia_suficiente": true}', U())

    custo = verificador._CustoB()
    got = verificador.verificar_pergunta(
        repo=repo, claim=repo.claim(cid), pergunta="data?",
        campo_do_claim="2010-03-03", evidencia_texto="t",
        chamar=discorda, custo=custo)
    assert got["verdict"] == "divergencia"        # fica ABERTA

    def sem_evidencia(prompt, png=None):
        class U:
            prompt_tokens, completion_tokens = 10, 10
        return '{"valor": "", "evidencia_suficiente": false}', U()

    got2 = verificador.verificar_pergunta(
        repo=repo, claim=repo.claim(cid), pergunta="data?",
        campo_do_claim="2010-03-03", evidencia_texto="t",
        chamar=sem_evidencia, custo=custo)
    assert got2["verdict"] == "evidencia_insuficiente"


def test_lote_exhibit_a_transcricao_independente(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    c1 = _claim(repo, unit, "lease_in_unit", "lease 0111111/001",
                {"lease_no": "0111111/001", "lessor": "FULANO",
                 "vol": "100", "page": "1"})
    c2 = _claim(repo, unit, "lease_in_unit", "lease 0111111/002",
                {"lease_no": "0111111/002", "lessor": "BELTRANO",
                 "vol": "200", "page": "2"})

    def transcreve(prompt, png=None):
        class U:
            prompt_tokens, completion_tokens = 500, 200
        return (json.dumps({"linhas": [
            {"lease_no": "0111111-001", "lessor": "Fulano",
             "vol": "100", "page": "1"},
            {"lease_no": "0111111-002", "lessor": "OUTRO NOME",
             "vol": "200", "page": "2"}]}), U())

    custo = verificador._CustoB()
    got = verificador.verificar_lote_exhibit_a(
        repo=repo, unit=unit,
        claims_lease=[repo.claim(c1), repo.claim(c2)],
        pngs=[b"png"], chamar=transcreve, custo=custo)
    assert got == {"concordancia": 1, "divergencia": 1,
                   "evidencia_insuficiente": 0}
    assert repo.verificacoes_do_claim(c2)[0]["verdict"] == "divergencia"


# --- ferramentas VS3 --------------------------------------------------------

def test_propor_grafo_valida_claim_e_documento(tmp_path):
    repo, unit, pasta = _unit(tmp_path)
    cid = _claim(repo, unit)
    ref = {"id": None}
    dispatch = exame_vs3.montar_dispatch_vs3(
        base={}, repo=repo, unit=unit, pasta=pasta, session_ref=ref)
    got = dispatch["propor_grafo"](
        nodes=[{"id": "t1", "tipo": "tract", "rotulo": "Tract 1"},
               {"id": "l1", "tipo": "lease", "rotulo": "lease 1"}],
        edges=[{"de": "t1", "para": "l1", "tipo": "baseline",
                "claim_id": cid, "documento": "files/doc.pdf"},
               {"de": "t1", "para": "l1", "tipo": "x",
                "claim_id": 999, "documento": "files/doc.pdf"}])
    assert got["aceito"] and got["edges"] == 1
    assert got["rejeitadas"][0]["erros"] == ["claim 999 nao e desta unit"]
    grafo = json.loads((pasta / "_casefile" / "CHAIN_GRAPH_VS3.json")
                       .read_text(encoding="utf-8"))
    assert len(grafo["edges"]) == 1


def test_classificar_populacao_e_claims_ddr(tmp_path):
    repo, unit, pasta = _unit(tmp_path)
    cid = _claim(repo, unit)
    ref = {"id": None}
    dispatch = exame_vs3.montar_dispatch_vs3(
        base={}, repo=repo, unit=unit, pasta=pasta, session_ref=ref)
    got = dispatch["classificar_populacao"](itens=[
        {"item": "tract 1", "classificacao": "comprovada",
         "claim_ids": [cid]},
        {"item": "ruim", "classificacao": "comprovada",
         "claim_ids": [777]}])
    assert got["aceitos"] == 1 and got["rejeitados"]
    assert repo.posicoes(unit["id"])[0]["classification"] == "comprovada"
    got2 = dispatch["propor_claims_ddr"](itens=[
        {"claim_id": cid, "celulas_candidatas": ["Lease Review!R17"],
         "limitacoes": "simulacao"}])
    assert got2["aceitos"] == 1
    assert repo.claim(cid)["ddr_candidates"] == ["Lease Review!R17"]


# --- reconciliação e entregáveis --------------------------------------------

def test_reconciliar_e_gerar_todos(tmp_path):
    repo, unit, pasta = _unit(tmp_path)
    cid = _claim(repo, unit, "fact", "data de corte do exame",
                 {"data": "2026-06-16", "fonte": "XREF 06-16-2026",
                  "tipo_resultado": "fato_documental"})
    repo.gravar_posicao(unit["id"], "tract 1", "comprovada", [cid], "", 1)
    repo.registrar_verificacao(cid, "q", "concordancia", "b", {}, {}, 0.01)
    repo.atualizar_claim_ddr(unit["id"], cid, ["Summary!B2"], "")
    rec = vs3_entregaveis.reconciliar(repo, unit)
    assert rec["claims_com_verificacao"] == 1
    assert rec["vereditos"]["concordancia"] == 1
    assert rec["claims_ddr_prontos"] == 1
    caminhos = vs3_entregaveis.gerar_todos(repo, unit, pasta)
    assert set(caminhos) == {"title_examination", "claims_ready",
                             "unresolved", "coverage", "cost"}
    ready = json.loads(caminhos["claims_ready"].read_text(encoding="utf-8"))
    assert ready["itens"][0]["claim_id"] == cid
    assert ready["itens"][0]["verificacao_independente"][0]["verdict"] == \
        "concordancia"
    corpo = caminhos["title_examination"].read_text(encoding="utf-8")
    assert "2026-06-16" in corpo and "comprovada" in corpo


def test_preflight_reprova_sem_orcamento(tmp_path, monkeypatch):
    from src.casefile import cli
    repo, unit, pasta = _unit(tmp_path)
    monkeypatch.setattr(cli, "ULTIMA", tmp_path / "ultima")
    monkeypatch.setenv("CASEFILE_TETO_UNIT_USD", "25")
    repo.transicionar(unit["id"], "INDICADA", "EXAMINANDO", "atalho", "t")
    repo.registrar_custo(unit["id"], "modelo", 22.0, {})   # restante $3
    with pytest.raises(SystemExit, match="PREFLIGHT REPROVADO"):
        cli.cmd_examinar("U UNIT", repo=repo)
    assert repo.sessoes_da_unit(unit["id"]) == []   # nenhuma chamada
