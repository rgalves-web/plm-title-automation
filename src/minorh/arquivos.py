"""PEDIDOS.md e PERGUNTAS.md — a fronteira com o operador.

Dois arquivos na raiz da pasta da unidade. O modelo emite itens pelas
ferramentas; este módulo só os desenha em markdown e lê de volta as respostas
que o operador escreveu. O formato é rígido de propósito: `continuar` precisa
achar a resposta sem adivinhar.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.minorh.estado import Estado

MARCADOR_RESPOSTA = "**Resposta:**"
PLACEHOLDER = "_(escreva aqui e rode `minorh continuar`)_"


def escrever_pedidos(estado: Estado) -> Path:
    """Empacotado por SENTADA (D2): itens com o mesmo `onde` saem juntos,
    para o operador resolver cada lugar numa ida só — a meta do doc
    governante é ≤ 1h de operador por unidade. Agrupar por string igual é
    plumbing; decidir o `onde` de cada item é do modelo."""
    path = estado.unidade / "PEDIDOS.md"
    abertos = [p for p in estado.pedidos if p["status"] == "aberto"]
    atendidos = [p for p in estado.pedidos if p["status"] != "aberto"]
    lines = [
        f"# PEDIDOS — {estado.unidade.name}",
        "",
        "O que falta buscar para fechar o censo. Um item por decisão,",
        "agrupado por sentada de busca — cada seção abaixo se resolve numa",
        "ida a um lugar só. Quando o documento chegar, coloque-o em `FILES/`",
        "e rode `minorh continuar` — o sistema lê só o que é novo e atualiza",
        "os números.",
        "",
    ]
    sentadas: dict[str, list[dict[str, Any]]] = {}
    for p in abertos:
        sentadas.setdefault(str(p.get("onde") or "(sem lugar)"), []).append(p)
    for onde, itens in sentadas.items():
        lines += [f"## Sentada: {onde} — {len(itens)} item(ns)", ""]
        for p in itens:
            lines += [f"### {p['id']} — {p['titulo']}",
                      f"- **O que buscar:** {p['o_que']}",
                      f"- **Onde:** {p['onde']}",
                      f"- **Método:** {p['metodo']}",
                      "- **Responde aos campos:** "
                      + "; ".join(f"{c.get('entidade')} :: {c.get('campo')}"
                                  for c in p["campos"]),
                      ""]
    if not abertos:
        lines += ["_Nenhum pedido aberto._", ""]
    if atendidos:
        lines += ["---", "## Atendidos", ""]
        lines += [f"- ~~{p['id']} — {p['titulo']}~~" for p in atendidos]
        lines += [""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def escrever_perguntas(estado: Estado) -> Path:
    path = estado.unidade / "PERGUNTAS.md"
    lines = [
        f"# PERGUNTAS — {estado.unidade.name}",
        "",
        "Dúvidas que só o operador resolve. Escreva a resposta no espaço",
        "marcado e rode `minorh continuar`: a resposta vira precedente para as",
        "próximas unidades.",
        "",
    ]
    for q in estado.perguntas:
        lines += [f"## {q['id']} — {'ABERTA' if q['status'] == 'aberta' else 'respondida'}",
                  f"**Pergunta:** {q['pergunta']}", ""]
        if q["candidatos"]:
            lines += ["**Candidatos:**"]
            lines += [f"- {c}" for c in q["candidatos"]]
            lines += [""]
        lines += [f"**O que desempataria:** {q['desempate']}", "",
                  MARCADOR_RESPOSTA,
                  q["resposta"] if q["resposta"] else PLACEHOLDER,
                  ""]
    if not estado.perguntas:
        lines += ["_Nenhuma pergunta._", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


_BLOCO = re.compile(r"^## (P\d+) — ", re.MULTILINE)


def ler_respostas(estado: Estado) -> list[dict[str, Any]]:
    """Respostas que o operador escreveu e o sistema ainda não processou."""
    path = estado.unidade / "PERGUNTAS.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    marks = list(_BLOCO.finditer(text))
    novas: list[dict[str, Any]] = []
    abertas = {q["id"]: q for q in estado.perguntas_abertas()}
    for i, m in enumerate(marks):
        qid = m.group(1)
        if qid not in abertas:
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        bloco = text[m.start():end]
        if MARCADOR_RESPOSTA not in bloco:
            continue
        resposta = bloco.split(MARCADOR_RESPOSTA, 1)[1].strip()
        resposta = re.sub(r"^_.*?_\s*$", "", resposta,
                          flags=re.MULTILINE).strip()
        if resposta:
            novas.append({"id": qid, "pergunta": abertas[qid]["pergunta"],
                          "resposta": resposta})
    return novas
