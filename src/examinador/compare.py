"""The measurement — cell by cell, populations declared BEFORE counting.

A score is only evidence if its denominator was fixed before anyone looked at
the numerator. So this module states its populations first, in the report it
writes, and every rate it prints names the population it divides by.

It compares three things and never conflates them:

  the hand DDR      what a landman delivered — the thing being reproduced;
  the IA workbook   what the Examiner wrote this round;
  the template      what was already in the file before either of them.

The third matters: a cell that agrees with the hand because the TEMPLATE
happened to hold the same value is not a cell the model got right, and counting
it would be the easiest way to fake this whole exercise.

This harness runs OUTSIDE the quarantine, after the run. It is the only code
allowed to open the answer sheet.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

HAND = (Path("C:/Users/Renato/PURPLE LAND MGMT/BKV122TX - Project Emirates")
        / "JOSH B UNIT" / "1. Landman Submitted" / "PLM Report"
        / "DDR - Josh B Unit.xlsx")


def norm(value: Any) -> str:
    """Compare what a reader would call the same value.

    Case, surrounding whitespace and trailing zeros in a decimal are noise. A
    different number, a different name or a different volume is not.

    A date is normalised to ISO because a workbook stores `2010-01-21` as a
    datetime and a model writes it as text, and calling those two different
    values makes the harness — not the model — the thing being measured."""
    from datetime import date as _date
    from datetime import datetime as _datetime

    if isinstance(value, (_datetime, _date)):
        return value.strftime("%Y-%m-%d")
    text = " ".join(str(value if value is not None else "").split()).strip().lower()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ t]00:00:00", text):
        text = text[:10]
    if re.fullmatch(r"-?\d+\.\d+", text):
        text = text.rstrip("0").rstrip(".")
    return text


# Punctuation the two writers use differently around identical content: an em
# dash where the other has a comma, a parenthetical source note appended.
_LOOSE = re.compile(r"[^a-z0-9]+")


def equivalent(a: str, b: str) -> bool:
    """Same value, more or less prose around it.

    `volume 506, page 386, real records, montague county` and `volume 506, page
    386, montague county, texas` are one recording written two ways. This is
    NOT a claim that they are interchangeable in a deliverable — the house style
    is part of the product — which is why it gets its own bucket rather than
    being folded into agreement."""
    x, y = _LOOSE.sub(" ", a).strip(), _LOOSE.sub(" ", b).strip()
    if not x or not y:
        return False
    return x == y or x in y or y in x


def cells_of(path: str | Path, raw: bool = False) -> dict[tuple[str, str], str]:
    """Normalised for comparing; raw for showing a human what is in the file."""
    wb = openpyxl.load_workbook(Path(path), data_only=True)
    try:
        return {(ws.title, c.coordinate): (
                    " ".join(str(c.value).split()) if raw else norm(c.value))
                for ws in wb.worksheets
                for row in ws.iter_rows() for c in row
                if c.value not in (None, "")}
    finally:
        wb.close()


@dataclass
class Population:
    name: str
    definition: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {"populacao": self.name, "definicao": self.definition,
                "tamanho": self.size}


@dataclass
class Comparison:
    populations: list[Population] = field(default_factory=list)
    tabs_only_hand: list[str] = field(default_factory=list)
    tabs_only_ia: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    agreed: list[str] = field(default_factory=list)
    equivalent: list[dict[str, str]] = field(default_factory=list)
    disagreed: list[dict[str, str]] = field(default_factory=list)
    silent: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    inherited: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "populacoes_declaradas_antes": [p.to_dict() for p in self.populations],
            "abas_alinhadas_por_apelido": self.aliases,
            "abas_so_no_gabarito": self.tabs_only_hand,
            "abas_so_na_ia": self.tabs_only_ia,
            "baldes": {
                "concordou": "mesmo valor, caractere a caractere apos "
                             "normalizar caixa, espaco e data",
                "equivalente": "mesmo valor com mais ou menos prosa em volta "
                               "— um contem o outro. NAO e acerto: o estilo da "
                               "casa faz parte do produto",
                "divergiu": "conteudo diferente",
                "calou": "a mao escreveu, a IA nao",
                "escreveu_a_mais": "a IA escreveu, a mao nao tem",
                "herdado": "bateu porque o TEMPLATE ja tinha o valor — nao e "
                           "obra do modelo",
            },
            "resultado": {
                "concordou": len(self.agreed),
                "equivalente": len(self.equivalent),
                "divergiu": len(self.disagreed),
                "calou_onde_a_mao_escreveu": len(self.silent),
                "escreveu_onde_a_mao_nao_tem": len(self.extra),
                "herdado_do_template_nao_conta": len(self.inherited),
            },
            "equivalentes": self.equivalent[:200],
            "divergencias": self.disagreed[:200],
            "calados": self.silent[:200],
            "herdados": self.inherited[:200],
        }


def compare(ia_workbook: str | Path, ledger_path: str | Path,
            hand: str | Path = HAND,
            template: str | Path | None = None,
            aliases: dict[str, str] | None = None) -> Comparison:
    """Every count below divides by a population named in the report.

    `aliases` renames a tab on the IA side before comparing. It exists for one
    real case: the template calls a sheet `Ownership Report` and the delivered
    kit calls the same sheet `Ownership - Worksheet`. Without the alias every
    cell on it counts twice as a failure — once as silence, once as surplus —
    and the number would be measuring my harness, not the model. It is declared
    in the report so nobody has to take that on trust."""
    from src.examinador.run import TEMPLATE

    aliases = {"Ownership Report": "Ownership - Worksheet"} if aliases is None \
        else aliases

    def alias(cells: dict[tuple[str, str], str]) -> dict[tuple[str, str], str]:
        return {(aliases.get(t, t), c): v for (t, c), v in cells.items()}

    hand_cells = cells_of(hand)
    ia_cells = alias(cells_of(ia_workbook))
    tpl_cells = alias(cells_of(template if template is not None else TEMPLATE))

    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    written = {(aliases.get(c["aba"], c["aba"]), c["celula"])
               for c in ledger["celulas"]}

    hand_tabs = {t for t, _ in hand_cells}
    ia_tabs = {t for t, _ in ia_cells}

    out = Comparison(
        aliases=aliases,
        tabs_only_hand=sorted(hand_tabs - ia_tabs),
        tabs_only_ia=sorted(ia_tabs - hand_tabs),
        populations=[
            Population("gabarito", "celulas nao vazias do DDR a mao, todas as "
                                   "abas", len(hand_cells)),
            Population("escritas_pela_ia", "celulas que o ledger registra como "
                                           "escritas pelo modelo", len(written)),
            Population("template", "celulas nao vazias do template antes de "
                                   "qualquer escrita", len(tpl_cells)),
        ])

    for key, hand_value in hand_cells.items():
        ia_value = ia_cells.get(key)
        if key not in written:
            if ia_value is not None and ia_value == hand_value:
                # Right answer, wrong author: the template already held it.
                out.inherited.append(f"{key[0]}!{key[1]} = {hand_value[:40]}")
            else:
                out.silent.append(f"{key[0]}!{key[1]} (mao: {hand_value[:40]})")
            continue
        if ia_value == hand_value:
            out.agreed.append(f"{key[0]}!{key[1]}")
        elif ia_value is not None and equivalent(hand_value, ia_value):
            out.equivalent.append({"celula": f"{key[0]}!{key[1]}",
                                   "mao": hand_value[:70],
                                   "ia": ia_value[:70]})
        else:
            out.disagreed.append({"celula": f"{key[0]}!{key[1]}",
                                  "mao": hand_value[:70],
                                  "ia": (ia_value or "")[:70]})

    for key in written:
        if key not in hand_cells:
            out.extra.append(f"{key[0]}!{key[1]}")

    return out


def leftovers(ia_workbook: str | Path, ledger_path: str | Path,
              template: str | Path | None = None) -> dict[str, Any]:
    """Template cells that survived untouched into the delivered workbook.

    Another unit's sample data reaching a client is a defect whether or not it
    affects the score, so it is counted separately and never nets off against
    anything."""
    from src.examinador.run import TEMPLATE

    source = template if template is not None else TEMPLATE
    tpl = cells_of(source)
    shown = cells_of(source, raw=True)
    ia = cells_of(ia_workbook)
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    touched = ({(c["aba"], c["celula"]) for c in ledger["celulas"]}
               | {(b["aba"], b["celula"]) for b in ledger["brancos"]})
    survived = [f"{t}!{c} = {shown[(t, c)][:40]}" for (t, c), v in tpl.items()
                if (t, c) not in touched and ia.get((t, c)) == v]
    return {"celulas_do_template_ainda_no_entregavel": len(survived),
            "amostra": survived[:100]}


def report(ia_workbook: str | Path, ledger_path: str | Path,
           out_path: str | Path) -> dict[str, Any]:
    data = {"comparacao": compare(ia_workbook, ledger_path).to_dict(),
            "restos_do_template": leftovers(ia_workbook, ledger_path)}
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    return data
