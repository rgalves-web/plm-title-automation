"""Os comandos do Case File. Cada um termina imprimindo contagens e custo real.

    python -m src.casefile db migrar          aplica as migracoes pendentes
    python -m src.casefile db estado          versoes aplicadas + ping no banco
    python -m src.casefile indicar "<unit>" [--projeto=DIR]
                                              resolve a pasta pelo NOME e cria
                                              a unit em INDICADA
    python -m src.casefile planejar ["<unit>"]
                                              o VS1: censo -> triagem ->
                                              Examinador -> plano proposto
    python -m src.casefile plano ["<unit>"] [--versao=N]   imprime o plano
    python -m src.casefile aprovar ["<unit>"] [--nota="..."]
    python -m src.casefile rejeitar ["<unit>"] --motivo="..."
    python -m src.casefile estado ["<unit>"]  estado, contagens, custo
    python -m src.casefile unidades           uma linha por unit no banco

Teto duro por unit: US$ 25 (`CASEFILE_TETO_UNIT_USD`). Ao bater, qualquer
comando com modelo recusa, reporta e espera ordem — nunca estoura em silêncio.

Este arquivo não contém juízo de title: resolve pastas, monta sessões,
persiste o que o modelo afirmou e imprime contagens.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from src.casefile import caneta, censo, custo, estados, ferramentas
from src.casefile import plano as plano_mod
from src.casefile import referencia, sessao, triagem
from src.casefile.acervo import montar_acervo

ULTIMA = Path.home() / ".casefile_ultima"

SISTEMA_PLANEJADOR = """Voce e o landman responsavel por PLANEJAR a
investigacao desta unidade. O entregavel desta fase NAO e o DDR — e o UNIT
INVESTIGATION PLAN: o inventario completo e auditavel do que o registro exige,
do que existe no acervo e do que falta pesquisar.

Voce trabalha em AFIRMACOES (`registrar_claims`): cada fato que voce
estabelece — linha do XREF pertencente a unit, lease do Exhibit A, tract,
legal description, seller, title opinion e sua cobertura, documento presente,
documento faltante, divergencia entre fontes — vira um claim com citacao
literal (documento, pagina, trecho). Um claim sem evidencia nao existe;
`document_missing` cita a fonte QUE EXIGE o documento, nunca a propria
ignorancia (ausencia nao se infere de nao ter procurado).

O que falta pesquisar vira `registrar_pesquisas` — um item por decisao de
busca, com onde e metodo; itens do mesmo lugar recebem o MESMO texto em
`onde`.

Ao final, feche com `propor_plano`: o markdown completo do plano (secoes:
identidade da unit e perimetro; XREFs e linhas da unit; tracts e legal
descriptions; sellers; title opinions e coberturas; censo documental —
presentes e ausentes; divergencias; pesquisas necessarias) e o resumo com as
contagens declaradas. O plano sera aprovado ou rejeitado pelo operador; toda
afirmacao material precisa ser rastreavel ate a fonte.

Regra de sempre: branco declarado e melhor que numero plausivel. Divergencia
entre fontes vira claim `divergence`, nunca uma escolha em silencio."""


# --------------------------------------------------------------------------
# infra
# --------------------------------------------------------------------------

def _repo() -> Any:
    from src.casefile.db import connect
    from src.casefile.repo import Repo
    return Repo(connect())


def _nome_de(args: list[str]) -> str:
    posicionais = [a for a in args if not a.startswith("--")]
    if posicionais:
        return posicionais[0]
    if ULTIMA.exists():
        return ULTIMA.read_text(encoding="utf-8").strip()
    raise SystemExit("qual unit? `python -m src.casefile <comando> "
                     "\"<nome da unit>\"` na primeira vez.")


def _unit_de(repo: Any, nome: str) -> dict[str, Any]:
    unit = repo.obter_unit_por_nome(nome)
    if unit is None:
        pasta = referencia.unit_folder(nome)
        if pasta is not None:
            unit = repo.obter_unit_por_nome(pasta.name)
    if unit is None:
        raise SystemExit(f"unit {nome!r} nao esta no Case File — rode "
                         f"`python -m src.casefile indicar \"{nome}\"`.")
    ULTIMA.write_text(unit["canonical_name"], encoding="utf-8")
    return unit


def _flag(args: list[str], nome: str) -> str | None:
    prefixo = f"--{nome}="
    for a in args:
        if a.startswith(prefixo):
            return a[len(prefixo):]
    return None


def _fecho(repo: Any, unit: dict[str, Any], cache: Any = None) -> None:
    contagens = repo.contagens_claims(unit["id"])
    print()
    print(f"claims ativos: {sum(contagens.values())} "
          f"({', '.join(f'{k} {v}' for k, v in sorted(contagens.items()))})"
          if contagens else "claims ativos: 0")
    print(f"pesquisas abertas: {repo.contagem_pesquisas(unit['id'])}")
    print(f"acumulado da unit: ${repo.custo_acumulado(unit['id'])} "
          f"(teto ${custo.teto_unit()})")
    if cache is not None:
        stats = cache.stats()
        consultas = stats["hits"] + stats["misses"]
        if consultas:
            print(f"cache global de paginas: {stats['hits']} hit(s) / "
                  f"{consultas} consulta(s) "
                  f"({100 * stats['hits'] // consultas}%)")


# --------------------------------------------------------------------------
# comandos sem modelo
# --------------------------------------------------------------------------

def cmd_db(resto: list[str]) -> None:
    from src.casefile.db import connect, estado_migracoes, migrar
    if not resto or resto[0] not in ("migrar", "estado"):
        raise SystemExit("uso: python -m src.casefile db migrar|estado")
    conn = connect()
    try:
        if resto[0] == "migrar":
            novas = migrar(conn)
            print(f"aplicadas agora: {novas or 'nenhuma (em dia)'}")
        for m in estado_migracoes(conn):
            print(f"  {m['version']:04d}_{m['name']}  "
                  f"{str(m['applied_at'])[:19]}  {m['checksum'][:12]}…")
        print("banco: ok")
    finally:
        conn.close()


def cmd_indicar(nome: str, projeto_dir: str | None = None,
                repo: Any = None) -> None:
    repo = repo or _repo()
    root = referencia.raiz_do_projeto(projeto_dir)
    pasta = referencia.unit_folder(nome, root)
    if pasta is None:
        candidatas = referencia.listar_pastas_de_unit(root)
        raise SystemExit(
            f"nenhuma pasta de unit corresponde a {nome!r} em {root}.\n"
            f"Candidatas:\n" + "\n".join(f"  - {c}" for c in candidatas))
    engagement, _, resto_nome = root.name.partition(" - ")
    proj = repo.obter_ou_criar_projeto(
        engagement.strip(), (resto_nome or root.name).strip(), str(root))
    unit, criada = repo.obter_ou_criar_unit(
        proj["id"], nome, pasta.name, str(pasta))
    if criada:
        repo.transicionar(unit["id"], "", "INDICADA", "indicar", "operador",
                          f"como digitado: {nome!r}")
        print(f"INDICADA: {unit['canonical_name']} "
              f"(projeto {proj['engagement']}, pasta {pasta})")
    else:
        print(f"ja indicada: {unit['canonical_name']} — estado "
              f"{repo.estado_da_unit(unit['id'])}")
    ULTIMA.write_text(unit["canonical_name"], encoding="utf-8")


def cmd_estado(nome: str, repo: Any = None) -> None:
    repo = repo or _repo()
    unit = _unit_de(repo, nome)
    print(f"unit: {unit['canonical_name']} — estado "
          f"{repo.estado_da_unit(unit['id'])}")
    print(f"pasta: {unit['folder_path']}")
    origens = repo.contagem_censo(unit["id"])
    if origens:
        print("censo: " + " · ".join(
            f"{o} {d['conteudos']} conteudo(s)/{d['sightings']} caminho(s)"
            for o, d in sorted(origens.items())))
    pl = repo.plano(unit["id"])
    if pl:
        print(f"plano: v{pl['version']} ({pl['status']})")
    for t in repo.transicoes(unit["id"])[-5:]:
        print(f"  {str(t['at'])[:19]}  {t['from_state'] or '-'} -> "
              f"{t['to_state']}  [{t['event']}] {t['actor']}"
              + (f" — {t['note']}" if t["note"] else ""))
    _fecho(repo, unit)


def cmd_unidades(repo: Any = None) -> None:
    repo = repo or _repo()
    units = repo.listar_units()
    if not units:
        print("nenhuma unit no Case File — comece com `indicar`.")
        return
    for u in units:
        pl = repo.plano(u["id"])
        print(f"{u['canonical_name']}: {u['state']} · "
              f"claims {sum(repo.contagens_claims(u['id']).values())} · "
              f"pesquisas {repo.contagem_pesquisas(u['id'])} · "
              f"${repo.custo_acumulado(u['id'])}"
              + (f" · plano v{pl['version']} ({pl['status']})" if pl else ""))


def cmd_plano(nome: str, versao: int | None = None, repo: Any = None) -> None:
    repo = repo or _repo()
    unit = _unit_de(repo, nome)
    pl = repo.plano(unit["id"], versao)
    if pl is None:
        raise SystemExit(f"{unit['canonical_name']} nao tem plano"
                         + (f" v{versao}" if versao else "")
                         + " — rode `planejar`.")
    print(f"--- PLANO v{pl['version']} ({pl['status']}) — "
          f"{unit['canonical_name']} ---")
    print(pl["markdown"])
    print()
    print(plano_mod.contagens_lado_a_lado(repo, unit, pl["summary"]))


def cmd_aprovar(nome: str, nota: str = "", repo: Any = None) -> None:
    repo = repo or _repo()
    unit = _unit_de(repo, nome)
    pl = repo.plano(unit["id"])
    if pl is None or pl["status"] != "proposto":
        raise SystemExit(
            f"{unit['canonical_name']} nao tem plano PROPOSTO para aprovar"
            + (f" (ultimo: v{pl['version']} {pl['status']})" if pl else "")
            + " — rode `planejar`.")
    repo.decidir_plano(pl["id"], "aprovado", "operador", nota)
    novo = estados.transicionar(repo, unit, "aprovar_plano", "operador", nota)
    print(f"plano v{pl['version']} APROVADO — "
          f"{unit['canonical_name']} agora em {novo} (a coleta e o VS2).")


def cmd_rejeitar(nome: str, motivo: str, repo: Any = None) -> None:
    repo = repo or _repo()
    if not motivo.strip():
        raise SystemExit("rejeitar exige --motivo=\"...\" — a regressao e "
                         "registrada, nunca silenciosa.")
    unit = _unit_de(repo, nome)
    pl = repo.plano(unit["id"])
    if pl is None or pl["status"] != "proposto":
        raise SystemExit(f"{unit['canonical_name']} nao tem plano PROPOSTO "
                         f"para rejeitar.")
    repo.decidir_plano(pl["id"], "rejeitado", "operador", motivo)
    estados.transicionar(repo, unit, "rejeitar_plano", "operador", motivo)
    print(f"plano v{pl['version']} REJEITADO — de volta a PLANEJANDO. "
          f"Rode `planejar` de novo (o motivo esta na trilha).")


# --------------------------------------------------------------------------
# o VS1
# --------------------------------------------------------------------------

def cmd_planejar(nome: str, repo: Any = None, client: Any = None) -> None:
    from src.examinador.cache import PageCache
    from src.examinador.okf import KnowledgeBase

    repo = repo or _repo()
    unit = _unit_de(repo, nome)
    pasta = Path(unit["folder_path"])
    if not pasta.is_dir():
        raise SystemExit(f"a pasta da unit sumiu do disco: {pasta}")

    atual = repo.estado_da_unit(unit["id"])
    if atual == "INDICADA":
        estados.transicionar(repo, unit, "planejar", "operador")
    elif atual == "PLANEJANDO":
        print("retomada: a unit ja esta em PLANEJANDO.")
    elif atual == "AGUARDANDO_RENATO":
        raise SystemExit(
            f"{unit['canonical_name']} tem plano proposto aguardando "
            f"decisao — rode `aprovar` ou `rejeitar --motivo`.")
    else:
        raise SystemExit(f"planejar exige INDICADA ou PLANEJANDO; "
                         f"{unit['canonical_name']} esta em {atual}.")

    teto_comando = float(os.environ.get("CASEFILE_TETO_USD", "40"))
    custo.orcamento(repo, unit, teto_comando)   # recusa limpa antes de tudo

    print("1/4 referencias da raiz do projeto + censo (deterministico)…",
          flush=True)
    proj_root = pasta.parent
    referencias = {k: referencia.find_reference(k, proj_root)
                   for k in referencia.REFERENCE_PATTERNS}
    resumo_censo = censo.executar(repo, unit, pasta, referencias)
    print(f"    censo: {resumo_censo['conteudos']} conteudo(s) em "
          f"{resumo_censo['sightings']} caminho(s) · homonimos com bytes "
          f"diferentes: {len(resumo_censo['homonimos'])}", flush=True)

    cache = PageCache()
    acervo = montar_acervo(pasta, referencias, cache=cache)
    kb_unidade = KnowledgeBase(caneta.caminho(pasta) / "fichas")
    kb_global = KnowledgeBase()
    session_ref: dict[str, Any] = {"id": None}
    dispatch = ferramentas.montar_dispatch(
        acervo=acervo, repo=repo, unit=unit, pasta=pasta,
        kb_unidade=kb_unidade, kb_global=kb_global,
        ator=f"modelo:{sessao.modelo()}", session_ref=session_ref)

    print(f"2/4 triagem do censo ({triagem.modelo_triagem()})…", flush=True)
    dispatch_leitura = {n: f for n, f in dispatch.items()
                        if n in ("read_page", "list_documents",
                                 "search_corpus")}
    orc = custo.orcamento(repo, unit, teto_comando)
    novos, _log_tri = triagem.triar(
        repo=repo, unit=unit, pasta=pasta, acervo=acervo,
        dispatch_leitura=dispatch_leitura, client=client,
        max_cost_usd=min(3.0, orc))
    print(f"    {novos} conteudo(s) rotulado(s) agora", flush=True)

    print("3/4 sessao do Examinador (plano de investigacao)…", flush=True)
    task = _task_planejar(repo, unit, referencias, resumo_censo)
    orc = custo.orcamento(repo, unit, teto_comando)
    sessao.rodar(
        repo=repo, unit=unit, pasta=pasta, comando="planejar.examinador",
        sistema=SISTEMA_PLANEJADOR, task=task,
        ferramentas=ferramentas.FERRAMENTAS_LEITURA
        + ferramentas.FERRAMENTAS_ESCRITA,
        dispatch=dispatch, modelo_sessao=sessao.modelo(),
        max_cost_usd=orc, client=client, session_ref=session_ref)

    print("4/4 fecho…", flush=True)
    pl = repo.plano(unit["id"])
    if pl is None:
        print("ATENCAO: a sessao terminou SEM propor plano — a unit segue "
              "em PLANEJANDO; rode `planejar` de novo para continuar.")
    else:
        caminho_md = caneta.caminho(pasta) / \
            f"PLANO_INVESTIGACAO_v{pl['version']}.md"
        print(f"plano v{pl['version']} proposto: {caminho_md}")
        print(plano_mod.contagens_lado_a_lado(repo, unit, pl["summary"]))
        print("decisao do operador: `python -m src.casefile aprovar` ou "
              "`rejeitar --motivo=\"...\"`.")
    _fecho(repo, unit, cache)


def _task_planejar(repo: Any, unit: dict[str, Any],
                   referencias: dict[str, Path | None],
                   resumo_censo: dict[str, Any]) -> str:
    sha_por_nome = repo.sha_por_nome(unit["id"])
    linhas_ref = []
    for kind in sorted(referencias):
        path = referencias[kind]
        if path is None:
            linhas_ref.append(f"- {kind}: NAO ENCONTRADA na raiz do projeto "
                              f"— a ausencia e fato do plano")
            continue
        logical = f"referencias/{path.name}".lower()
        hashes = sha_por_nome.get(logical, [])
        linhas_ref.append(
            f"- {kind}: `{logical}`"
            + (f" (sha256 {hashes[0][:12]}…)" if hashes else ""))

    homonimos = resumo_censo.get("homonimos") or {}
    linhas_hom = [
        f"- {nome}: {len(shas)} conteudos distintos "
        f"({', '.join(s[:12] + '…' for s in shas)})"
        for nome, shas in sorted(homonimos.items())][:20]

    mapa = triagem.mapa_markdown(repo.rotulos(unit["id"]), sha_por_nome)

    partes = [
        f"UNIDADE: {unit['canonical_name']}",
        f"CENSO DETERMINISTICO: {resumo_censo['conteudos']} conteudos "
        f"distintos em {resumo_censo['sightings']} caminhos. Por origem: "
        + "; ".join(f"{o}: {d['conteudos']}" for o, d in
                    sorted(resumo_censo["por_origem"].items()))
        + ". A pasta de entrega (origin `entrega`) esta FORA do acervo "
          "desta sessao (quarentena por identidade de origem).",
        "REFERENCIAS DA RAIZ DO PROJETO (no acervo sob `referencias/`):\n"
        + "\n".join(linhas_ref),
    ]
    if linhas_hom:
        partes.append(
            "HOMONIMOS COM BYTES DIFERENTES (mesmo nome de arquivo, "
            "conteudos distintos — cite sha256:<hash> ao afirmar sobre "
            "eles):\n" + "\n".join(linhas_hom))
    if mapa:
        partes.append(mapa)
    partes.append(
        "MONTE O UNIT INVESTIGATION PLAN. O caminho, nesta ordem:\n\n"
        "1. PERIMETRO: ache a DPU/Unit Designation no acervo (Exhibit \"A\" "
        "= leases; Exhibit \"C\" = tracts) e registre `unit_identity`, "
        "`lease_in_unit`, `tract`, `legal_description` com citacoes.\n\n"
        "2. ESCOPO CRUZADO: cruze o Exhibit \"A\" com AS DUAS abas do "
        "Lease-to-Well XREF e com a Lease & Mineral Schedule, county-aware "
        "(a coluna RECORDING e multi-condado; leases podem ser dual-recorded "
        "— ficha `lease-mineral-schedule-recording-multi-condado`). O XREF "
        "tem dezenas de milhares de linhas em janelas de 200 — NUNCA varra: "
        "use `search_corpus` e as fichas de layout (`layout-xref-lease-to-"
        "well-ordenacao-e-custo`) para ir direto as janelas. Ha DUAS vias de "
        "pertencimento a unit: a coluna UNIT LEVEL NAME quando o export a "
        "tiver, e senao o contrato UNIT AGREEMENT/DPU (K…) cujo nome carrega "
        "os tokens da unit. Se as vias divergirem ou a coluna nao existir, "
        "isso vira claim `divergence` ou pergunta no plano — nunca escolha "
        "em silencio. Cada linha da unit vira claim `xref_row`.\n\n"
        "3. TITLE OPINIONS: liste os TOs do acervo e das planilhas "
        "(`title_opinion`) e o que cada um cobre (`to_coverage`).\n\n"
        "4. SELLERS: identifique sellers e interesses (`seller_interest`) "
        "pelo que o registro e as planilhas declaram.\n\n"
        "5. CENSO DOCUMENTAL: cruze o que o registro exige com o acervo — "
        "`document_present` (com o nome logico) e `document_missing` (citando "
        "a fonte que exige, ex. a linha do Exhibit A sem pasta de lease).\n\n"
        "6. PESQUISAS: todo documento faltante com referencia deterministica "
        "(Book/Page, reception number + ano, condado) vira item de "
        "`registrar_pesquisas`.\n\n"
        "7. Feche com `propor_plano` — o markdown completo e as contagens "
        "declaradas.\n\n"
        "O que valer alem desta unidade (layouts, cadeias, licoes de custo), "
        "grave com write_knowledge escopo `global`: sao ~300 unidades do "
        "mesmo projeto.")
    return "\n\n".join(partes)


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    # Console Windows sem UTF-8 nao pode derrubar um comando por causa de um
    # caractere: substituir e melhor que perder a contabilidade da sessao.
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
    if comando == "db":
        cmd_db(resto)
    elif comando == "indicar":
        posicionais = [a for a in resto if not a.startswith("--")]
        if not posicionais:
            raise SystemExit('uso: python -m src.casefile indicar '
                             '"<nome da unit>" [--projeto=DIR]')
        cmd_indicar(posicionais[0], _flag(resto, "projeto"))
    elif comando == "planejar":
        cmd_planejar(_nome_de(resto))
    elif comando == "plano":
        versao = _flag(resto, "versao")
        cmd_plano(_nome_de(resto), int(versao) if versao else None)
    elif comando == "aprovar":
        cmd_aprovar(_nome_de(resto), _flag(resto, "nota") or "")
    elif comando == "rejeitar":
        cmd_rejeitar(_nome_de(resto), _flag(resto, "motivo") or "")
    elif comando == "estado":
        cmd_estado(_nome_de(resto))
    elif comando == "unidades":
        cmd_unidades()
    else:
        raise SystemExit(f"comando desconhecido: {comando!r}. Comandos: db, "
                         f"indicar, planejar, plano, aprovar, rejeitar, "
                         f"estado, unidades.")
