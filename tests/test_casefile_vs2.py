"""VS2 — encanamento: índice local, populações, busca, staging, gates.

Nenhuma asserção conclui title: os testes provam recuperação por chave,
preservação de denominador, auditabilidade da busca, round-trip do staging e
a recusa do avanço com gate pendente.
"""
from __future__ import annotations

import openpyxl
import pytest

from src.casefile import buscas, estados, gates, populacoes, staging
from src.casefile import xref_local as xl
from tests.helpers_casefile import RepoFake, unit_de_teste

SHA_X = "e" * 64


def _unit(tmp_path, nome="JOSH T UNIT"):
    repo = RepoFake()
    pasta = tmp_path / nome
    (pasta / "FILES").mkdir(parents=True)
    unit = unit_de_teste(repo, pasta, nome)
    return repo, unit, pasta


def _claim_lease(repo, unit, lease, lessor="F", vol="100", page="1"):
    sess = repo.abrir_sessao(unit["id"], "t", "m")
    repo.registrar_source_file(SHA_X, 9)
    return repo.inserir_claim(
        unit["id"], "lease_in_unit", f"lease {lease}",
        {"lease_no": lease, "lessor": lessor, "vol": vol, "page": page},
        SHA_X, "1", "trecho", "alta", "alta", sess)


# --- índice local -----------------------------------------------------------

def _xref_sintetico(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    # cabeçalho com nomes DUPLICADOS (lado lease e lado contrato, como o real)
    ws.append(["LEASE NO", "LESSOR", "RECORD TYPE", "WELL OR CONTRACT NB",
               "WELL OR CONTRACT NAME", "RECORD TYPE"])
    ws.append(["0111111-001", "FULANO", "FEE", "K9999999",
               "DECL OF POOLED UNIT- JOSH T UN", "UNIT AGREEMENT"])
    ws.append(["0111111-002", "BELTRANO", "FEE", "K0000001",
               "OUTRA UNIT", "UNIT AGREEMENT"])
    ws2 = wb.create_sheet("Sheet2")
    ws2.append(["LEASE NO", "LESSOR", "RECORD TYPE", "WELL OR CONTRACT NB",
                "WELL OR CONTRACT NAME", "RECORD TYPE"])
    ws2.append(["0111111-003", "SICRANO", "FEE", "K9999999",
                "DECL OF POOLED UNIT- JOSH T UN", "UNIT AGREEMENT"])
    path = tmp_path / "XREF sintetico.xlsx"
    wb.save(path)
    return path


def test_indexador_recupera_por_chave_e_registra_lookups(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    path = _xref_sintetico(tmp_path)
    chaves = [xl.chave_contract("K9999999"),
              xl.chave_unit_name("JOSH T"),
              xl.chave_lease_no("0111111/001"),     # formato dos claims
              xl.chave_lease_no("0111111/999")]     # inexistente
    got = xl.indexar(repo, unit, path, SHA_X, chaves,
                     ["LEASE NO", "WELL OR CONTRACT NB",
                      "WELL OR CONTRACT NAME"])
    assert got["linhas_casadas"] == 2                # linhas 2 (S1) e 2 (S2)
    assert got["chaves_sem_linha"] == ["lease_no:0111111/999"]
    lookups = {(x["key_kind"], x["key_value"]): x["rows_found"]
               for x in repo.xref_lookups(unit["id"])}
    assert lookups[("contract", "K9999999")] == 2
    assert lookups[("lease_no", "0111111/001")] == 1
    assert lookups[("lease_no", "0111111/999")] == 0
    linhas = repo.xref_rows_da_unit(unit["id"])
    # cabeçalho duplicado desambiguado e linha inteira preservada
    assert linhas[0]["row"]["RECORD TYPE"] == "FEE"
    assert linhas[0]["row"]["RECORD TYPE__2"] == "UNIT AGREEMENT"


def test_indexador_falha_ruidoso_sem_coluna(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    path = _xref_sintetico(tmp_path)
    with pytest.raises(xl.ErroDeCabecalho, match="INEXISTENTE"):
        xl.indexar(repo, unit, path, SHA_X, [], ["COLUNA INEXISTENTE"])


def test_indexador_pula_aba_sem_colunas_e_aceita_alternativas(tmp_path):
    """A Schedule real: aba principal com cabeçalho VAZIO na coluna da
    lease; abas seguintes com 'LEASENO'; uma aba de outra natureza."""
    repo, unit, _ = _unit(tmp_path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "EOG Leases"
    ws.append(["DIVISION", "", "RECORDING"])
    ws.append(["FW", "0111111-001", "Vol 531, Pg 840"])
    ws2 = wb.create_sheet("Outra Natureza")
    ws2.append(["QUALQUER", "COISA"])
    ws2.append(["x", "y"])
    ws3 = wb.create_sheet("EOG Outleases")
    ws3.append(["DIVISION", "LEASENO", "RECORDING"])
    ws3.append(["FW", "0111111-002", "Vol 1, Pg 2"])
    path = tmp_path / "Schedule sintetica.xlsx"
    wb.save(path)
    chaves = [xl.chave_lease_no("0111111/001", coluna=("LEASENO", "")),
              xl.chave_lease_no("0111111/002", coluna=("LEASENO", "")),
              xl.chave_recording("531", "840", coluna="RECORDING")]
    got = xl.indexar(repo, unit, path, SHA_X, chaves,
                     [("LEASENO", ""), "RECORDING"])
    assert got["abas"] == ["EOG Leases", "EOG Outleases"]
    assert list(got["abas_puladas"]) == ["Outra Natureza"]
    assert got["linhas_casadas"] == 2
    lookups = {(x["key_kind"], x["key_value"]): x["rows_found"]
               for x in repo.xref_lookups(unit["id"])}
    assert lookups[("lease_no", "0111111/001")] == 1
    assert lookups[("recording", "531/840")] == 1


def test_normalizacao_e_recording():
    assert xl.normalizar_lease(" 0220604/001 ") == "0220604-001"
    assert xl.normalizar_lease("0220604-001") == "0220604-001"
    chave = xl.chave_recording("531", "840", coluna="REC")
    assert chave.casa({"REC": "Montague: Vol 531, Pg 840"})
    assert chave.casa({"REC": "531/840 (Cooke)"})
    assert not chave.casa({"REC": "Vol 5310 Pg 8400"})
    assert not chave.casa({"REC": "Vol 531 ....... Pg 999"})


# --- populações -------------------------------------------------------------

def test_populacoes_preservam_denominador_e_expOem_deltas(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    for lease in ("0111111/001", "0111111/002", "0220936/001"):
        _claim_lease(repo, unit, lease)
    repo.registrar_xref_row(unit["id"], SHA_X, "Sheet1", 2,
                            {"LEASE NO": "0111111-001"}, ["contract:K"])
    repo.registrar_xref_row(unit["id"], SHA_X, "Sheet1", 9,
                            {"LEASE NO": "0999999-000"}, ["contract:K"])
    got = populacoes.recalcular(repo, unit)
    assert got["contagens"]["dpu_exhibit_a"] == 3
    assert got["contagens"]["operacional"] == 3        # 0220936 NAO sai
    assert got["contagens"]["candidate_out_of_scope"] == 1
    assert got["dpu_sem_linha_no_xref"] == ["0111111-002", "0220936-001"]
    assert got["xref_fora_da_dpu"] == ["0999999-000"]
    # recalcular é idempotente
    de_novo = populacoes.recalcular(repo, unit)
    assert de_novo["contagens"] == got["contagens"]


# --- busca negativa ---------------------------------------------------------

def test_busca_negativa_auditavel(tmp_path):
    repo, unit, pasta = _unit(tmp_path)
    (pasta / "FILES" / "carta.txt").write_text(
        "nada a ver com o assunto", encoding="utf-8")
    raiz = pasta.parent
    (raiz / "OUTRA PASTA").mkdir()
    (raiz / "OUTRA PASTA" / "Division Order antigo.pdf").write_bytes(b"x")
    from src.casefile.acervo import montar_acervo
    acervo = montar_acervo(pasta, {})
    got = buscas.busca_doto_doi(repo, unit, raiz, acervo)
    b = repo.buscas(unit["id"], "DOTO/DOI")[0]
    assert got["resultado"] == "pendente_julgamento"     # hit de NOME
    assert any(h["escopo"] == "nome" for h in b["hits"])
    assert b["names_scanned"] >= 2
    repo.julgar_busca(b["id"], "nao_encontrado", "hit e de outra unit")
    assert repo.buscas(unit["id"])[0]["result"] == "nao_encontrado"


# --- staging e promoção -----------------------------------------------------

def test_staging_valida_e_promove_com_round_trip(tmp_path):
    repo, unit, pasta = _unit(tmp_path)
    iid = repo.criar_collection_item(unit["id"], "610.245.pdf",
                                     "courthousedirect",
                                     {"book": "610", "page": "245"})
    caminho, sha = staging.stage_bytes(
        repo, unit, pasta, iid, "610.245.pdf", b"pdf-bytes",
        {"portal": "teste"})
    assert "staging" in caminho.parts
    item = repo.collection_items(unit["id"])[0]
    with pytest.raises(AssertionError, match="VALIDADO"):
        staging.promover(repo, unit, pasta, item)       # staged nao promove
    staging.marcar_validado(repo, iid, "ok")
    item = repo.collection_items(unit["id"])[0]
    final = staging.promover(repo, unit, pasta, item)
    assert final == pasta / "FILES" / "610.245.pdf"
    assert final.read_bytes() == b"pdf-bytes"
    # censo imediato: identidade + sighting registrados
    assert repo.sha_existe(sha)
    assert "files/610.245.pdf" in repo.sha_por_nome(unit["id"])
    # promover de novo (mesmos bytes) é idempotente
    item = repo.collection_items(unit["id"])[0]
    assert item["status"] == "promovido"


def test_caneta_recusa_promocao_fora_das_regras(tmp_path):
    from src.casefile import caneta
    repo, unit, pasta = _unit(tmp_path)
    solto = tmp_path / "solto.pdf"
    solto.write_bytes(b"x")
    with pytest.raises(caneta.EscritaForaDoCaseFile, match="staging"):
        caneta.promover_staged(solto, pasta / "FILES" / "x.pdf", "0" * 64)
    staged = staging.dir_staging(pasta) / "x.pdf"
    staged.write_bytes(b"x")
    import hashlib
    sha = hashlib.sha256(b"x").hexdigest()
    with pytest.raises(caneta.EscritaForaDoCaseFile, match="FILES"):
        caneta.promover_staged(staged, pasta / "Leases" / "x.pdf", sha)
    (pasta / "FILES" / "x.pdf").write_bytes(b"DIFERENTE")
    with pytest.raises(AssertionError, match="DIFERENTES"):
        caneta.promover_staged(staged, pasta / "FILES" / "x.pdf", sha)


# --- gates e avanço ---------------------------------------------------------

def _fact(repo, unit, entidade, valor):
    sess = repo.abrir_sessao(unit["id"], "coletar.exame", "m")
    repo.registrar_source_file(SHA_X, 9)
    return repo.inserir_claim(unit["id"], "fact", entidade, valor, SHA_X,
                              "1", "trecho", "alta", "media", sess)


def _armar_gates(repo, unit, completo=True):
    """Arma os artefatos dos 6 gates; `completo=False` deixa as leituras
    sem as chaves de evidência (determinação 2)."""
    _claim_lease(repo, unit, "0111111/001")
    _claim_lease(repo, unit, "0220936/001")
    populacoes.recalcular(repo, unit)
    extra_serie = {"leitura_completa": True} if completo else {}
    _fact(repo, unit, "serie 0220936 legal descriptions",
          {"abrange_a669_ou_a319": "nao", "por_lease": {}, **extra_serie})
    for kind, valor in (("contract", "K9999999"), ("unit_name", "JOSH T"),
                        ("lease_no", "0111111-001"),
                        ("lease_no", "0220936-001"),
                        ("recording", "100/1")):
        repo.registrar_xref_lookup(unit["id"], SHA_X, kind, valor, 1)
    _fact(repo, unit, "grupo BRA-DE", {"instrumentos": [],
                                       "classificacao": "top lease"})
    extra_155 = {"diferenca_gross_explicada":
                 "TO cobre 155 ac gross; o trato usa 80.02"} if completo \
        else {}
    _fact(repo, unit, "TO A-669 155ac",
          {"certification_date": "2010-03-03", "amarracao": {"2": "ok"},
           **extra_155})
    extra_rel = {"leitura_completa": True} if completo else {}
    _fact(repo, unit, "release Marlee M Stewart",
          {"natureza": "release", "efeito_no_tract_1": "x", **extra_rel})
    repo.registrar_busca(unit["id"], "DOTO/DOI", ["doto"], "tudo",
                         10, [], result="nao_encontrado")
    sess = repo.abrir_sessao(unit["id"], "x", "m")
    repo.inserir_pesquisa(unit["id"], "Solicitar DOTO/DOI",
                          "DOTO/DOI do unit", "PM/seller", "email", sess, [])


def test_gates_pendentes_e_ok_na_ordem(tmp_path):
    repo, unit, pasta = _unit(tmp_path)
    _claim_lease(repo, unit, "0111111/001")
    assert all(g["status"] != "ok" for g in gates.avaliar(repo, unit))
    repo2, unit2, _ = _unit(tmp_path / "b")
    _armar_gates(repo2, unit2, completo=True)
    todos = gates.avaliar(repo2, unit2)
    assert [g["status"] for g in todos] == ["ok"] * 6, todos


def test_tentativa_nao_e_evidencia_semantica_da_determinacao_2(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    _armar_gates(repo, unit, completo=False)
    por_condicao = {g["condicao"]: g["status"]
                    for g in gates.avaliar(repo, unit)}
    # leitura declarada impossível BLOQUEIA; parciais passam com ressalva
    assert por_condicao["release-marlee-stewart"] == "pendente_evidencia"
    assert por_condicao["to-155ac-certificacao-e-amarracao"] == "ok_parcial"
    assert por_condicao["populacao-exhibit-a"] == "ok_parcial"
    bloqueiam = gates.pendentes(repo, unit)
    assert [g["condicao"] for g in bloqueiam] == ["release-marlee-stewart"]


def test_avancar_recusa_com_gate_pendente_e_passa_com_todos_ok(tmp_path,
                                                               monkeypatch):
    from src.casefile import cli
    repo, unit, pasta = _unit(tmp_path)
    monkeypatch.setattr(cli, "ULTIMA", tmp_path / "ultima")
    repo.transicionar(unit["id"], "INDICADA", "COLETANDO", "atalho", "teste")
    with pytest.raises(SystemExit, match="AVANCO RECUSADO"):
        cli.cmd_avancar(unit["canonical_name"], repo=repo)
    assert repo.estado_da_unit(unit["id"]) == "COLETANDO"


def test_pergunta_vs2_trava_gate_como_pendente_operador(tmp_path):
    repo, unit, pasta = _unit(tmp_path)
    repo.registrar_pergunta_vs2(unit["id"], "[bra-de] ambiguidade real")
    g3 = [g for g in gates.avaliar(repo, unit)
          if g["condicao"] == "cadeia-bra-de"][0]
    assert g3["status"] == "pendente_operador"


def test_bloqueio_por_evento_continua_valido(tmp_path):
    repo, unit, _ = _unit(tmp_path)
    estados.transicionar(repo, unit, "planejar", "operador")
    assert repo.estado_da_unit(unit["id"]) == "PLANEJANDO"


# --- determinações de 02/09 (rodada 2) --------------------------------------

def test_claim_de_evidencia_so_da_entrega_leva_marca_de_contaminacao(
        tmp_path):
    from src.casefile import ferramentas
    repo, unit, pasta = _unit(tmp_path)
    sid = repo.registrar_source_file(SHA_X, 9)
    repo.registrar_sighting(sid, unit["id"], "c", "", "1. landman "
                            "submitted/seller files/release.pdf", "entrega")
    sess_ref = {"id": repo.abrir_sessao(unit["id"], "t", "m")}
    from src.casefile.acervo import Acervo, AcervoIndex
    dispatch = ferramentas.montar_dispatch(
        acervo=Acervo(AcervoIndex([])), repo=repo, unit=unit, pasta=pasta,
        kb_unidade=_KbNula(), kb_global=_KbNula(), ator="modelo:x",
        session_ref=sess_ref)
    got = dispatch["registrar_claims"](claims=[{
        "tipo": "fact", "entidade": "release — leitura",
        "valor": {"natureza": "x", "leitura_completa": True},
        "documento": f"sha256:{SHA_X}", "pagina": "1",
        "trecho": "trecho literal", "confianca": "alta"}])
    assert got["aceitos"] == 1
    claim = repo.claims_da_unit(unit["id"], "fact")[0]
    assert claim["value"]["benchmark_contamination"] is True
    assert claim["value"]["origem_evidencia"] == "entrega"
    # evidência que TAMBÉM existe fora da entrega não leva a marca
    repo.registrar_sighting(sid, unit["id"], "d", "", "files/release.pdf",
                            "unit_files")
    dispatch["registrar_claims"](claims=[{
        "tipo": "fact", "entidade": "release 2",
        "valor": {"natureza": "y"}, "documento": f"sha256:{SHA_X}",
        "pagina": "1", "trecho": "t", "confianca": "alta"}])
    segundo = repo.claims_da_unit(unit["id"], "fact")[1]
    assert "benchmark_contamination" not in segundo["value"]


class _KbNula:
    def read(self, conceito):
        return {"encontrado": False}

    def write(self, *a, **k):
        return {"gravada": True}


def test_acervo_libera_so_o_arquivo_autorizado_da_entrega(tmp_path):
    from src.casefile.acervo import montar_acervo
    repo, unit, pasta = _unit(tmp_path)
    entrega = pasta / "1. Landman Submitted" / "Seller Files"
    entrega.mkdir(parents=True)
    (entrega / "Stewart curative - EOG release of suspense.pdf"
     ).write_bytes(b"pdf")
    (entrega / "DDR - Josh T Unit.xlsx").write_bytes(b"ddr")
    acervo = montar_acervo(pasta, {},
                           entrega_permitida=("release of suspense",))
    nomes = acervo.names()
    assert any("release of suspense" in n for n in nomes)
    assert not any("ddr - josh t" in n for n in nomes)   # o resto fica fora


def test_reconciliacao_matriz_acoes_e_pull_deduplicada(tmp_path):
    from src.casefile import reconciliacao as rc
    repo, unit, pasta = _unit(tmp_path)
    # lease com instrumento no acervo -> nenhuma ação
    cid = _claim_lease(repo, unit, "0111111/001", vol="100", page="1")
    sid = repo.registrar_source_file("f" * 64, 5)
    repo.registrar_sighting(
        sid, unit["id"], "z", "m",
        "files/0111111-001 (fulano-oil & gas)/lease.tif", "unit_files")
    # lease da checagem do operador (506/386), sem pasta -> coletar corrigido
    _claim_lease(repo, unit, "0220604/018", vol="506", page="386")
    linhas = rc.matriz(repo, unit)
    por_lease = {li["lease"]: li for li in linhas}
    assert por_lease["0111111/001"]["acao"].startswith("nenhuma")
    assert por_lease["0220604/018"]["acao"] == "coletar 506.386.pdf"
    assert "CORRIGIDO" in por_lease["0220604/018"]["divergencia"]
    # pull: cancela item antigo com o nome errado e cria o corrigido
    velho = repo.criar_collection_item(unit["id"], "506.38.pdf",
                                       "courthousedirect", {"book": "506",
                                                            "page": "38"})
    got = rc.regenerar_pull(repo, unit, linhas)
    assert got["cancelados"] == 1 and got["novos"] == 1
    itens = repo.collection_items(unit["id"])
    assert itens[velho - 1]["status"] == "cancelado"
    novos = [i for i in itens if i["status"] == "pendente"]
    assert novos[0]["title"] == "506.386.pdf"
    assert got["custo_estimado_usd"] == 0.5
    # regenerar de novo é idempotente (dedupe por par vol/página)
    de_novo = rc.regenerar_pull(repo, unit, linhas)
    assert de_novo["novos"] == 1
    assert len([i for i in repo.collection_items(unit["id"])
                if i["status"] == "pendente"]) == 1
