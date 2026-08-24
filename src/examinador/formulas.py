"""Propriedades da caneta: fórmulas do template são intocáveis.

A regra é do cliente (Manual Técnico cap. 9.1/13, S02 de 13/08: nunca
hard-keyar células azuis) e a fronteira é a §2 do doc governante: proteger
bytes não é decidir title. Este módulo só INDEXA e COMPARA — quem decide o que
fazer com uma escrita recusada é o modelo, que recebe o erro nomeado.

Duas funções:

  formula_cells(path)   {(aba, célula): fórmula} de um workbook
  formulas_hash(path)   hash ordenado do conjunto — o mesmo antes e depois de
                        todo save, ou o ship aborta (VAL-003)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import openpyxl


class FormulaAlterada(AssertionError):
    """O conjunto de fórmulas do arquivo salvo difere do template."""


def formula_cells(path: str | Path) -> dict[tuple[str, str], str]:
    """Toda célula com fórmula, por (aba, coordenada).

    `data_only=False` para ler a fórmula em si; cobre tanto `data_type == 'f'`
    quanto valores-string que começam com `=` (template salvo sem cache)."""
    wb = openpyxl.load_workbook(Path(path), data_only=False)
    out: dict[tuple[str, str], str] = {}
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    value = cell.value
                    if value is None:
                        continue
                    if cell.data_type == "f" or (
                            isinstance(value, str) and value.startswith("=")):
                        out[(ws.title, cell.coordinate)] = str(value)
    finally:
        wb.close()
    return out


def formulas_hash(path: str | Path) -> str:
    """Hash do conjunto ordenado {(aba, célula, fórmula)}."""
    triplos = sorted((aba, coord, formula)
                     for (aba, coord), formula in formula_cells(path).items())
    blob = json.dumps(triplos, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def erro_celula_de_formula(aba: str, celula: str) -> str:
    """A mensagem nomeada que volta ao modelo — ele redecide, nunca vira
    branco silencioso."""
    return (f"{aba}!{celula} contém fórmula do template — não escreva; o "
            f"valor verificado pertence à célula branca correspondente")
