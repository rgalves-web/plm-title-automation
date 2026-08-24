"""O Triador — a cabeça barata que faz o mapa do corpus (Etapa F2).

Papel da ARQUITETURA §6 nunca implementado até 24/08: uma sessão de modelo
pequeno (`MINORH_MODELO_TRIADOR`, default Haiku) rotula cada documento do
corpus — rótulo + uma linha + confiança — majoritariamente pelo NOME, abrindo
página só quando o nome não basta. O Examinador (Opus) recebe o mapa e decide
o que abrir. Continua IA decidindo tudo; só muda o preço da cabeça em cada
papel.

O mapa vive em `_minorh/triagem.json` (plumbing de armazenamento). Nenhuma
linha daqui julga title: rótulo é inventário, não conclusão.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.examinador.loop import run_loop

MODELO_TRIADOR_DEFAULT = "claude-haiku-4-5-20251001"

FERRAMENTAS_TRIADOR: list[dict[str, Any]] = [
    {
        "name": "rotular_documentos",
        "description": (
            "Rotula VARIOS documentos numa chamada. Para cada um: rotulo "
            "curto (ex. lease-ogl, lease-memo, title-opinion, dpu, "
            "assignment, well-file, planilha-projeto, recibo, "
            "correspondencia, screenshot, outro), resumo de UMA linha e "
            "confianca. Rotule pelo NOME quando ele basta; abra a pagina 1 "
            "em modo texto so quando nao basta."),
        "input_schema": {"type": "object", "properties": {
            "rotulos": {"type": "array", "items": {
                "type": "object", "properties": {
                    "documento": {"type": "string"},
                    "rotulo": {"type": "string"},
                    "resumo": {"type": "string"},
                    "confianca": {"type": "string",
                                  "enum": ["alta", "media", "baixa"]}},
                "required": ["documento", "rotulo", "resumo", "confianca"]}}},
            "required": ["rotulos"]},
    },
]

SISTEMA_TRIADOR = """Voce e o TRIADOR de um corpus de due diligence. Seu
trabalho e o MAPA, nao o julgamento: rotular cada documento para que o
Examinador saiba o que existe e abra so o necessario.

Regras:
1. Rotule TODOS os documentos da lista. `rotular_documentos` aceita lotes —
   use lotes grandes.
2. O nome do arquivo costuma bastar (os zips de lease trazem numero e lessor;
   T#### sao title opinions; K#### sao instrumentos gravados). Abra a pagina 1
   em modo `texto` SO quando o nome nao diz o que o documento e — e marque
   confianca baixa quando nem isso resolver.
3. Rotulo e inventario, nao conclusao de title. Nada do que voce escrever
   vira celula.

Quando todos estiverem rotulados, pare de pedir ferramentas e resuma."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def modelo_triador() -> str:
    return os.environ.get("MINORH_MODELO_TRIADOR", MODELO_TRIADOR_DEFAULT)


def caminho_triagem(pasta: Path) -> Path:
    return pasta / "_minorh" / "triagem.json"


def carregar(pasta: Path) -> dict[str, dict[str, str]]:
    path = caminho_triagem(pasta)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def triar(*, pasta: Path, corpus: Any, dispatch_leitura: dict[str, Any],
          client: Any = None, max_cost_usd: float = 3.0
          ) -> tuple[dict[str, dict[str, str]], Any]:
    """Sessão do Triador sobre os documentos ainda sem rótulo."""
    triagem = carregar(pasta)
    nomes = set(corpus.names())
    pendentes = sorted(nomes - set(triagem))
    if not pendentes:
        return triagem, None

    def _rotular(rotulos: list[dict[str, str]]) -> dict[str, Any]:
        aceitos = 0
        for r in rotulos:
            if r["documento"] not in nomes:
                raise ValueError(f"{r['documento']!r} nao esta no corpus")
            triagem[r["documento"]] = {
                "rotulo": r["rotulo"], "resumo": r["resumo"],
                "confianca": r["confianca"], "quando": _now()}
            aceitos += 1
        _salvar(pasta, triagem)
        return {"rotulados": aceitos,
                "faltam": len(nomes - set(triagem))}

    dispatch = dict(dispatch_leitura)
    dispatch["rotular_documentos"] = _rotular
    from src.minorh.ship import _leitura_schemas
    ferramentas = FERRAMENTAS_TRIADOR + [
        t for t in _leitura_schemas() if t["name"] in dispatch_leitura]

    task = (f"CORPUS DA UNIDADE {pasta.name} — {len(pendentes)} documentos "
            f"sem rotulo:\n"
            + "\n".join(f"- {n}" for n in pendentes)
            + "\n\nRotule todos.")
    log, _ = run_loop(system=SISTEMA_TRIADOR, task=task, tools=ferramentas,
                      dispatch=dispatch, model=modelo_triador(),
                      max_turns=60, max_cost_usd=max_cost_usd, client=client)
    return triagem, log


def _salvar(pasta: Path, triagem: dict[str, dict[str, str]]) -> None:
    path = caminho_triagem(pasta)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(triagem, indent=1, ensure_ascii=False),
                    encoding="utf-8")


def mapa_markdown(triagem: dict[str, dict[str, str]],
                  por_rotulo_max: int = 400) -> str:
    """O mapa para o task do Examinador, agrupado por rótulo."""
    if not triagem:
        return ""
    grupos: dict[str, list[str]] = {}
    for nome, r in sorted(triagem.items()):
        grupos.setdefault(r["rotulo"], []).append(
            f"  - {nome} — {r['resumo'][:90]} [{r['confianca']}]")
    linhas = [f"MAPA DO TRIADOR ({len(triagem)} documentos, por rótulo):"]
    for rotulo, itens in sorted(grupos.items()):
        linhas.append(f"- {rotulo} ({len(itens)}):")
        linhas.extend(itens[:por_rotulo_max])
        if len(itens) > por_rotulo_max:
            linhas.append(f"  … e mais {len(itens) - por_rotulo_max}")
    return "\n".join(linhas)
