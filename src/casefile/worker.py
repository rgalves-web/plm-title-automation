"""Worker genérico da firma de agentes (ARQUITETURA_AGENTICA_v1, etapa C).

Pega uma tarefa, monta o contexto a partir de DADOS (ficha da função +
pacote de domínio + lições publicadas + entrada da tarefa + esquema de
saída), chama o modelo pelo mesmo `run_loop` do Examinador, valida a saída
e grava. Nenhuma instrução de title mora aqui: o que a função deve fazer
está na ficha versionada; o que o código faz é encanamento.

Fronteiras:
- a ficha é a lista de permissão de ferramentas: só se expõe o que ela
  declara E o chamador fornece; o resto é dito ao modelo como indisponível;
- lição `draft` nunca entra no contexto (só `stable`, do pacote e da
  função da tarefa);
- Verificador não roda aqui até o operador decidir o formato da saída dele
  (divergência 2 do checkpoint A) — a tarefa fica `pronta`, intocada;
- o custo de cada run entra no livro da unit pelo `fechar_run`; se o run se
  perdeu (trava vencida e retomada), o custo entra do mesmo jeito.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from src.casefile import agentes, orquestracao as orq, validacao
from src.casefile.orquestracao_repo import TransicaoInvalida
from src.examinador.loop import RATES, Usage, run_loop

MODELO_POR_NIVEL = {
    "forte": "claude-opus-5",
    "medio": "claude-sonnet-5",
    "barato": "claude-haiku-4-5-20251001",
    "barato_a_medio": "claude-haiku-4-5-20251001",
}
FAMILIA = "A"
FUNCOES_FORA_DO_WORKER = ("verificador",)
MAX_TURNOS_PADRAO = 40

FERRAMENTA_ENTREGA = {
    "name": "entregar_saida",
    "description": (
        "Entrega a saída desta tarefa, no esquema indicado na tarefa. A "
        "resposta diz se a entrega é válida e, se não for, os erros de "
        "forma, item a item. Pode entregar de novo para corrigir; vale a "
        "ÚLTIMA entrega."),
    "input_schema": {"type": "object",
                     "properties": {"saida": {"type": "object"}},
                     "required": ["saida"]},
}

SISTEMA_BASE = """Voce executa UMA tarefa como uma funcao da firma de agentes \
da PLM. A ficha da sua funcao (abaixo) e a sua instrucao; o pacote de dominio \
traz o vocabulario, as fontes e o fluxo da area. Regras que valem para toda \
funcao:
- faca so o que a sua funcao faz; o resto e tarefa de outra funcao;
- sem trecho literal nao ha afirmacao; branco declarado com motivo vence \
valor plausivel; inferencia nunca vira fato;
- fato de outra unit nunca e prova;
- entregue o resultado pela ferramenta `entregar_saida`, no esquema pedido, \
e pare."""


# --- contexto ---------------------------------------------------------------------

def _refs_de_esquema(esquema: dict[str, Any]) -> set[str]:
    return set(re.findall(r'"\$ref":\s*"([\w-]+)\.json', json.dumps(esquema)))


def _esquema_com_refs(nome: str, raiz: Path) -> str:
    disponiveis = agentes.esquemas_disponiveis(raiz)
    vistos, fila, partes = set(), [nome], []
    while fila:
        n = fila.pop(0)
        if n in vistos or n not in disponiveis:
            continue
        vistos.add(n)
        texto = disponiveis[n].read_text(encoding="utf-8")
        partes.append(f"### {n}.json\n```json\n{texto.strip()}\n```")
        fila.extend(sorted(_refs_de_esquema(json.loads(texto))))
    return "\n\n".join(partes)


def montar_contexto(task: dict[str, Any], *, raiz: str | Path | None = None,
                    ferramentas_disponiveis: set[str] | frozenset[str] = frozenset()
                    ) -> dict[str, Any]:
    """Sistema + mensagem da tarefa, e o inventário do que entrou."""
    raiz = Path(raiz) if raiz is not None else agentes.RAIZ_PADRAO
    r = orq._fichas(raiz)
    funcao = next(f for f in r.por_tipo("Role") if f.nome == task["role"])
    partes = [SISTEMA_BASE,
              f"## Ficha da funcao `{funcao.nome}` (versao "
              f"{agentes.versao(funcao.caminho)[:12]})\n\n"
              + funcao.caminho.read_bytes().decode("utf-8").strip()]
    pacote = None
    if task.get("pack"):
        pacote = next(f for f in r.por_tipo("Domain Pack")
                      if f.nome == task["pack"])
        partes.append(f"## Pacote de dominio `{pacote.nome}` (versao "
                      f"{agentes.versao(pacote.caminho)[:12]})\n\n"
                      + pacote.caminho.read_bytes().decode("utf-8").strip())
    licoes = [f for f in r.por_tipo("Lesson")
              if f.status == "stable" and f.front.get("funcao") == funcao.nome
              and (f.front.get("escopo") or {}).get("pacote") == task.get("pack")]
    for f in licoes:
        partes.append(f"## Licao publicada `{f.nome}` (versao "
                      f"{agentes.versao(f.caminho)[:12]})\n\n"
                      + f.caminho.read_bytes().decode("utf-8").strip())

    declaradas = [str(x) for x in funcao.front.get("ferramentas") or []]
    expostas = [n for n in declaradas if n in ferramentas_disponiveis]
    indisponiveis = [n for n in declaradas if n not in ferramentas_disponiveis]

    tarefa = [
        f"# Tarefa `{task['ref']}`: {task['title']}",
        f"Criterio de aceite: {task['acceptance']}",
        "## Entrada\n```json\n" + json.dumps(task.get("input_json") or {},
                                              ensure_ascii=False, indent=1)
        + "\n```",
        f"## Esquema de saida (`{task['output_schema']}`)\n\n"
        + _esquema_com_refs(task["output_schema"], raiz),
    ]
    if indisponiveis:
        tarefa.append(
            "## Ferramentas da ficha indisponiveis nesta execucao\n"
            + ", ".join(indisponiveis) + ". Nao presuma o resultado delas: "
            "o que depender delas fica declarado como pendente na saida.")
    tarefa.append("Entregue com `entregar_saida(saida=<objeto no esquema>)`.")
    return {"sistema": "\n\n".join(partes), "tarefa": "\n\n".join(tarefa),
            "funcao": funcao, "pacote": pacote,
            "licoes": [f.rel for f in licoes], "ferramentas": expostas,
            "indisponiveis": indisponiveis}


# --- validação e gravação por esquema ---------------------------------------------

def _checar_claims(repo: Any, task: dict[str, Any], saida: Any) -> list[str]:
    """Mesma validação estrutural de `registrar_claims` (validacao.py)."""
    from src.casefile.acervo import _norm
    tipos = repo.tipos_de_claim()
    sha_por_nome = repo.sha_por_nome(task["unit_id"])
    erros = []
    for i, item in enumerate(saida.get("claims") or []):
        try:
            validacao.validar_claim(
                item, tipos, lambda n: sha_por_nome.get(_norm(n), []),
                repo.sha_existe)
        except validacao.ClaimInvalido as exc:
            erros.append(f"claims/{i}: {exc}")
    return erros


def _gravar_claims(repo: Any, task: dict[str, Any], saida: Any,
                   session_id: int) -> list[int]:
    from src.casefile.acervo import _norm
    tipos = repo.tipos_de_claim()
    sha_por_nome = repo.sha_por_nome(task["unit_id"])
    ids = []
    for item in saida.get("claims") or []:
        ok = validacao.validar_claim(
            item, tipos, lambda n: sha_por_nome.get(_norm(n), []),
            repo.sha_existe)
        # Determinação 1 do operador (02/09), como em ferramentas.py:
        # evidência que existe só na entrega é marcada como contaminação.
        origens = repo.origens_do_sha(ok["source_sha256"])
        if origens and origens <= {"entrega"}:
            ok["value"] = dict(ok["value"], benchmark_contamination=True,
                               origem_evidencia="entrega")
        ids.append(repo.inserir_claim(unit_id=task["unit_id"],
                                      session_id=session_id, **ok))
        extras = {k: item[k] for k in ("celulas_candidatas", "limitacoes")
                  if k in item}
        if extras:
            repo.atualizar_claim_ddr(task["unit_id"], ids[-1],
                                     list(extras.get("celulas_candidatas", [])),
                                     extras.get("limitacoes", ""))
    if ids:
        repo.vincular_claims(task["id"], ids)
    return ids


VALIDADORES: dict[str, Callable[..., list[str]]] = {"claims": _checar_claims}
GRAVADORES: dict[str, Callable[..., list[int]]] = {"claims": _gravar_claims}


# --- executar ---------------------------------------------------------------------

class _ClienteContado:
    """Soma o uso de cada resposta ANTES de o laço seguir: se a execução
    cai no meio (erro da API, trava perdida), o gasto já está contado."""

    def __init__(self, inner: Any, uso: Usage) -> None:
        self.inner, self.uso, self.turnos = inner, uso, 0
        self.messages = self

    def create(self, **kw: Any) -> Any:
        msg = self.inner.messages.create(**kw)
        self.uso.add(msg.usage)
        self.turnos += 1
        return msg


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def executar_uma(repo: Any, unit_id: int, worker: str, *, teto: float,
                 client: Any = None, raiz: str | Path | None = None,
                 ferramentas: dict[str, tuple[dict[str, Any], Callable]] | None = None,
                 modelos: dict[str, str] | None = None,
                 lease_segundos: int = orq.LEASE_PADRAO_S,
                 max_turnos: int = MAX_TURNOS_PADRAO) -> dict[str, Any] | None:
    """Uma tarefa, do `pegar` ao `entregar`. None quando não há tarefa pronta
    para este worker. TetoAtingido sobe (pendentes já bloqueadas)."""
    got = orq.pegar(repo, unit_id, worker, teto=teto, raiz=raiz,
                    lease_segundos=lease_segundos,
                    excluir_roles=FUNCOES_FORA_DO_WORKER)
    if got is None:
        return None
    task, run = got
    ferramentas = ferramentas or {}
    ctx = montar_contexto(task, raiz=raiz,
                          ferramentas_disponiveis=set(ferramentas))
    nivel = ctx["funcao"].front["nivel_modelo"]
    modelo = (modelos or MODELO_POR_NIVEL)[nivel]
    if modelo not in RATES:
        raise ValueError(f"modelo_sem_tarifa: {modelo!r} — custo invisível "
                         f"não roda")

    checar = VALIDADORES.get(task["output_schema"])
    validar_extra = (lambda t, s: checar(repo, t, s)) if checar else None
    entrega: dict[str, Any] = {"saida": None, "entregas": 0}

    def _entregar_saida(saida: Any) -> dict[str, Any]:
        erros = agentes.validar_saida(task["output_schema"], saida, raiz)
        if not erros and validar_extra is not None:
            erros = validar_extra(task, saida)
        entrega["saida"], entrega["entregas"] = saida, entrega["entregas"] + 1
        return {"recebida": True, "valida": not erros, "erros": erros[:20]}

    tools = [FERRAMENTA_ENTREGA] + [ferramentas[n][0]
                                   for n in ctx["ferramentas"]]
    dispatch = {"entregar_saida": _entregar_saida,
                **{n: ferramentas[n][1] for n in ctx["ferramentas"]}}
    session_id = repo.abrir_sessao(unit_id, f"tarefa:{task['id']}", modelo)

    def _renovar(_registro: Any) -> None:
        repo.renovar_lease(run["id"], worker, lease_segundos)

    if client is None:
        from src.examinador.loop import _client
        client = _client()
    uso = Usage()
    contado = _ClienteContado(client, uso)
    falha = ""
    perdido: TransicaoInvalida | None = None
    try:
        log, _ = run_loop(system=ctx["sistema"], task=ctx["tarefa"],
                          tools=tools, dispatch=dispatch, model=modelo,
                          max_turns=max_turnos,
                          max_cost_usd=task["budget_usd"] or None,
                          on_turn=_renovar, client=contado)
        parada = log.stop_reason
    except TransicaoInvalida as exc:              # trava perdida no meio
        perdido, parada = exc, f"trava_perdida: {exc}"
    except Exception as exc:                      # o run não fica órfão
        parada = falha = f"erro_do_modelo: {exc.__class__.__name__}: {exc}"
    custo = uso.cost(modelo) or 0.0
    repo.fechar_sessao(session_id, parada, contado.turnos,
                       uso.to_dict(modelo), custo, "")
    if perdido is not None:
        _custo_perdido(repo, unit_id, task, run, custo)
        raise perdido

    motivo = ("erro_do_modelo" if falha else
              "sem_entrega" if entrega["entregas"] == 0 else "")
    meta = {"model": modelo, "model_family": FAMILIA,
            "prompt_sha256": _sha(ctx["sistema"] + "\n\n" + ctx["tarefa"]),
            "tokens_in": uso.input + uso.cache_write + uso.cache_read,
            "tokens_out": uso.output, "cost_usd": custo}
    try:
        res = orq.entregar(repo, run["id"], worker, entrega["saida"],
                           teto=teto, raiz=raiz, validar_extra=validar_extra,
                           motivo_invalida=motivo, **meta)
    except TransicaoInvalida:
        _custo_perdido(repo, unit_id, task, run, custo)
        raise

    gravados: list[int] = []
    gravar = GRAVADORES.get(task["output_schema"])
    if not res["erros"] and gravar is not None:
        gravados = gravar(repo, task, entrega["saida"], session_id)
    return {"tarefa": res["tarefa"], "run_id": run["id"],
            "erros": res["erros"], "teto_atingido": res["teto_atingido"],
            "modelo": modelo, "custo_usd": custo, "parada": parada,
            "entregas": entrega["entregas"], "gravados": gravados,
            "licoes": ctx["licoes"], "indisponiveis": ctx["indisponiveis"]}


def _custo_perdido(repo: Any, unit_id: int, task: dict[str, Any],
                   run: dict[str, Any], custo: float) -> None:
    """Trava vencida e retomada por outro worker: a saída não vale, mas o
    gasto aconteceu e entra no livro da unit."""
    if custo:
        repo.registrar_custo(unit_id, "tarefa", custo,
                             {"task_id": task["id"], "run_id": run["id"],
                              "role": task["role"], "run_perdido": True})


def executar_ate_parar(repo: Any, unit_id: int, worker: str, *, teto: float,
                       max_tarefas: int = 50, **kw: Any) -> dict[str, Any]:
    """Executa tarefas prontas até não haver mais, bater o teto ou o limite.
    Não aceita nem decide nada: o que precisa de verificação ou do operador
    fica esperando."""
    execucoes: list[dict[str, Any]] = []
    parada = "sem tarefa pronta para este worker"
    for _ in range(max_tarefas):
        try:
            got = executar_uma(repo, unit_id, worker, teto=teto, **kw)
        except orq.TetoAtingido as exc:
            parada = f"teto: {exc}"
            break
        if got is None:
            break
        execucoes.append(got)
        if got["teto_atingido"]:
            parada = "teto atingido na última execução"
            break
    else:
        parada = f"limite de {max_tarefas} tarefas nesta chamada"
    return {"execucoes": execucoes, "parada": parada,
            "custo_usd": round(sum(e["custo_usd"] for e in execucoes), 4)}
