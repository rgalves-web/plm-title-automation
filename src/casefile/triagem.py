"""A triagem do casefile — a cabeça barata rotula o censo, no banco.

Padrão copiado de src/minorh/triador.py (sistema, schema de lote, disciplina
nome-antes-de-página), com duas diferenças: os rótulos persistem em
`triage_labels` (por sha256, não por nome — renomear não re-rotula) e a sessão
entra em `model_sessions`/`cost_entries` como qualquer outra. Rótulo é
inventário, não conclusão de title.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.casefile import sessao
from src.casefile.acervo import _norm

MODELO_TRIAGEM_DEFAULT = "claude-haiku-4-5-20251001"

FERRAMENTAS_TRIAGEM: list[dict[str, Any]] = [
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
                "required": ["documento", "rotulo", "resumo",
                             "confianca"]}}},
            "required": ["rotulos"]},
    },
]

SISTEMA_TRIAGEM = """Voce e o TRIADOR de um corpus de due diligence. Seu
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


def modelo_triagem() -> str:
    return os.environ.get("CASEFILE_MODELO_TRIAGEM",
                          os.environ.get("MINORH_MODELO_TRIADOR",
                                         MODELO_TRIAGEM_DEFAULT))


def triar(*, repo: Any, unit: dict[str, Any], pasta: Path, acervo: Any,
          dispatch_leitura: dict[str, Any], client: Any = None,
          max_cost_usd: float = 3.0) -> tuple[int, Any]:
    """Rotula os conteúdos do acervo ainda sem rótulo; devolve (novos, log)."""
    sha_por_nome = repo.sha_por_nome(unit["id"])
    rotulados = set(repo.rotulos(unit["id"]))
    pendentes = sorted(
        nome for nome in acervo.names()
        if any(sha not in rotulados
               for sha in sha_por_nome.get(nome, ["?"])))
    if not pendentes:
        return 0, None

    session_ref: dict[str, Any] = {"id": None}
    novos = {"n": 0}

    def _rotular(rotulos: list[dict[str, str]]) -> dict[str, Any]:
        for r in rotulos:
            nome = _norm(r["documento"])
            hashes = sha_por_nome.get(nome, [])
            if not hashes:
                raise ValueError(f"{r['documento']!r} nao esta no censo")
            # Nome com dois conteúdos distintos: o rótulo vale para ambos —
            # a ambiguidade já é fato nomeado do censo, não da triagem.
            for sha in hashes:
                sid = repo.source_file_id_por_sha(sha)
                repo.gravar_rotulo(sid, unit["id"], r["rotulo"], r["resumo"],
                                   r["confianca"], session_ref["id"])
                if sha not in rotulados:
                    rotulados.add(sha)
                    novos["n"] += 1
        faltam = sum(1 for n in pendentes
                     if any(s not in rotulados
                            for s in sha_por_nome.get(n, [])))
        return {"rotulados": len(rotulos), "faltam": faltam}

    dispatch = dict(dispatch_leitura)
    dispatch["rotular_documentos"] = _rotular
    from src.casefile.ferramentas import FERRAMENTAS_LEITURA
    ferramentas = FERRAMENTAS_TRIAGEM + [
        t for t in FERRAMENTAS_LEITURA if t["name"] in dispatch_leitura]

    task = (f"CORPUS DA UNIDADE {unit['canonical_name']} — {len(pendentes)} "
            f"documentos sem rotulo:\n"
            + "\n".join(f"- {n}" for n in pendentes)
            + "\n\nRotule todos.")
    log, _sid = sessao.rodar(
        repo=repo, unit=unit, pasta=pasta, comando="planejar.triagem",
        sistema=SISTEMA_TRIAGEM, task=task, ferramentas=ferramentas,
        dispatch=dispatch, modelo_sessao=modelo_triagem(),
        max_cost_usd=max_cost_usd, client=client, max_turns=60,
        session_ref=session_ref)
    return novos["n"], log


def mapa_markdown(rotulos_por_sha: dict[str, dict[str, str]],
                  sha_por_nome: dict[str, list[str]],
                  por_rotulo_max: int = 400) -> str:
    """O mapa para o task do Examinador, por rótulo (padrão do triador)."""
    if not rotulos_por_sha:
        return ""
    grupos: dict[str, list[str]] = {}
    for nome, hashes in sorted(sha_por_nome.items()):
        for sha in hashes:
            r = rotulos_por_sha.get(sha)
            if r is None:
                continue
            grupos.setdefault(r["rotulo"], []).append(
                f"  - {nome} — {r['resumo'][:90]} [{r['confianca']}]")
            break
    linhas = [f"MAPA DA TRIAGEM ({len(rotulos_por_sha)} conteudos, "
              f"por rotulo):"]
    for rotulo, itens in sorted(grupos.items()):
        linhas.append(f"- {rotulo} ({len(itens)}):")
        linhas.extend(itens[:por_rotulo_max])
        if len(itens) > por_rotulo_max:
            linhas.append(f"  … e mais {len(itens) - por_rotulo_max}")
    return "\n".join(linhas)
