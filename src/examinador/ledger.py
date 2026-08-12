"""What the Examiner produced: cells, blanks, questions.

The ledger is a notebook, not a referee. It records what the model wrote, the
citation it gave and the confidence it declared, in the order it decided them.
It does not check that a citation resolves, that a value is plausible, that a
reason comes from a vocabulary, or that a cell was allowed to be written. Every
one of those checks used to live in code; here they are the Conferente's and the
Promotor's job, and in round 1 they are simply absent — which is the measurement.

One thing it does keep, because it is bookkeeping and not judgement: when the
same cell is written twice, both writes are kept in order, and the last one is
what reaches the workbook. A model that changed its mind should leave a visible
trail of having done so.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Citation:
    documento: str
    pagina: Any
    trecho: str

    def to_dict(self) -> dict[str, Any]:
        return {"documento": self.documento, "pagina": self.pagina,
                "trecho": self.trecho}

    def render(self) -> str:
        page = f" p.{self.pagina}" if self.pagina not in (None, "") else ""
        return f"{self.documento}{page}"


@dataclass
class CellWrite:
    aba: str
    celula: str
    valor: Any
    citacao: Citation
    confianca: str
    at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {"aba": self.aba, "celula": self.celula, "valor": self.valor,
                "citacao": self.citacao.to_dict(), "confianca": self.confianca,
                "quando": self.at}


@dataclass
class BlankRecord:
    aba: str
    celula: str
    motivo: str
    dono: str
    at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {"aba": self.aba, "celula": self.celula, "motivo": self.motivo,
                "dono": self.dono, "quando": self.at}


@dataclass
class Question:
    pergunta: str
    candidatos: list[str]
    o_que_desempataria: str
    at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {"pergunta": self.pergunta, "candidatos": self.candidatos,
                "o_que_desempataria": self.o_que_desempataria, "quando": self.at}


class Ledger:
    def __init__(self) -> None:
        self.cells: list[CellWrite] = []
        self.blanks: list[BlankRecord] = []
        self.questions: list[Question] = []

    def write_cell(self, aba: str, celula: str, valor: Any,
                   documento: str, pagina: Any, trecho: str,
                   confianca: str) -> dict[str, Any]:
        write = CellWrite(aba=aba, celula=str(celula).upper(), valor=valor,
                          citacao=Citation(documento, pagina, trecho),
                          confianca=confianca)
        self.cells.append(write)
        previous = [c for c in self.cells[:-1]
                    if (c.aba, c.celula) == (write.aba, write.celula)]
        return {"gravado": f"{aba}!{write.celula}",
                "reescreveu": len(previous) or None}

    def record_blank(self, aba: str, celula: str, motivo: str,
                     dono: str) -> dict[str, Any]:
        self.blanks.append(BlankRecord(aba=aba, celula=str(celula).upper(),
                                       motivo=motivo, dono=dono))
        return {"branco_registrado": f"{aba}!{str(celula).upper()}"}

    def flag_for_human(self, pergunta: str, candidatos: list[str] | None,
                       o_que_desempataria: str) -> dict[str, Any]:
        self.questions.append(Question(pergunta=pergunta,
                                       candidatos=list(candidatos or []),
                                       o_que_desempataria=o_que_desempataria))
        return {"perguntas_na_fila": len(self.questions)}

    # --- what reaches the workbook ---------------------------------------
    def final_cells(self) -> dict[tuple[str, str], CellWrite]:
        out: dict[tuple[str, str], CellWrite] = {}
        for cell in self.cells:
            out[(cell.aba, cell.celula)] = cell
        return out

    def counts(self) -> dict[str, int]:
        return {"escritas": len(self.cells),
                "celulas_distintas": len(self.final_cells()),
                "brancos": len(self.blanks),
                "perguntas": len(self.questions)}

    def to_dict(self) -> dict[str, Any]:
        return {"contagens": self.counts(),
                "celulas": [c.to_dict() for c in self.cells],
                "brancos": [b.to_dict() for b in self.blanks],
                "perguntas": [q.to_dict() for q in self.questions]}

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path
