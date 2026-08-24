"""Os comandos. Cada um termina imprimindo os três números e o custo real.

    minorh unidade "<pasta>"   abre a unidade: censo, memória, PEDIDOS, PERGUNTAS
    minorh continuar           só o que é novo em FILES/ + respostas do operador
    minorh estado              os números, sem chamada de modelo
    minorh perguntas           as perguntas, sem chamada de modelo
    minorh ship                projeção + auditoria de 100% + kit de submissão
    minorh publicar            congela o kit em <UNIT>/SUBMISSION PLM/
    minorh horas <h> ["nota"]  registra horas do operador no estado
    minorh painel "<pasta-mãe>"  uma linha por unidade aberta, sem modelo

Teto duro por unidade: US$ 25 (`MINORH_TETO_UNIT_USD`). Ao bater, qualquer
comando com modelo recusa, reporta o que falta e espera ordem — nunca estoura
em silêncio (doc governante §3).

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


def _teto_unit() -> float:
    return float(os.environ.get("MINORH_TETO_UNIT_USD", "25"))


def _orcamento(ctx: dict[str, Any], teto_comando: float) -> float:
    """B4: o teto duro por unidade. Devolve o orçamento da sessão =
    min(teto_do_comando, teto_unit − acumulado); com o teto batido, recusa
    limpa — imprime o acumulado, o que está pendente e como autorizar."""
    teto = _teto_unit()
    gasto = ctx["estado"].custo_acumulado()["custo_usd"]
    if gasto < teto:
        return min(teto_comando, round(teto - gasto, 4))
    e = ctx["estado"]
    c = ctx["memoria"].contar()
    pedidos = sum(1 for p in e.pedidos if p["status"] == "aberto")
    raise SystemExit(
        f"TETO DA UNIDADE ATINGIDO: ${gasto} acumulado ≥ teto de ${teto} "
        f"(MINORH_TETO_UNIT_USD).\n"
        f"O que está pendente: {c['pendentes']} campo(s) pendente(s) de "
        f"documento · {pedidos} pedido(s) aberto(s) · "
        f"{len(e.perguntas_abertas())} pergunta(s) aberta(s) · "
        f"{c['escritos']} escritos · {c['brancos']} brancos.\n"
        f"Nada foi gasto nesta execução. Para autorizar exceção, o operador "
        f"roda: MINORH_TETO_UNIT_USD=<novo teto> minorh <comando>")


def _numeros(ctx: dict[str, Any]) -> str:
    n = ctx["estado"].censo.get("exige")
    c = ctx["memoria"].contar()
    return (f"exige {n if n is not None else '?'} · "
            f"escrevi {c['escritos']} (com citação) · "
            f"branco declarado {c['brancos']} (motivo e dono) · "
            f"pendente de documento {c['pendentes']}")


def _imprimir_fecho(ctx: dict[str, Any], comando: str,
                    uso: dict[str, Any] | None) -> None:
    # O custo é registrado ANTES de qualquer print: um console que engasga
    # num caractere não pode apagar a contabilidade do que já foi gasto
    # (aconteceu em 23/08 — UnicodeEncodeError no delta engoliu $0.53).
    if uso:
        ctx["estado"].registrar_execucao(comando, uso)
    print()
    print(_numeros(ctx))
    if uso:
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
        chamadas = ", ".join(c["tool"] for c in rec.calls) or "(sem chamadas)"
        custo = (rec.usage or {}).get("custo_usd")
        print(f"   turno {rec.turn}: {chamadas}"
              + (f" · ${custo}" if custo is not None else ""), flush=True)

    print("   modelo chamado — a primeira resposta pode levar de 1 a 3 "
          "minutos; cada turno imprime uma linha abaixo.", flush=True)
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
    print(f"1/4 abrindo {pasta.name} e indexando o corpus…", flush=True)
    ctx = _abrir(pasta)
    if ctx["estado"].existe:
        print(f"{pasta} já foi aberta — use `minorh continuar`.")
        _imprimir_fecho(ctx, "unidade", None)
        return
    ULTIMA.write_text(str(pasta.resolve()), encoding="utf-8")

    print(f"    corpus indexado: {len(ctx['corpus'].names())} documentos",
          flush=True)
    print("2/4 mapeando o template do entregável…", flush=True)
    from src.examinador.run import template_map
    template = _template_de(pasta)
    task = (
        f"UNIDADE: {pasta.name}\n\n"
        f"O corpus está nas ferramentas ({len(ctx['corpus'].names())} "
        f"documentos em FILES/).\n\n"
        f"MAPA DO TEMPLATE do entregável, célula a célula:\n"
        f"{template_map(template)}\n\n"
        "Abra a unidade. O dia 1 tem três entregas, nesta ordem:\n\n"
        "1. CENSO (`declarar_censo`), como sempre — o denominador primeiro.\n\n"
        "2. ESCOPO CRUZADO: cruze o Exhibit \"A\" da DPU com AS DUAS abas do "
        "Lease-to-Well XREF e com a Lease & Mineral Schedule, county-aware "
        "(a coluna RECORDING é multi-condado e leases podem ser "
        "dual-recorded — ficha "
        "`lease-mineral-schedule-recording-multi-condado`). Toda divergência "
        "entre as fontes vira pergunta ou pedido — nunca uma escolha em "
        "silêncio. Se uma dessas fontes não existir no corpus, declare isso "
        "na memória e peça-a.\n\n"
        "3. PULL LIST DE CARTÓRIO DESDE O DIA 1: todo instrumento do "
        "perímetro sem arquivo em FILES/ mas com Book/Page (ou reception "
        "number + ano) determinístico na Schedule/Exhibit vira item de "
        "PEDIDOS.md (`pedir_documento`) com a referência exata, o condado e "
        "o caminho provável do viewer (ficha "
        "`cartorio-courthousedirect-arvore-e-busca`). Um item por decisão. "
        "Itens do mesmo lugar recebem o MESMO texto em `onde` (ex. "
        "\"cartório de Cooke — CourthouseDirect\"): o PEDIDOS.md é "
        "empacotado por esse campo em sentadas de busca, e a meta é ≤ 1h de "
        "operador por unidade.\n\n"
        "Depois: leia o que o corpus tem, grave a memória campo a campo, "
        "peça o que falta, pergunte o que só o operador resolve. Quando o "
        "que há de legível estiver na memória, pare de pedir ferramentas e "
        "resuma.")
    print("3/4 sessão do Examinador…", flush=True)
    uso = _sessao(ctx, task, "unidade",
                  _orcamento(ctx, float(os.environ.get("MINORH_TETO_USD",
                                                       "40"))), client)

    print("4/4 gravando PEDIDOS.md e PERGUNTAS.md…", flush=True)
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
    print(f"processando {len(novos)} documento(s) novo(s) e "
          f"{len(respostas)} resposta(s)…", flush=True)
    uso = _sessao(ctx, "\n\n".join(partes), "continuar",
                  _orcamento(ctx, float(os.environ.get("MINORH_TETO_USD",
                                                       "25"))), client)

    for r in respostas:
        ctx["estado"].responder(r["id"], r["resposta"])
    escrever_pedidos(ctx["estado"])
    escrever_perguntas(ctx["estado"])

    depois = {"censo": ctx["estado"].censo.get("exige"),
              **ctx["memoria"].contar()}
    # "->" e não "→": um console Windows em cp1252 não codifica U+2192, e um
    # print que estoura depois da sessão perderia o registro do custo.
    print(f"\ndelta: censo {antes['censo']} -> {depois['censo']} · "
          f"escritos {antes['escritos']} -> {depois['escritos']} · "
          f"pendentes {antes['pendentes']} -> {depois['pendentes']} · "
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
    print(f"execuções: {len(e.execucoes)} · horas do operador: "
          f"{e.horas_acumuladas()}h (meta ≤ 1h/unit) · teto da unidade: "
          f"${_teto_unit()}")
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
    from src.knowledge.write_roots import write_scope
    from src.minorh import kit as k
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

    def _somar(log: Any) -> None:
        uso_total.input += log.usage.input
        uso_total.output += log.usage.output
        uso_total.cache_write += log.usage.cache_write
        uso_total.cache_read += log.usage.cache_read

    # B3: o ship declara seu write-root ANTES de escrever; escrita fora dele
    # é exceção, não warning.
    with write_scope(pasta / PASTA_ESTADO, label=f"minorh ship {pasta.name}"):
        ship_dir = pasta / PASTA_ESTADO / "ship"
        ship_dir.mkdir(parents=True, exist_ok=True)

        print("1/4 projeção: a memória vira DDR…")
        ledger, log1 = s.projetar(
            pasta=pasta, memoria=ctx["memoria"], template=template,
            modelo=MODELO, dispatch_leitura=dispatch_leitura, client=client,
            max_cost_usd=_orcamento(ctx, 40.0))
        _somar(log1)
        # Cada sessão do ship flui para o disco na hora: um crash depois do
        # último token pago não pode apagar a contabilidade (23/08).
        log1.save(ship_dir / "log_projecao.json")
        ledger.save(ship_dir / "ledger.json")

        ddr = s.write_workbook(ledger, ship_dir / "DDR.xlsx",
                               template=template)

        print("2/4 auditoria de 100% das células escritas…")
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
            log2 = s.corrigir(pasta=pasta, ledger=ledger,
                              reprovadas=reprovadas, modelo=MODELO,
                              dispatch_leitura=dispatch_leitura,
                              template=template, client=client,
                              max_cost_usd=_orcamento(ctx, 20.0))
            _somar(log2)
            log2.save(ship_dir / "log_correcao.json")
            ledger.save(ship_dir / "ledger.json")
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
                      f"rebaixada(s) a branco declarado: "
                      f"{', '.join(removidas)}")

        print("3/4 relatórios…")
        caminhos = s.escrever_kit(
            pasta=pasta, ledger=ledger, template=template,
            vereditos=vereditos, contagem=contagem, auditor=auditor,
            memoria=ctx["memoria"], estado=ctx["estado"],
            rodadas_auditoria=rodadas,
            historico_rodada_1=historico_rodada_1)
        for nome, caminho in caminhos.items():
            print(f"   {nome}: {caminho}")

        print("4/4 kit de submissão (alocação é do modelo)…")
        # Checklist: célula alguma afirma o que a rodada não computou — os
        # Yes/No e Notes são escritos pelo modelo a partir da memória e
        # auditados como qualquer célula. Sem template na unidade, o kit
        # declara a ausência (nunca embarca checklist em branco).
        checklist_final = None
        checklist_tpl = pasta / "Phase I - Checklist.xlsx"
        if checklist_tpl.exists():
            print("   checklist: projeção da memória e auditoria…")
            led_ck, log_ck = s.projetar(
                pasta=pasta, memoria=ctx["memoria"], template=checklist_tpl,
                modelo=MODELO, dispatch_leitura=dispatch_leitura,
                client=client, max_cost_usd=_orcamento(ctx, 10.0))
            _somar(log_ck)
            log_ck.save(ship_dir / "log_checklist.json")
            checklist_final = s.write_workbook(
                led_ck, ship_dir / "Phase I - Checklist.xlsx",
                template=checklist_tpl)
            ck_vereditos, _ck = s.auditar_tudo(
                unidade=pasta.name, workbook=checklist_final, ledger=led_ck,
                corpus=ctx["corpus"], auditor=auditor)
            ck_reprovadas = s.reprovadas_de(ck_vereditos)
            if ck_reprovadas:
                removidas = s.aplicar_regra_de_embarque(led_ck, ck_reprovadas)
                checklist_final = s.write_workbook(
                    led_ck, ship_dir / "Phase I - Checklist.xlsx",
                    template=checklist_tpl)
                print(f"   checklist: {len(removidas)} célula(s) "
                      f"reprovada(s) rebaixada(s) a branco declarado")

        alocacao, log_kit = k.alocar(
            pasta=pasta, corpus=ctx["corpus"], memoria=ctx["memoria"],
            modelo=MODELO, dispatch_leitura=dispatch_leitura, client=client,
            max_cost_usd=_orcamento(ctx, 10.0))
        _somar(log_kit)
        log_kit.save(ship_dir / "log_alocacao.json")
        relatorio_kit = k.montar(
            pasta=pasta, corpus=ctx["corpus"], alocacao=alocacao, ddr=ddr,
            checklist=checklist_final)
        print(f"   kit: {relatorio_kit['raiz']}")
        print(f"   copiados (md5 conferido): "
              f"{relatorio_kit['md5_roundtrip']} · fora do kit: "
              f"{len(relatorio_kit['fora_do_kit'])} · sem decisão: "
              f"{len(relatorio_kit['sem_decisao'])}")
        print(f"   checklist: {relatorio_kit['checklist']}")

    uso = uso_total.to_dict(MODELO)
    uso_auditor = auditor.uso.to_dict(auditor.modelo)
    if uso.get("custo_usd") is not None and \
            uso_auditor.get("custo_usd") is not None:
        uso["custo_usd"] = round(uso["custo_usd"]
                                 + uso_auditor["custo_usd"], 4)
    print(f"   auditor ({auditor.provedor}/{auditor.modelo}): "
          f"{uso_auditor}")
    _imprimir_fecho(ctx, "ship", uso)


def cmd_publicar(pasta: Path) -> None:
    from src.minorh import kit as k

    ctx = _abrir(pasta)
    if not ctx["estado"].existe:
        raise SystemExit(f"{pasta} nunca foi aberta — use `minorh unidade`.")
    got = k.publicar(pasta)
    print(f"publicado: {got['publicado_em']}")
    print(f"round-trip md5: {got['md5_roundtrip']}")
    _imprimir_fecho(ctx, "publicar", None)


def cmd_painel(mae: Path) -> None:
    """D3 — leitura pura: varre a pasta-mãe e imprime uma linha por unidade
    com `_minorh/estado.json`. Zero chamada de modelo, zero escrita."""
    achadas = sorted(p.parent.parent
                     for p in mae.glob(f"*/{PASTA_ESTADO}/estado.json"))
    if not achadas:
        print(f"nenhuma unidade aberta sob {mae} (procuro "
              f"<unidade>/{PASTA_ESTADO}/estado.json).")
        return
    for unidade in achadas:
        e = Estado(unidade)
        m = Memoria(unidade / PASTA_ESTADO / "memoria.json")
        c = m.contar()
        ultima = e.execucoes[-1] if e.execucoes else None
        print(f"{unidade.name}: "
              f"censo {e.censo.get('exige', '?')} · "
              f"escritos {c['escritos']} · brancos {c['brancos']} · "
              f"pendentes {c['pendentes']} · "
              f"pedidos {sum(1 for p in e.pedidos if p['status'] == 'aberto')}"
              f" · perguntas {len(e.perguntas_abertas())} · "
              f"${e.custo_acumulado()['custo_usd']} · "
              f"{e.horas_acumuladas()}h · "
              + (f"último: {ultima['comando']} {ultima['quando'][:10]}"
                 if ultima else "último: (nenhum comando com modelo)"))


def cmd_horas(pasta: Path, horas: float, nota: str = "") -> None:
    ctx = _abrir(pasta)
    if not ctx["estado"].existe:
        raise SystemExit(f"{pasta} nunca foi aberta — use `minorh unidade`.")
    ctx["estado"].registrar_horas(horas, nota)
    print(f"registrado: {horas}h{f' — {nota}' if nota else ''}")
    print(f"horas acumuladas da unidade: "
          f"{ctx['estado'].horas_acumuladas()}h")


# --------------------------------------------------------------------------

def _pasta_de(args: list[str]) -> Path:
    if args:
        return Path(args[0])
    if ULTIMA.exists():
        return Path(ULTIMA.read_text(encoding="utf-8").strip())
    raise SystemExit("qual unidade? `minorh <comando> \"<pasta>\"` na "
                     "primeira vez.")


def main(argv: list[str] | None = None) -> None:
    # Console Windows sem UTF-8 não pode derrubar um comando por causa de um
    # caractere: substituir é melhor que perder a contabilidade da sessão.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
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
    elif comando == "publicar":
        cmd_publicar(_pasta_de(resto))
    elif comando == "painel":
        if not resto:
            raise SystemExit('uso: minorh painel "<pasta-mãe das unidades>"')
        cmd_painel(Path(resto[0]))
    elif comando == "horas":
        if not resto:
            raise SystemExit('uso: minorh horas <horas> ["nota"] ["<pasta>"]')
        try:
            horas = float(resto[0])
        except ValueError:
            raise SystemExit(f"horas deve ser número, veio {resto[0]!r}")
        nota = resto[1] if len(resto) > 1 else ""
        cmd_horas(_pasta_de(resto[2:]), horas, nota)
    else:
        raise SystemExit(f"comando desconhecido: {comando!r}. "
                         f"Comandos: unidade, continuar, estado, perguntas, "
                         f"ship, publicar, horas, painel.")
