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


# Writes and blanks are one stream of actions, not two lists. The model cleared
# surplus template rows and then wrote its own values into them; replaying all
# writes and then all blanks reverses that and erases the work. `seq` is what
# makes the order unambiguous — timestamps land on the same second constantly.
@dataclass
class CellWrite:
    aba: str
    celula: str
    valor: Any
    citacao: Citation
    confianca: str
    at: str = field(default_factory=_now)
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"aba": self.aba, "celula": self.celula, "valor": self.valor,
                "citacao": self.citacao.to_dict(), "confianca": self.confianca,
                "quando": self.at, "seq": self.seq}


@dataclass
class BlankRecord:
    aba: str
    celula: str
    motivo: str
    dono: str
    at: str = field(default_factory=_now)
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"aba": self.aba, "celula": self.celula, "motivo": self.motivo,
                "dono": self.dono, "quando": self.at, "seq": self.seq}


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
        self._seq = 0

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def write_cell(self, aba: str, celula: str, valor: Any,
                   documento: str, pagina: Any, trecho: str,
                   confianca: str) -> dict[str, Any]:
        write = CellWrite(aba=aba, celula=str(celula).upper(), valor=valor,
                          citacao=Citation(documento, pagina, trecho),
                          confianca=confianca, seq=self._next())
        self.cells.append(write)
        previous = [c for c in self.cells[:-1]
                    if (c.aba, c.celula) == (write.aba, write.celula)]
        return {"gravado": f"{aba}!{write.celula}",
                "reescreveu": len(previous) or None}

    def record_blank(self, aba: str, celula: str, motivo: str,
                     dono: str) -> dict[str, Any]:
        self.blanks.append(BlankRecord(aba=aba, celula=str(celula).upper(),
                                       motivo=motivo, dono=dono,
                                       seq=self._next()))
        return {"branco_registrado": f"{aba}!{str(celula).upper()}"}

    def flag_for_human(self, pergunta: str, candidatos: list[str] | None,
                       o_que_desempataria: str) -> dict[str, Any]:
        self.questions.append(Question(pergunta=pergunta,
                                       candidatos=list(candidatos or []),
                                       o_que_desempataria=o_que_desempataria))
        return {"perguntas_na_fila": len(self.questions)}

    # --- what reaches the workbook ---------------------------------------
    def actions(self) -> list[CellWrite | BlankRecord]:
        """Writes and blanks in the order the model took them.

        Where `seq` is missing — a ledger flushed before it existed — the
        timestamp orders them, and a write beats a blank of the same second.
        That tie-break is declared rather than silent: it is the only place the
        replay guesses, and it guesses in favour of a value the model sourced
        over an erasure it may have made first."""
        stream = list(self.cells) + list(self.blanks)
        if all(a.seq for a in stream):
            return sorted(stream, key=lambda a: a.seq)
        return sorted(stream, key=lambda a: (a.at,
                                             isinstance(a, BlankRecord) and 0 or 1))

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

    @classmethod
    def load(cls, path: str | Path) -> "Ledger":
        """Rebuild from the per-turn flush.

        The flush exists so a run of several hours is not lost to a crash after
        the last model token is paid for — which is exactly what happened on the
        first full round. Reading it back is how the artefacts get produced
        without buying the conversation twice."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        led = cls()
        for c in data.get("celulas", []):
            cite = c.get("citacao") or {}
            led.cells.append(CellWrite(
                aba=c["aba"], celula=c["celula"], valor=c.get("valor"),
                citacao=Citation(cite.get("documento", ""), cite.get("pagina"),
                                 cite.get("trecho", "")),
                confianca=c.get("confianca", ""), at=c.get("quando", ""),
                seq=int(c.get("seq") or 0)))
        for b in data.get("brancos", []):
            led.blanks.append(BlankRecord(
                aba=b["aba"], celula=b["celula"], motivo=b.get("motivo", ""),
                dono=b.get("dono", ""), at=b.get("quando", ""),
                seq=int(b.get("seq") or 0)))
        led._seq = max([a.seq for a in led.cells + led.blanks] or [0])
        for q in data.get("perguntas", []):
            led.questions.append(Question(
                pergunta=q.get("pergunta", ""),
                candidatos=list(q.get("candidatos") or []),
                o_que_desempataria=q.get("o_que_desempataria", ""),
                at=q.get("quando", "")))
        return led

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path
