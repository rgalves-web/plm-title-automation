"""Censo determinístico — identidade por bytes, recursão, origem, quarentena."""
from __future__ import annotations

import zipfile

from src.casefile import censo
from src.casefile.acervo import montar_acervo
from tests.helpers_casefile import RepoFake, unit_de_teste

XREF_NOME = "Lease to Well and Contract XREF 06-16-2026.xlsx"


def _arvore(tmp_path):
    """Unit com zip em subpasta, conteúdo duplicado, entrega e homônimo."""
    root = tmp_path / "PROJ"
    unit = root / "TESTE A UNIT"
    (unit / "FILES").mkdir(parents=True)
    # mesmo conteúdo em 2 caminhos: dentro do zip e solto
    (unit / "FILES" / "solto.pdf").write_bytes(b"conteudo-A")
    with zipfile.ZipFile(unit / "FILES" / "pacote.zip", "w") as zf:
        zf.writestr("Pasta X/doc1.pdf", b"conteudo-A")
        zf.writestr("Pasta X/doc2.pdf", b"conteudo-B")
    # zip em subpasta fora de FILES (recursão)
    (unit / "docs" / "nested").mkdir(parents=True)
    with zipfile.ZipFile(unit / "docs" / "nested" / "extra.zip", "w") as zf:
        zf.writestr("sub/m.txt", b"conteudo-C")
    # entrega: réplica do doc1 no kit entregue
    entrega = unit / "1. Landman Submitted" / "Title Documents"
    entrega.mkdir(parents=True)
    (entrega / "506.386.pdf").write_bytes(b"conteudo-A")
    # homônimo: XREF na unit com bytes DIFERENTES do master da raiz
    (unit / XREF_NOME).write_bytes(b"xref-da-unit")
    (root / XREF_NOME).write_bytes(b"xref-master")
    # estado de automação: nunca vira corpus
    (unit / "_minorh").mkdir()
    (unit / "_minorh" / "estado.json").write_text("{}", encoding="utf-8")
    return root, unit


def test_censo_identidade_recursao_e_homonimos(tmp_path):
    root, pasta = _arvore(tmp_path)
    repo = RepoFake()
    unit = unit_de_teste(repo, pasta, "TESTE A UNIT")
    referencias = {"xref": root / XREF_NOME, "well_list": None}

    got = censo.executar(repo, unit, pasta, referencias)

    # mesmos bytes em 3 caminhos (zip, solto, entrega) = 1 conteúdo
    shas = repo.sha_por_nome(unit["id"])
    assert len(shas["files/solto.pdf"]) == 1
    assert shas["files/solto.pdf"] == shas["files/pasta x/doc1.pdf"]
    # recursão: membro de zip em subpasta indexado
    assert "docs/nested/sub/m.txt" in shas
    # homônimo por basename com bytes diferentes é fato nomeado
    assert XREF_NOME.lower() in {n.lower() for n in got["homonimos"]}
    # _minorh nunca entra
    assert not any("_minorh" in n for n in shas)
    # origem: entrega registrada como entrega
    origens = repo.contagem_censo(unit["id"])
    assert origens["entrega"]["sightings"] == 1
    assert origens["project_reference"]["sightings"] == 1


def test_censo_e_idempotente(tmp_path):
    root, pasta = _arvore(tmp_path)
    repo = RepoFake()
    unit = unit_de_teste(repo, pasta, "TESTE A UNIT")
    referencias = {"xref": root / XREF_NOME}
    a = censo.executar(repo, unit, pasta, referencias)
    b = censo.executar(repo, unit, pasta, referencias)
    assert a["sightings"] == b["sightings"]
    assert len(repo.sightings) == a["sightings"]     # upsert, não duplicação


def test_acervo_da_sessao_exclui_entrega_por_padrao(tmp_path):
    root, pasta = _arvore(tmp_path)
    referencias = {"xref": root / XREF_NOME}
    acervo = montar_acervo(pasta, referencias)
    nomes = acervo.names()
    assert not any("landman submitted" in n for n in nomes)
    assert "files/solto.pdf" in nomes
    assert f"referencias/{XREF_NOME.lower()}" in nomes
    com_entrega = montar_acervo(pasta, referencias, incluir_entrega=True)
    assert any("landman submitted" in n for n in com_entrega.names())
    # leitura in-place de membro de zip em subpasta
    assert acervo.read_bytes("docs/nested/sub/m.txt") == b"conteudo-C"
