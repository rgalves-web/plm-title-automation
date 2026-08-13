"""A memória da unidade — fichas por entidade, campo a campo.

O modelo não escreve mais direto na célula: trabalha aqui, e o DDR é projeção
disto no `ship`. Cada campo é uma de três coisas, sempre explícitas:

  ESCRITO    valor + citação literal (documento, página, trecho) + confiança;
  BRANCO     motivo + dono do trabalho que o motivo cria;
  PENDENTE   espera um documento que um item de PEDIDOS.md descreve.

Este módulo guarda e conta. Não valida valor, não confere citação, não julga
motivo — quem decide o conteúdo é o modelo, e quem confere é o auditor do ship.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Campo:
    estado: str                     # escrito | branco | pendente
    valor: str = ""
    documento: str = ""
    pagina: Any = None
    trecho: str = ""
    confianca: str = ""
    motivo: str = ""
    dono: str = ""
    pedido: str = ""                # id do item de PEDIDOS.md que o espera
    quando: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Memoria:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.entidades: dict[str, dict[str, Campo]] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for ent, campos in raw.get("entidades", {}).items():
                self.entidades[ent] = {
                    nome: Campo(**spec) for nome, spec in campos.items()}

    # --- as três operações do modelo --------------------------------------
    def gravar(self, entidade: str, campo: str, valor: str, documento: str,
               pagina: Any, trecho: str, confianca: str) -> dict[str, Any]:
        anterior = self.entidades.get(entidade, {}).get(campo)
        self.entidades.setdefault(entidade, {})[campo] = Campo(
            estado="escrito", valor=valor, documento=documento, pagina=pagina,
            trecho=trecho, confianca=confianca)
        self._save()
        return {"gravado": f"{entidade} :: {campo}",
                "substituiu": anterior.estado if anterior else None}

    def branco(self, entidade: str, campo: str, motivo: str,
               dono: str) -> dict[str, Any]:
        self.entidades.setdefault(entidade, {})[campo] = Campo(
            estado="branco", motivo=motivo, dono=dono)
        self._save()
        return {"branco": f"{entidade} :: {campo}"}

    def pendente(self, entidade: str, campo: str, pedido: str) -> None:
        # Um campo já escrito não regride a pendente por causa de um pedido
        # amplo — o valor provado fica.
        atual = self.entidades.get(entidade, {}).get(campo)
        if atual is not None and atual.estado == "escrito":
            return
        self.entidades.setdefault(entidade, {})[campo] = Campo(
            estado="pendente", pedido=pedido)
        self._save()

    # --- contagem e projeção ----------------------------------------------
    def contar(self) -> dict[str, int]:
        out = {"escritos": 0, "brancos": 0, "pendentes": 0}
        for campos in self.entidades.values():
            for c in campos.values():
                out[{"escrito": "escritos", "branco": "brancos",
                     "pendente": "pendentes"}[c.estado]] += 1
        return out

    def dump(self) -> dict[str, Any]:
        return {"entidades": {
            ent: {nome: c.to_dict() for nome, c in campos.items()}
            for ent, campos in sorted(self.entidades.items())}}

    def dump_markdown(self) -> str:
        """A memória inteira, legível para a sessão de projeção do ship."""
        lines: list[str] = []
        for ent, campos in sorted(self.entidades.items()):
            lines.append(f"\n### {ent}")
            for nome, c in sorted(campos.items()):
                if c.estado == "escrito":
                    lines.append(
                        f"- {nome} = {c.valor!r}  [{c.documento} p.{c.pagina} "
                        f"— {c.trecho[:80]!r}] (confiança {c.confianca})")
                elif c.estado == "branco":
                    lines.append(f"- {nome} = BRANCO — motivo: {c.motivo} — "
                                 f"dono: {c.dono}")
                else:
                    lines.append(f"- {nome} = PENDENTE — aguarda documento "
                                 f"(pedido {c.pedido})")
        return "\n".join(lines)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.dump(), indent=2, ensure_ascii=False),
            encoding="utf-8")
