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


def test_gates_pendentes_e_ok_na_ordem(tmp_path):
    repo, unit, pasta = _unit(tmp_path)
    _claim_lease(repo, unit, "0111111/001")
    _claim_lease(repo, unit, "0220936/001")
    assert all(g["status"] != "ok" for g in gates.avaliar(repo, unit))

    # G1: populações + leitura da série
    populacoes.recalcular(repo, unit)
    _fact(repo, unit, "serie 0220936 legal descriptions",
          {"abrange_a669_ou_a319": "nao", "por_lease": {}})
    # G2: lookups por contrato, unit, todas as leases e recording
    for kind, valor in (("contract", "K9999999"), ("unit_name", "JOSH T"),
                        ("lease_no", "0111111-001"),
                        ("lease_no", "0220936-001"),
                        ("recording", "100/1")):
        repo.registrar_xref_lookup(unit["id"], SHA_X, kind, valor, 1)
    # G3, G5, G6: leituras dirigidas
    _fact(repo, unit, "grupo BRA-DE", {"instrumentos": [],
                                       "classificacao": "ratificacao"})
    _fact(repo, unit, "TO A-669 155ac",
          {"certification_date": "2010-04-09", "amarracao": {"2": "ok"}})
    _fact(repo, unit, "release Marlee M Stewart",
          {"natureza": "release", "efeito_no_tract_1": "x"})
    # G4: busca julgada + solicitação ao PM
    bid = repo.registrar_busca(unit["id"], "DOTO/DOI", ["doto"], "tudo",
                               10, [], result="nao_encontrado")
    sess = repo.abrir_sessao(unit["id"], "x", "m")
    repo.inserir_pesquisa(unit["id"], "Solicitar DOTO/DOI",
                          "DOTO/DOI do unit", "PM/seller", "email", sess, [])
    todos = gates.avaliar(repo, unit)
    assert [g["status"] for g in todos] == ["ok"] * 6, todos


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
