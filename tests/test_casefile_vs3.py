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
                   "evidencia_insuficiente": 0, "nao_verificavel": 0}
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
    assert rec["verificacao_tentada"] == 1
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


def test_identidade_da_evidencia_e_afirmada_antes_da_chamada(tmp_path):
    """Veredito CTO item 1: sha/página renderizados = os do claim, senão
    NENHUMA chamada acontece."""
    repo, unit, _ = _unit(tmp_path)
    cid = _claim(repo, unit, valor={"certification_date": "2010-03-03"})
    claim = repo.claim(cid)

    def nunca_chamar(*a, **k):
        raise AssertionError("chamada feita com evidencia errada!")

    custo = verificador._CustoB()
    with pytest.raises(verificador.EvidenciaNaoCorresponde,
                       match="documento renderizado"):
        verificador.verificar_pergunta(
            repo=repo, claim=claim, pergunta="q", campo_do_claim="x",
            evidencia_texto="t", sha_doc_renderizado="f" * 64,
            pagina_renderizada="1", chamar=nunca_chamar, custo=custo)
    with pytest.raises(verificador.EvidenciaNaoCorresponde,
                       match="pagina renderizada"):
        verificador.verificar_pergunta(
            repo=repo, claim=claim, pergunta="q", campo_do_claim="x",
            evidencia_texto="t", sha_doc_renderizado=SHA_A,
            pagina_renderizada="9", chamar=nunca_chamar, custo=custo)
    assert repo.verificacoes_do_claim(cid) == []


def test_rastreio_completo_gravado_na_verificacao(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    cid = _claim(repo, unit, valor={"certification_date": "2010-03-03"})

    def chamar(prompt, png=None, max_tokens=4000):
        class U:
            prompt_tokens, completion_tokens = 10, 10
        return ('{"valor": "2010-03-03", "trecho": "x", '
                '"evidencia_suficiente": true}', U(),
                {"request_id": "req_abc",
                 "model_params": {"model": "gpt-x"}})

    custo = verificador._CustoB()
    verificador.verificar_pergunta(
        repo=repo, claim=repo.claim(cid), pergunta="q?",
        campo_do_claim="2010-03-03", evidencia_texto="as of 2010-03-03",
        sha_doc_renderizado=SHA_A, pagina_renderizada="1",
        chamar=chamar, custo=custo)
    v = repo.verificacoes_do_claim(cid)[0]
    assert v["source_sha256"] == SHA_A and v["page"] == "1"
    assert v["request_id"] == "req_abc"
    assert len(v["evidence_payload_sha256"]) == 64
    assert len(v["prompt_sha256"]) == 64
    assert "2010-03-03" in v["raw_response"]
    # e o valor do examinador NUNCA vaza para o prompt (hash != do payload
    # nao prova; o teste de cegueira ja cobre no test acima do modulo)


def test_invalidacao_preserva_trilha_e_sai_das_metricas(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    cid = _claim(repo, unit, valor={"x": 1})
    vid = repo.registrar_verificacao(cid, "q", "divergencia", "b", {}, {},
                                     0.0)
    repo.invalidar_verificacao(vid, "verifier_error — inspecao do operador")
    v = repo.verificacoes_do_claim(cid)[0]
    assert v["status"] == "invalidada"
    assert "verifier_error" in v["invalidation_reason"]
    rec = vs3_entregaveis.reconciliar(repo, unit)
    assert rec["verificacao_tentada"] == 0       # fora das métricas
    assert rec["vereditos"]["divergencia"] == 0  # não é divergência de título


def test_lifecycle_dos_entregaveis_partial_ate_exame_fechar(tmp_path):
    repo, unit, pasta = _unit(tmp_path)
    _claim(repo, unit, valor={"x": 1})
    caminhos = vs3_entregaveis.gerar_todos(repo, unit, pasta)
    d = repo.deliverables(unit["id"], "title_examination_vs3")[0]
    assert d["lifecycle"] == "partial"
    corpo = caminhos["title_examination"].read_text(encoding="utf-8")
    assert "STATUS: PARTIAL" in corpo


def test_regressao_596_589_evidencia_nao_contem_1272(tmp_path):
    """Regressão do caso 142 (dados REAIS): a EVIDÊNCIA ENTREGUE ao
    verificador — a página 596/589 renderizada — NÃO contém 1272. Isso
    prova mecanicamente que a verification 142 (que declarou A-1272) foi
    verifier_error, não divergência de título. Skip visível sem o Drive
    local ou sem OCR configurado."""
    import io
    import pathlib

    import fitz
    from PIL import Image

    doc = pathlib.Path(r"C:\Users\Renato\PURPLE LAND MGMT"
                       r"\BKV122TX - Project Emirates\JOSH B UNIT"
                       r"\1. Landman Submitted\Leases"
                       r"\l52 - 596.589 - Frances Caswell OGL "
                       r"(Memorandum).pdf")
    if not doc.exists():
        pytest.skip("Drive local indisponivel nesta maquina")
    try:
        from src.knowledge.classifier import default_ocr
        with fitz.open(doc) as pdf:
            png = pdf[0].get_pixmap(dpi=200).tobytes("png")
        ocr = default_ocr()(Image.open(io.BytesIO(png))).upper()
    except Exception:
        pytest.skip("OCR nao configurado nesta maquina")
    assert ocr.strip(), "OCR vazio"
    # o cerne do verifier_error: o numero 1272 NAO esta na pagina entregue
    assert "1272" not in ocr


def test_regressao_verifier_error_nao_e_divergencia_de_titulo(tmp_path):
    """A metade positiva, com dado real embutido: o trecho que o examinador
    capturou (a citação literal do memorandum 596/589) contém A-811, e uma
    verificação que declara A-1272 sobre ele é `divergencia` — mas ao ser
    invalidada como verifier_error SAI das métricas de título."""
    repo, unit, _ = _unit(tmp_path)
    evidencia_real = ("50.00 acres of land, more or less, being a part of "
                      "Section #3422, Texas Emigration & Land Co., Survey, "
                      "A-811, and being more particularly described in that "
                      "certain Deed dated January 4, 1940")
    assert "A-811" in evidencia_real and "1272" not in evidencia_real
    sess = repo.abrir_sessao(unit["id"], "coletar.leitura_006", "opus")
    cid = repo.inserir_claim(
        unit["id"], "fact", "serie 0220936 — leitura da /006 (596/589)",
        {"abrange_a669_ou_a319": "nao", "leitura_completa": True},
        SHA_A, "1", evidencia_real, "alta", "alta", sess)
    vid = repo.registrar_verificacao(
        cid, "survey/abstract?", "divergencia", "gpt-x",
        {"valor": "C.H.G.R.R. A-1272"}, {}, 0.02)
    # inspeção visual do operador: a página tem A-811 -> verifier_error
    repo.invalidar_verificacao(vid, "verifier_error: a pagina 596/589 tem "
                               "A-811 (inspecao visual do operador); "
                               "A-1272 nao esta na evidencia")
    rec = vs3_entregaveis.reconciliar(repo, unit)
    assert rec["vereditos"]["divergencia"] == 0   # nao conta como divergencia
    assert rec["verificacao_tentada"] == 0        # invalidada fora


def test_preflight_resume_aware_exclui_trabalho_concluido(tmp_path,
                                                          monkeypatch,
                                                          capsys):
    from src.casefile import cli
    repo, unit, pasta = _unit(tmp_path)
    monkeypatch.setattr(cli, "ULTIMA", tmp_path / "ultima")
    monkeypatch.setenv("CASEFILE_TETO_UNIT_USD", "25")
    repo.transicionar(unit["id"], "INDICADA", "EXAMINANDO", "atalho", "t")
    repo.registrar_custo(unit["id"], "modelo", 19.5, {})   # restante $5.50
    sess = repo.abrir_sessao(unit["id"], "exame.vs3", "opus")
    repo.fechar_sessao(sess, "INTERROMPIDA: credit", 5, {}, 2.3, "x")
    cid = _claim(repo, unit, valor={"x": 1})
    repo.registrar_verificacao(cid, "q", "concordancia", "b", {}, {}, 0.0)
    n_antes = len(repo.sessoes_da_unit(unit["id"]))
    cli.cmd_examinar("U UNIT", repo=repo, so_preflight=True)
    saida = capsys.readouterr().out
    assert "resume-aware" in saida
    assert "INTERROMPIDA" in saida
    assert "verificacoes validas: 1" in saida
    assert "nenhuma chamada de modelo" in saida
    assert len(repo.sessoes_da_unit(unit["id"])) == n_antes  # nada novo


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
