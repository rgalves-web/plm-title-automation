"""O estado persistente da unidade — o que sobrevive entre comandos.

Censo declarado pelo modelo, documentos já lidos (por hash do conteúdo),
pedidos emitidos, perguntas pendentes, custo acumulado. `continuar` parte
daqui: nada se relê, nada se perde.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PASTA_ESTADO = "_minorh"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Estado:
    def __init__(self, unidade: str | Path) -> None:
        self.unidade = Path(unidade)
        self.dir = self.unidade / PASTA_ESTADO
        self.path = self.dir / "estado.json"
        data: dict[str, Any] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        self.censo: dict[str, Any] = data.get("censo", {})
        self.lidos: dict[str, dict[str, str]] = data.get("lidos", {})
        self.pedidos: list[dict[str, Any]] = data.get("pedidos", [])
        self.perguntas: list[dict[str, Any]] = data.get("perguntas", [])
        self.execucoes: list[dict[str, Any]] = data.get("execucoes", [])
        self.horas: list[dict[str, Any]] = data.get("horas", [])

    @property
    def existe(self) -> bool:
        return self.path.exists()

    # --- censo --------------------------------------------------------------
    def declarar_censo(self, exige: int, resumo: str) -> None:
        self.censo = {"exige": int(exige), "resumo": resumo, "quando": _now()}
        self.save()

    # --- leitura por hash ---------------------------------------------------
    @staticmethod
    def hash_de(dados: bytes) -> str:
        return hashlib.sha256(dados).hexdigest()[:32]

    def marcar_lido(self, documento: str, digest: str) -> None:
        self.lidos[digest] = {"documento": documento, "quando": _now()}

    def novos_documentos(self, corpus: Any) -> list[str]:
        """Documentos cujo CONTEÚDO nunca foi aberto — por hash, não por nome.

        Um arquivo renomeado não é novo; um arquivo substituído é."""
        out = []
        for nome in corpus.names():
            try:
                digest = self.hash_de(corpus.read_bytes(nome))
            except Exception:
                continue
            if digest not in self.lidos:
                out.append(nome)
        return out

    # --- pedidos e perguntas ------------------------------------------------
    def novo_pedido(self, titulo: str, o_que: str, onde: str, metodo: str,
                    campos: list[dict[str, str]]) -> str:
        pid = f"PED-{len(self.pedidos) + 1:03d}"
        self.pedidos.append({"id": pid, "titulo": titulo, "o_que": o_que,
                             "onde": onde, "metodo": metodo,
                             "campos": campos, "status": "aberto",
                             "quando": _now()})
        self.save()
        return pid

    def nova_pergunta(self, pergunta: str, candidatos: list[str],
                      desempate: str) -> str:
        qid = f"P{len(self.perguntas) + 1}"
        self.perguntas.append({"id": qid, "pergunta": pergunta,
                               "candidatos": candidatos,
                               "desempate": desempate, "resposta": "",
                               "status": "aberta", "quando": _now()})
        self.save()
        return qid

    def perguntas_abertas(self) -> list[dict[str, Any]]:
        return [q for q in self.perguntas if q["status"] == "aberta"]

    def responder(self, qid: str, resposta: str) -> None:
        for q in self.perguntas:
            if q["id"] == qid:
                q["resposta"] = resposta
                q["status"] = "respondida"
        self.save()

    # --- horas do operador --------------------------------------------------
    # A medida do negócio (meta: ≤ 1h/unit, doc governante §3). Plumbing puro:
    # grava o que o operador declarou, soma, nada mais.
    def registrar_horas(self, horas: float, nota: str = "") -> None:
        self.horas.append({"horas": float(horas), "nota": nota,
                           "quando": _now()})
        self.save()

    def horas_acumuladas(self) -> float:
        return round(sum(float(h.get("horas") or 0) for h in self.horas), 2)

    # --- custo --------------------------------------------------------------
    def registrar_execucao(self, comando: str, uso: dict[str, Any]) -> None:
        self.execucoes.append({"comando": comando, "quando": _now(),
                               "uso": uso})
        self.save()

    def custo_acumulado(self) -> dict[str, Any]:
        total = {"entrada": 0, "saida": 0, "cache_escrita": 0,
                 "cache_leitura": 0, "custo_usd": 0.0}
        for e in self.execucoes:
            uso = e.get("uso") or {}
            for k in total:
                total[k] = round(total[k] + (uso.get(k) or 0), 4)
        return total

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "unidade": str(self.unidade), "censo": self.censo,
            "lidos": self.lidos, "pedidos": self.pedidos,
            "perguntas": self.perguntas, "execucoes": self.execucoes,
            "horas": self.horas,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
