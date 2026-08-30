"""Resolver de unit e referências — nome para pasta, mais novo por data."""
from __future__ import annotations

from src.casefile import referencia


def _projeto(tmp_path):
    root = tmp_path / "BKV999TX - Projeto Teste"
    root.mkdir()
    for nome in ("JOSH B UNIT", "WEBB B UNIT", "CAIN RANCH A UNIT #1H WELL",
                 "MAXWELL A UNIT"):
        (root / nome).mkdir()
    return root


def test_unit_folder_resolve_caixa_e_tokens(tmp_path):
    root = _projeto(tmp_path)
    assert referencia.unit_folder("Josh B Unit", root).name == "JOSH B UNIT"
    assert referencia.unit_folder("josh b unit", root).name == "JOSH B UNIT"
    # Tokens distintivos: o sufixo "#1H WELL" da pasta nao impede o match.
    assert referencia.unit_folder("Cain Ranch A", root).name == \
        "CAIN RANCH A UNIT #1H WELL"


def test_unit_folder_ambiguo_ou_ausente_devolve_none(tmp_path):
    root = _projeto(tmp_path)
    (root / "JOSH C UNIT").mkdir()
    assert referencia.unit_folder("Josh", root) is None      # 2 candidatas
    assert referencia.unit_folder("Inexistente X", root) is None
    assert "JOSH B UNIT" in referencia.listar_pastas_de_unit(root)


def test_find_reference_pega_a_mais_nova_e_ignora_copy(tmp_path):
    root = _projeto(tmp_path)
    (root / "Lease to Well and Contract XREF 05-22-2026.xlsx").write_bytes(
        b"velha")
    (root / "Lease to Well and Contract XREF 06-16-2026 (1).xlsx"
     ).write_bytes(b"nova")
    (root / "Copy of Lease to Well and Contract XREF 06-16-2026 (1).xlsx"
     ).write_bytes(b"copia")
    got = referencia.find_reference("xref", root)
    assert got.name == "Lease to Well and Contract XREF 06-16-2026 (1).xlsx"
    assert referencia.find_reference("well_list", root) is None


def test_tokens_distintivos():
    assert referencia.unit_identity_tokens("MAXWELL A UNIT") == {"MAXWELL"}
    assert referencia.unit_identity_tokens("CAIN RANCH A UNIT #1H WELL") == \
        {"CAIN", "RANCH", "1H", "WELL"}
