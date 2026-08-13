"""Os comandos. Cada um termina imprimindo os três números e o custo real.

    minorh unidade "<pasta>"   abre a unidade: censo, memória, PEDIDOS, PERGUNTAS
    minorh continuar           só o que é novo em FILES/ + respostas do operador
    minorh estado              os números, sem chamada de modelo
    minorh perguntas           as perguntas, sem chamada de modelo
    minorh ship                projeção + auditoria de 100% + kit

Este arquivo não contém juízo de title: monta sessões, injeta ferramentas,
persiste o que o modelo fez e imprime contagens.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from src.examinador.cache import PageCache
from src.examinador.corpus import Corpus
from src.examinador.loop import Usage, run_loop
from src.examinador.okf import KnowledgeBase
from src.minorh.arquivos import (escrever_pedidos, escrever_perguntas,
                                 ler_respostas)
from src.minorh.estado import PASTA_ESTADO, Estado
from src.minorh.ferramentas import FERRAMENTAS, montar_dispatch
from src.minorh.memoria import Memoria

MODELO = os.environ.get("MINORH_MODELO", "claude-opus-5")
ULTIMA = Path.home() / ".minorh_ultima"

SISTEMA = """Voce e o landman responsavel por esta unidade. O trabalho e seu e
o entregavel sai com o seu nome.

A PRIMEIRA coisa ao abrir a unidade e o CENSO (`declarar_censo`): quantas
leases o registro declara (Exhibit "A" da DPU), quantos tratos (Exhibit "C"),
quantos pocos, e — do cabecalho de cada aba do template — quantos campos cada
linha exige. O censo e o denominador: sem ele, "terminei" e opiniao. Se um
documento novo mudar a conta, declare de novo.

Voce NAO escreve celulas agora. Trabalha na MEMORIA da unidade:

  gravar_campo      valor + citacao literal (documento, pagina, trecho)
  declarar_branco   motivo + dono, quando o registro nao diz
  pedir_documento   quando falta documento — vira item de PEDIDOS.md e os
                    campos ficam PENDENTES
  perguntar         quando so o operador resolve — vira PERGUNTAS.md

O DDR sera projetado da memoria no `ship`, e cada celula sera auditada por
outro modelo que reabre a pagina citada. Um campo cuja citacao nao sustenta o
valor vai ser reprovado la — entao a citacao e literal ou o campo e branco.

O que valer alem desta unidade (formularios, cadeias, layouts, licoes de
custo), grave com write_knowledge escopo `global`. Sao 300 unidades do mesmo
projeto: o que voce le uma vez, as outras consultam.

Regra de sempre: branco declarado e melhor que numero plausivel. Quem recebe
este relatorio toma decisao de milhoes com ele."""


# --------------------------------------------------------------------------
# infra por unidade
# --------------------------------------------------------------------------

def _abrir(pasta: Path) -> dict[str, Any]:
    files = pasta / "FILES"
    corpus = Corpus(files if files.is_dir() else pasta, cache=PageCache())
    estado = Estado(pasta)
    memoria = Memoria(pasta / PASTA_ESTADO / "memoria.json")
    kb_unidade = KnowledgeBase(pasta / PASTA_ESTADO / "fichas")
    kb_global = KnowledgeBase()
    return {"pasta": pasta, "corpus": corpus, "estado": estado,
            "memoria": memoria, "kb_unidade": kb_unidade,
            "kb_global": kb_global}


def _template_de(pasta: Path) -> Path:
    proprio = pasta / "template.xlsx"
    if proprio.exists():
        return proprio
    from src.examinador.run import TEMPLATE
    if TEMPLATE.exists():
        return TEMPLATE
    raise SystemExit(f"sem template: nem {proprio} nem o template da casa.")


def _numeros(ctx: dict[str, Any]) -> str:
    n = ctx["estado"].censo.get("exige")
    c = ctx["memoria"].contar()
    return (f"exige {n if n is not None else '?'} · "
            f"escrevi {c['escritos']} (com citação) · "
            f"branco declarado {c['brancos']} (motivo e dono) · "
            f"pendente de documento {c['pendentes']}")


def _imprimir_fecho(ctx: dict[str, Any], comando: str,
                    uso: dict[str, Any] | None) -> None:
    print()
    print(_numeros(ctx))
    if uso:
        ctx["estado"].registrar_execucao(comando, uso)
        print(f"custo desta execução: ${uso.get('custo_usd')} "
              f"(entrada_total {uso.get('entrada_total')} · "
              f"saída {uso.get('saida')} · cache escrita "
              f"{uso.get('cache_escrita')} · cache leitura "
              f"{uso.get('cache_leitura')})")
    total = ctx["estado"].custo_acumulado()
    print(f"acumulado da unidade: ${total['custo_usd']}")


def _sessao(ctx: dict[str, Any], task: str, comando: str,
            max_cost: float, client: Any = None) -> dict[str, Any]:
    dispatch = montar_dispatch(ctx["corpus"], ctx["kb_unidade"],
                               ctx["kb_global"], ctx["memoria"],
                               ctx["estado"])
    progresso = ctx["pasta"] / PASTA_ESTADO / f"progresso_{comando}.jsonl"
    progresso.parent.mkdir(parents=True, exist_ok=True)

    def flush(rec: Any) -> None:
        with progresso.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"turno": rec.turn, "chamadas": [c["tool"] for c in rec.calls],
                 "uso": rec.usage, "texto": rec.text[:300]},
                ensure_ascii=False) + "\n")

    log, _ = run_loop(system=SISTEMA, task=task, tools=FERRAMENTAS,
                      dispatch=dispatch, model=MODELO, max_turns=250,
                      max_cost_usd=max_cost, on_turn=flush, client=client)
    (ctx["pasta"] / PASTA_ESTADO / f"log_{comando}.json").write_text(
        json.dumps(log.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8")
    if "INCOMPLETA" in log.stop_reason:
        print(f"ATENÇÃO: {log.stop_reason}")
    return log.usage.to_dict(MODELO)


# --------------------------------------------------------------------------
# comandos
# --------------------------------------------------------------------------

def cmd_unidade(pasta: Path, client: Any = None) -> None:
    ctx = _abrir(pasta)
    if ctx["estado"].existe:
        print(f"{pasta} já foi aberta — use `minorh continuar`.")
        _imprimir_fecho(ctx, "unidade", None)
        return
    ULTIMA.write_text(str(pasta.resolve()), encoding="utf-8")

    from src.examinador.run import template_map
    template = _template_de(pasta)
    task = (
        f"UNIDADE: {pasta.name}\n\n"
        f"O corpus está nas ferramentas ({len(ctx['corpus'].names())} "
        f"documentos em FILES/).\n\n"
        f"MAPA DO TEMPLATE do entregável, célula a célula:\n"
        f"{template_map(template)}\n\n"
        "Abra a unidade: declare o censo, leia o que o corpus tem, grave a "
        "memória campo a campo, peça o que falta, pergunte o que só o "
        "operador resolve. Quando o que há de legível estiver na memória, "
        "pare de pedir ferramentas e resuma.")
    uso = _sessao(ctx, task, "unidade",
                  float(os.environ.get("MINORH_TETO_USD", "40")), client)

    escrever_pedidos(ctx["estado"])
    escrever_perguntas(ctx["estado"])
    _imprimir_fecho(ctx, "unidade", uso)


def cmd_continuar(pasta: Path, client: Any = None) -> None:
    ctx = _abrir(pasta)
    if not ctx["estado"].existe:
        raise SystemExit(f"{pasta} nunca foi aberta — use `minorh unidade`.")

    antes = {"censo": ctx["estado"].censo.get("exige"),
             **ctx["memoria"].contar()}
    novos = ctx["estado"].novos_documentos(ctx["corpus"])
    respostas = ler_respostas(ctx["estado"])
    if not novos and not respostas:
        print("nada novo: nenhum documento inédito em FILES/ e nenhuma "
              "resposta nova em PERGUNTAS.md.")
        _imprimir_fecho(ctx, "continuar", None)
        return

    partes = [f"UNIDADE: {pasta.name} — continuação. NÃO releia o que já "
              f"está na memória; trabalhe só no que segue."]
    if novos:
        partes.append("DOCUMENTOS NOVOS EM FILES/ (nunca abertos):\n"
                      + "\n".join(f"- {n}" for n in novos))
    if respostas:
        partes.append(
            "RESPOSTAS DO OPERADOR EM PERGUNTAS.md:\n" + "\n".join(
                f"- [{r['id']}] {r['pergunta']}\n  RESPOSTA: {r['resposta']}"
                for r in respostas))
        partes.append(
            "Para cada resposta: aplique-a na memória e grave-a como "
            "precedente (write_knowledge, escopo global, tipo veredito) — "
            "ela vale para as próximas unidades.")
    partes.append(
        "Se um documento novo destravar campos PENDENTES, grave-os. Se a "
        "conta do censo mudar, declare o censo de novo. Ao final, pare e "
        "resuma o delta.")
    uso = _sessao(ctx, "\n\n".join(partes), "continuar",
                  float(os.environ.get("MINORH_TETO_USD", "25")), client)

    for r in respostas:
        ctx["estado"].responder(r["id"], r["resposta"])
    escrever_pedidos(ctx["estado"])
    escrever_perguntas(ctx["estado"])

    depois = {"censo": ctx["estado"].censo.get("exige"),
              **ctx["memoria"].contar()}
    print(f"\ndelta: censo {antes['censo']} → {depois['censo']} · "
          f"escritos {antes['escritos']} → {depois['escritos']} · "
          f"pendentes {antes['pendentes']} → {depois['pendentes']} · "
          f"documentos novos processados: {len(novos)} · "
          f"respostas processadas: {len(respostas)}")
    _imprimir_fecho(ctx, "continuar", uso)


def cmd_estado(pasta: Path) -> None:
    ctx = _abrir(pasta)
    if not ctx["estado"].existe:
        raise SystemExit(f"{pasta} nunca foi aberta — use `minorh unidade`.")
    e = ctx["estado"]
    print(f"unidade: {pasta}")
    print(f"documentos no corpus: {len(ctx['corpus'].names())} · "
          f"já lidos: {len(e.lidos)}")
    print(f"pedidos abertos: "
          f"{sum(1 for p in e.pedidos if p['status'] == 'aberto')} · "
          f"perguntas abertas: {len(e.perguntas_abertas())}")
    print(f"execuções: {len(e.execucoes)}")
    _imprimir_fecho(ctx, "estado", None)


def cmd_perguntas(pasta: Path) -> None:
    ctx = _abrir(pasta)
    for q in ctx["estado"].perguntas:
        print(f"[{q['id']}] ({q['status']}) {q['pergunta']}")
        if q["resposta"]:
            print(f"    resposta: {q['resposta']}")
    if not ctx["estado"].perguntas:
        print("nenhuma pergunta.")
    _imprimir_fecho(ctx, "perguntas", None)


def cmd_ship(pasta: Path, client: Any = None) -> None:
    from src.minorh import ship as s
    from src.minorh.auditor import Auditor

    ctx = _abrir(pasta)
    if not ctx["estado"].existe:
        raise SystemExit(f"{pasta} nunca foi aberta — use `minorh unidade`.")
    template = _template_de(pasta)
    uso_total = Usage()

    dispatch_leitura = {
        nome: fn for nome, fn in montar_dispatch(
            ctx["corpus"], ctx["kb_unidade"], ctx["kb_global"],
            ctx["memoria"], ctx["estado"]).items()
        if nome in ("read_page", "read_knowledge", "list_documents",
                    "search_corpus")}

    print("1/3 projeção: a memória vira DDR…")
    ledger, log1 = s.projetar(
        pasta=pasta, memoria=ctx["memoria"], template=template, modelo=MODELO,
        dispatch_leitura=dispatch_leitura, client=client)
    uso_total.input += log1.usage.input
    uso_total.output += log1.usage.output
    uso_total.cache_write += log1.usage.cache_write
    uso_total.cache_read += log1.usage.cache_read

    ship_dir = pasta / PASTA_ESTADO / "ship"
    ship_dir.mkdir(parents=True, exist_ok=True)
    ddr = s.write_workbook(ledger, ship_dir / "DDR.xlsx", template=template)

    print("2/3 auditoria de 100% das células escritas…")
    auditor = Auditor.escolher()
    if auditor.limitacao:
        print(f"   {auditor.limitacao}")
    vereditos, contagem = s.auditar_tudo(
        unidade=pasta.name, workbook=ddr, ledger=ledger,
        corpus=ctx["corpus"], auditor=auditor)
    rodadas = 1
    reprovadas = s.reprovadas_de(vereditos)
    historico_rodada_1 = list(reprovadas)
    print(f"   rodada 1: {contagem['auditadas']} auditadas, "
          f"{len(reprovadas)} reprovadas"
          + (": " + ", ".join(v.celula for v in reprovadas)
             if reprovadas else ""))

    if reprovadas:
        marcador = len(ledger.cells)
        log2 = s.corrigir(pasta=pasta, ledger=ledger, reprovadas=reprovadas,
                          modelo=MODELO, dispatch_leitura=dispatch_leitura,
                          client=client)
        uso_total.input += log2.usage.input
        uso_total.output += log2.usage.output
        uso_total.cache_write += log2.usage.cache_write
        uso_total.cache_read += log2.usage.cache_read
        ddr = s.write_workbook(ledger, ship_dir / "DDR.xlsx",
                               template=template)
        alvo = ({v.celula for v in reprovadas}
                | {f"{c.aba}!{c.celula}" for c in ledger.cells[marcador:]})
        segunda, _ = s.auditar_tudo(
            unidade=pasta.name, workbook=ddr, ledger=ledger,
            corpus=ctx["corpus"], auditor=auditor, apenas=alvo)
        rodadas = 2
        por_celula = {v.celula: v for v in vereditos}
        for v in segunda:
            por_celula[v.celula] = v
        vereditos = list(por_celula.values())
        ainda = s.reprovadas_de(segunda)
        print(f"   rodada 2: {len(segunda)} reauditadas, "
              f"{len(ainda)} seguem reprovadas")
        if ainda:
            removidas = s.aplicar_regra_de_embarque(ledger, ainda)
            ddr = s.write_workbook(ledger, ship_dir / "DDR.xlsx",
                                   template=template)
            print(f"   REGRA DE EMBARQUE: {len(removidas)} célula(s) "
                  f"rebaixada(s) a branco declarado: {', '.join(removidas)}")

    print("3/3 kit…")
    caminhos = s.escrever_kit(
        pasta=pasta, ledger=ledger, template=template, vereditos=vereditos,
        contagem=contagem, auditor=auditor, memoria=ctx["memoria"],
        estado=ctx["estado"], rodadas_auditoria=rodadas,
        historico_rodada_1=historico_rodada_1)
    for nome, caminho in caminhos.items():
        print(f"   {nome}: {caminho}")

    uso = uso_total.to_dict(MODELO)
    uso_auditor = auditor.uso.to_dict(auditor.modelo)
    if uso.get("custo_usd") is not None and \
            uso_auditor.get("custo_usd") is not None:
        uso["custo_usd"] = round(uso["custo_usd"]
                                 + uso_auditor["custo_usd"], 4)
    print(f"   auditor ({auditor.provedor}/{auditor.modelo}): "
          f"{uso_auditor}")
    _imprimir_fecho(ctx, "ship", uso)


# --------------------------------------------------------------------------

def _pasta_de(args: list[str]) -> Path:
    if args:
        return Path(args[0])
    if ULTIMA.exists():
        return Path(ULTIMA.read_text(encoding="utf-8").strip())
    raise SystemExit("qual unidade? `minorh <comando> \"<pasta>\"` na "
                     "primeira vez.")


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return
    comando, resto = args[0], args[1:]
    if comando == "unidade":
        if not resto:
            raise SystemExit('uso: minorh unidade "<pasta da unidade>"')
        cmd_unidade(Path(resto[0]))
    elif comando == "continuar":
        pasta = _pasta_de(resto)
        ULTIMA.write_text(str(pasta.resolve()), encoding="utf-8")
        cmd_continuar(pasta)
    elif comando == "estado":
        cmd_estado(_pasta_de(resto))
    elif comando == "perguntas":
        cmd_perguntas(_pasta_de(resto))
    elif comando == "ship":
        cmd_ship(_pasta_de(resto))
    else:
        raise SystemExit(f"comando desconhecido: {comando!r}. "
                         f"Comandos: unidade, continuar, estado, perguntas, "
                         f"ship.")
