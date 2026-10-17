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
  perdeu (trava vencida e retomada), o custo entra do mesmo jeito;
- teto ESTIMADO, com reserva no banco: antes de qualquer chamada o run
  reserva (unit travada) o menor saldo entre tarefa e unit, descontadas as
  reservas dos outros runs abertos — dois workers nunca contam o mesmo
  dinheiro; ≤ 0 não chama modelo; antes de CADA chamada, gasto + pior caso
  estimado da resposta não pode passar da reserva. A cobrança exata da API
  só se conhece depois da resposta (docs/ARQUITETURA_AGENTICA_ETAPA_D.md §4);
- saída de `plano_tarefas` vira PROPOSTA (plan_proposals), nunca tarefas;
- unit com perfil surface (Cibola) é recusada antes de qualquer efeito.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from src.casefile import agentes, orquestracao as orq, validacao
from src.casefile.orquestracao_repo import TransicaoInvalida

ATOR = "process:worker"
from src.infra.loop import RATES, Usage, run_loop

MODELO_POR_NIVEL = {
    "forte": "claude-opus-5",
    "medio": "claude-sonnet-5",
    "barato": "claude-haiku-4-5-20251001",
    "barato_a_medio": "claude-haiku-4-5-20251001",
}
FAMILIA = "A"
FUNCOES_FORA_DO_WORKER = ("verificador",)
MAX_TURNOS_PADRAO = 40


class ExecutionNeedsReview(RuntimeError):
    pass

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
                    ferramentas_disponiveis: set[str] | frozenset[str] = frozenset(),
                    blind: bool = False
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
    if task.get("pack") and not blind:
        pacote = next(f for f in r.por_tipo("Domain Pack")
                      if f.nome == task["pack"])
        partes.append(f"## Pacote de dominio `{pacote.nome}` (versao "
                      f"{agentes.versao(pacote.caminho)[:12]})\n\n"
                      + pacote.caminho.read_bytes().decode("utf-8").strip())
    licoes = [f for f in r.por_tipo("Lesson")
              if f.status == "stable" and f.front.get("funcao") == funcao.nome
              and (f.front.get("escopo") or {}).get("pacote") == task.get("pack")]
    if blind:
        licoes = []
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
    tarefa.append("## Ferramentas expostas nesta execucao\n"
                  + ", ".join(["entregar_saida", *expostas])
                  + ". Use os nomes e argumentos dos contratos fornecidos. "
                  "Nao declare uma ferramenta exposta como indisponivel. "
                  "Uma funcao equivalente exposta pode substituir um nome historico indisponivel. "
                  "Entregar_saida e o caminho de gravacao: a aplicacao valida, "
                  "persiste o resultado e registra a conclusao da tarefa juntas; "
                  "nao depende de uma segunda ferramenta registrar_*.")
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

def _checar_claims(repo: Any, task: dict[str, Any], saida: Any,
                   **_: Any) -> list[str]:
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
                   session_id: int, **_: Any) -> list[int]:
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


def _checar_plano(repo: Any, task: dict[str, Any], saida: Any, *,
                  teto: float, raiz: Any) -> list[str]:
    from src.casefile import coordenacao
    return coordenacao.checar_proposta(repo, task["unit_id"], saida,
                                       teto=teto, pacote=task.get("pack", ""),
                                       raiz=raiz)


def _gravar_plano(repo: Any, task: dict[str, Any], saida: Any,
                  session_id: int, *, run_id: int | None = None,
                  **_: Any) -> list[int]:
    """NÃO cria tarefas: guarda a PROPOSTA para o operador decidir."""
    from src.casefile import coordenacao
    return [coordenacao.registrar_proposta(repo, task, saida, run_id=run_id)]


VALIDADORES: dict[str, Callable[..., list[str]]] = {
    "claims": _checar_claims, "plano_tarefas": _checar_plano}
GRAVADORES: dict[str, Callable[..., list[int]]] = {
    "claims": _gravar_claims, "plano_tarefas": _gravar_plano}


def ferramentas_padrao(repo: Any, task: dict[str, Any]
                       ) -> dict[str, tuple[dict[str, Any], Callable]]:
    """Ferramentas que o próprio código implementa para uma função. A ficha
    continua sendo a lista de permissão (só se expõe o que ela declara)."""
    if task["role"] == "coordenador":
        from src.casefile import coordenacao
        return coordenacao.ferramentas_do_coordenador(repo, task["unit_id"])
    return {}


# --- executar ---------------------------------------------------------------------

class TetoDaTarefa(RuntimeError):
    """A próxima chamada poderia passar do saldo da tarefa: não é feita."""


def estimar_chamada(kw: dict[str, Any], modelo: str) -> float:
    """Text characters plus the documented visual-token ceiling, never base64.

    Vision bounds verified 2026-10-12: platform.claude.com/docs/en/build-with-claude/vision;
    developers.openai.com/api/docs/guides/images-vision. Cache discounts are ignored.
    """
    rate = RATES[modelo]
    visual_tokens=0
    def budget_content(value):
        nonlocal visual_tokens
        if isinstance(value,list):return [budget_content(x) for x in value]
        if not isinstance(value,dict):return value
        if value.get('type')=='image' and value.get('source',{}).get('type')=='base64':
            ceiling=4784 if modelo.startswith('claude-') else 36001 if modelo.startswith('gpt-5.6-') else None
            if ceiling is not None:
                visual_tokens+=ceiling
                return {'type':'image','source':{'type':'base64','media_type':value['source'].get('media_type')}}
        return {k:budget_content(v) for k,v in value.items()}
    carga = json.dumps(budget_content({k: kw.get(k) for k in ("system", "messages", "tools")}),
                       ensure_ascii=False, default=str)
    estimated_input=len(carga)/3+visual_tokens
    # Reserve the larger long-context price before a GPT request; an extra
    # output margin is deliberate. Never apply cache discounts to a ceiling.
    multiplier=2 if modelo.startswith('gpt-5.6-') and estimated_input>272000 else 1
    return multiplier*(estimated_input*rate['input']+int(kw.get('max_tokens') or 0)*rate['output'])/1_000_000


class _ClienteContado:
    """Soma o uso de cada resposta ANTES de o laço seguir (erro da API ou
    trava perdida não apagam o gasto) e recusa a próxima chamada quando o
    gasto + o pior caso estimado dela passaria do teto da tarefa."""

    def __init__(self, inner: Any, uso: Usage, modelo: str,
                 teto: float, accounting: Any = None) -> None:
        self.inner, self.uso, self.turnos = inner, uso, 0
        self.modelo, self.teto = modelo, teto
        self.messages = self
        self.accounting = accounting
        self.manages_retries = accounting is not None

    def create(self, **kw: Any) -> Any:
        gasto = self.uso.cost(self.modelo) or 0.0
        previsto = estimar_chamada(kw, self.modelo)
        if gasto + previsto > self.teto:
            raise TetoDaTarefa(
                f"teto_da_tarefa: gasto ${gasto:.4f} + pior caso da próxima "
                f"chamada ${previsto:.4f} > teto ${self.teto:.4f}")
        if self.accounting:
            if self.modelo.startswith('claude-'):
                kw['service_tier']='standard_only'
            self.accounting.before(previsto)
        for attempt in range(3):
            if attempt and self.accounting:
                self.accounting.before(previsto)
            try:
                msg = self.inner.messages.create(**kw)
                break
            except Exception as exc:
                if not self.accounting:
                    raise
                rejection=self.accounting.failure(exc)
                if rejection.status_code not in (429,529) or attempt==2:
                    raise rejection from exc
                # Only the application retries confirmed nonbillable throttle
                # responses. An uncertain request never reaches this branch.
                import time
                header=getattr(getattr(exc,'response',None),'headers',{}).get('retry-after','')
                try: delay=min(60,max(1,float(header)))
                except (ValueError,TypeError): delay=2**attempt
                if not __import__('math').isfinite(delay): delay=60
                time.sleep(delay)
        if self.accounting and msg.usage is None:
            self.accounting.response(msg, {}, 0)
        self.uso.add(msg.usage)
        self.turnos += 1
        if self.accounting:
            request_usage=Usage()
            request_usage.add(msg.usage)
            self.accounting.response(msg, request_usage.to_dict(self.modelo),
                                     round(request_usage.cost(self.modelo) or 0.0, 6))
        return msg


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _limitado_por_outros(conta: dict[str, float]) -> bool:
    """O que falta é dinheiro RESERVADO por runs abertos de outros workers
    (volta quando eles fecharem), não saldo gasto."""
    return (conta["reservado_por_outros"] > 0 and conta["saldo_tarefa"] > 0
            and conta["saldo_unit"] > 0
            and conta["saldo_unit"] - conta["reservado_por_outros"]
            < conta["saldo_tarefa"])


def executar_uma(repo: Any, unit_id: int, worker: str, *, teto: float,
                 client: Any = None, raiz: str | Path | None = None,
                 ferramentas: dict[str, tuple[dict[str, Any], Callable]] | None = None,
                 modelos: dict[str, str] | None = None,
                 lease_segundos: int = orq.LEASE_PADRAO_S,
                 max_turnos: int = MAX_TURNOS_PADRAO,
                 operation: bool = False) -> dict[str, Any] | None:
    """Uma tarefa, do `pegar` ao `entregar`. None quando não há tarefa pronta
    para este worker. TetoAtingido sobe (pendentes já bloqueadas). Unit com
    perfil surface é recusada antes de qualquer efeito."""
    from src.casefile import coordenacao
    if operation:
        from src.casefile import runtime, project_profile
        from src.casefile.operations import require_running
        case = require_running(repo, unit_id)
        teto = float(case['approved_budget_usd'])
        unit = next(u for u in repo.listar_units() if u['id'] == unit_id)
        if not project_profile.selected(repo, unit):
            raise ValueError('surface_explicit_profile_required')
    else:
        coordenacao.exigir_etapa_suportada(repo, unit_id, "trabalhar")
    terminal = operation and case['profile'].get('execution_backend') == 'terminal'
    # Issue 10: in operation the Case's latest Round decides inside the pick
    # itself: a closed Round picks nothing until a new one is approved, and
    # a focused Round picks only its focus task and its follow-ups.
    got = orq.pegar(repo, unit_id, worker, teto=teto, raiz=raiz,
                    lease_segundos=lease_segundos,
                    excluir_roles=() if operation else FUNCOES_FORA_DO_WORKER,
                    max_active_per_unit=1 if operation else None,
                    rodada=operation)
    if got is None:
        if operation:
            from src.casefile import rounds
            rounds.close_focus_if_done(repo, unit_id)
        return None
    task, run = got
    if operation:
        task['_operation_run_id'] = run['id']
    ferramentas = {**(runtime.tools(repo, task) if operation else ferramentas_padrao(repo, task)), **(ferramentas or {})}
    ctx = montar_contexto(task, raiz=raiz,
                          ferramentas_disponiveis=set(ferramentas),
                          blind=operation and (task['role'] == 'verificador' or task['input_json'].get('independent_comparison')))
    nivel = ctx["funcao"].front["nivel_modelo"]
    if operation and case['profile'].get('model_policy')=='economic' and task['role'] in ('coordenador','examinador'):
        nivel='medio'
    modelo = (modelos or MODELO_POR_NIVEL)[nivel]
    familia = FAMILIA
    if operation and (task['role'] == 'verificador' or task['input_json'].get('independent_comparison')):
        from src.casefile.verificador import modelo_b
        modelo, familia = modelo_b(), 'B'
    if terminal:
        from src.infra.terminal import codex_model
        modelo = 'terminal/codex/' + codex_model() if familia == 'B' else 'terminal/claude/' + ('opus' if nivel == 'forte' else 'haiku' if nivel in ('barato','barato_a_medio') else 'sonnet')
        repo.conn.execute("UPDATE task_runs SET execution_backend='terminal' WHERE id=%s", (run['id'],))
    if not terminal and modelo not in RATES:
        repo.fechar_run(run["id"], worker, output_json=None,
                        output_valid=None, validation_errors=[],
                        stop_reason="modelo_sem_tarifa", para="pronta",
                        nota=f"modelo sem tarifa: {modelo}")
        raise ValueError(f"modelo_sem_tarifa: {modelo!r} — custo invisível "
                         f"não roda")

    # reserva NO BANCO antes de qualquer chamada: dois workers nunca contam o
    # mesmo saldo da unit (a reserva é liberada quando o run fecha)
    conta = {'limite': 1} if terminal else repo.reservar_orcamento(run["id"], worker, teto)
    limite = conta["limite"]

    def _devolver(motivo: str, nota: str, **meta: Any) -> dict[str, Any]:
        # saldo preso em reservas de OUTROS runs abertos: a tarefa volta à
        # fila sem contar tentativa nem abrir escalonamento
        t = repo.fechar_run(run["id"], worker, output_json=None,
                            output_valid=None, validation_errors=[],
                            stop_reason=motivo, para="pronta", nota=nota,
                            **meta)
        return {"tarefa": t, "run_id": run["id"], "erros": [nota],
                "teto_atingido": False, "modelo": modelo,
                "custo_usd": meta.get("cost_usd", 0.0), "parada": motivo,
                "entregas": 0, "gravados": [], "proposta_id": None,
                "limite_usd": limite, "licoes": ctx["licoes"],
                "indisponiveis": ctx["indisponiveis"]}

    def _bloquear(motivo: str, nota: str, **meta: Any) -> dict[str, Any]:
        # sem saldo para (mais) uma chamada: nenhuma chamada paga começa; a
        # tarefa para e o operador é avisado (orçamento zero ou insuficiente
        # nunca vira execução ilimitada nem tentativa repetida)
        t = repo.fechar_run(run["id"], worker, output_json=None,
                            output_valid=None, validation_errors=[],
                            stop_reason=motivo, para="bloqueada", nota=nota,
                            **meta)
        repo.abrir_escalonamento(
            unit_id, task["id"], "orcamento_tarefa",
            f"Tarefa {task['ref']!r} sem saldo para chamar modelo ({nota}). "
            f"Aumentar o orçamento da tarefa ou cancelar?",
            ["aumentar orçamento", "cancelar a tarefa"])
        result={"tarefa": t, "run_id": run["id"], "erros": [nota],
                "teto_atingido": False, "modelo": modelo,
                "custo_usd": meta.get("cost_usd", 0.0), "parada": motivo,
                "entregas": 0, "gravados": [], "proposta_id": None,
                "limite_usd": limite, "licoes": ctx["licoes"],
                "indisponiveis": ctx["indisponiveis"]}
        if operation:runtime.finalize(repo,task,result)
        return result

    if limite <= 0:
        if _limitado_por_outros(conta):
            return _devolver(
                "saldo_reservado_por_outros",
                f"saldo da unit reservado por outros runs abertos: livre "
                f"${conta['saldo_unit'] - conta['reservado_por_outros']:.4f}")
        return _bloquear("sem_saldo",
                         f"orcamento_da_tarefa_esgotado: saldo ${limite:.4f} "
                         f"(budget ${task['budget_usd']:.2f})")

    handler = runtime.handlers().get(task['output_schema']) if operation else None
    if operation and handler is None:
        repo.fechar_run(run['id'],worker,output_json=None,output_valid=False,
                        validation_errors=['result_handler_not_implemented'],stop_reason='unsupported_output',para='bloqueada')
        raise ValueError('result_handler_not_implemented')
    checar = handler[0] if handler else VALIDADORES.get(task["output_schema"])
    validar_extra = (lambda t, s: checar(repo, {**t,'_operation_run_id':run['id']} if operation else t, s, teto=teto, raiz=raiz)
                     ) if checar else None
    entrega: dict[str, Any] = {"saida": None, "entregas": 0, "arquivo": None}

    def _entregar_saida(saida: Any) -> dict[str, Any]:
        erros = agentes.validar_saida(task["output_schema"], saida, raiz)
        if not erros and validar_extra is not None:
            erros = validar_extra(task, saida)
        if operation:
            # Issue 03: the output file is written BEFORE the delivery counts
            # and before anything is applied — accepted or rejected with the
            # reason. A delivery whose file cannot be written is not received.
            from src.casefile import function_files
            entrega["arquivo"] = function_files.write_output(
                repo, task, run["id"], entrega["entregas"] + 1, saida, erros)
        entrega["saida"], entrega["entregas"] = saida, entrega["entregas"] + 1
        return {"recebida": True, "valida": not erros, "erros": erros[:20]}

    tools = [FERRAMENTA_ENTREGA] + [ferramentas[n][0]
                                   for n in ctx["ferramentas"]]
    dispatch = {"entregar_saida": _entregar_saida,
                **{n: ferramentas[n][1] for n in ctx["ferramentas"]}}
    session_id = repo.abrir_sessao(unit_id, f"tarefa:{task['id']}", modelo)
    if operation:
        from src.casefile.accounting import RunAccounting
        from src.casefile.repo import _json
        ctx['tarefa'] += runtime.context(repo,task)
        repo.conn.execute('UPDATE task_runs SET operation_session_id=%s WHERE id=%s',(session_id,run['id']))
        if familia == 'B':
            repo.knowledge_context(unit_id,session_id,{'status':'independent_comparison' if task['input_json'].get('independent_comparison') else 'independent_blind','command':'tarefa:'+task['role'],
                                  'release_id':None,'cards':[],'expected_criteria':[],'methodology_supplied':False})
        else:
            from src.casefile.training_runtime import prepare
            provenance={'role':task['role'],'role_version':run['role_version'],'pack':task['pack'],
                'pack_version':run['pack_version'],'lessons':[{'path':p,'sha256':agentes.versao((Path(raiz) if raiz else agentes.RAIZ_PADRAO)/p)} for p in ctx['licoes']]}
            training_context, training_tools, training_dispatch = prepare(repo,unit,session_id,'tarefa:'+task['role'],provenance=provenance)
            ctx['sistema'] += training_context
            tools += training_tools
            dispatch.update(training_dispatch)
            manifest=repo.knowledge_audit(unit_id)['contexts'][-1]['manifest']
            repo.conn.execute('UPDATE task_runs SET knowledge_release_id=%s WHERE id=%s',(manifest.get('release_id'),run['id']))
        repo.operation_event('task.started',ATOR,{'run_id':run['id'],'model':modelo,'family':familia},unit_id=unit_id,task_id=task['id'])
        repo.conn.execute('UPDATE task_runs SET model=%s,model_family=%s,prompt_sha256=%s WHERE id=%s',
                          (modelo,familia,_sha(ctx['sistema']+'\n\n'+ctx['tarefa']),run['id']))

    fingerprints = []
    class OutputDelivered(Exception):
        pass

    def _renovar(_registro: Any) -> None:
        repo.renovar_lease(run["id"], worker, lease_segundos)
        if operation:
            from src.casefile.training import digest
            fingerprint=digest(_registro.calls)
            fingerprints.append(fingerprint)
            repo.operation_event('task.turn',ATOR,{'run_id':run['id'],'turn':_registro.turn,
                                                  'calls':_registro.calls},unit_id=unit_id,task_id=task['id'])
            if len(fingerprints)>=3 and len(set(fingerprints[-3:]))==1:
                raise ExecutionNeedsReview('no_progress_after_two_retries')
            if entrega['entregas']>=3 and (agentes.validar_saida(task['output_schema'],entrega['saida'],raiz) or validar_extra(task,entrega['saida'])):
                raise ExecutionNeedsReview('two_output_corrections_exhausted')
            if entrega['saida'] is not None and not agentes.validar_saida(task['output_schema'],entrega['saida'],raiz) and not validar_extra(task,entrega['saida']):
                raise OutputDelivered()

    if client is None:
        if operation:
            from src.infra.providers import client as provider_client
            try:
                client = provider_client(familia, transport='terminal') if terminal else provider_client(familia)
            except Exception as exc:
                reason='provider_not_called:'+type(exc).__name__
                repo.fechar_sessao(session_id,reason,0,{},0,'')
                repo.conn.execute("UPDATE task_runs SET usage_state='not_called' WHERE id=%s",(run['id'],))
                t=repo.fechar_run(run['id'],worker,output_json=None,output_valid=False,
                                  validation_errors=[reason],stop_reason=reason,para='bloqueada')
                repo.operation_update(unit_id,execution_state='waiting')
                repo.operation_event('provider.unavailable',ATOR,{'reason':reason},unit_id=unit_id,task_id=task['id'])
                return {'tarefa':t,'run_id':run['id'],'erros':[reason],'teto_atingido':False,
                        'modelo':modelo,'custo_usd':0,'parada':reason,'entregas':0,'gravados':[],'proposta_id':None,
                        'limite_usd':limite,'licoes':ctx['licoes'],'indisponiveis':ctx['indisponiveis']}
        else:
            from src.infra.loop import _client
            client = _client()
    uso = Usage()
    if terminal:
        from src.casefile.terminal_accounting import TerminalClient
        contado = TerminalClient(client, repo, task, run, uso, familia)
    else:
        contado = _ClienteContado(client, uso, modelo, limite,
                                 RunAccounting(repo,task,run) if operation else None)
    falha = ""
    provider_rejection = None
    execution_block = None
    round_stop = None
    perdido: TransicaoInvalida | None = None
    try:
        log, _ = run_loop(system=ctx["sistema"], task=ctx["tarefa"],
                          tools=tools, dispatch=dispatch, model=modelo,
                          max_turns=min(max_turnos,40) if terminal else max_turnos,
                          max_cost_usd=None if terminal else limite,
                          max_output_tokens=16000 if operation and task['role']=='coordenador' else 8000,
                          on_turn=_renovar, client=contado)
        parada = log.stop_reason
    except OutputDelivered:
        parada = 'saida_entregue'
    except TransicaoInvalida as exc:              # trava perdida no meio
        perdido, parada = exc, f"trava_perdida: {exc}"
    except TetoDaTarefa as exc:                   # parou ANTES de pedir
        parada, falha = str(exc), "teto_da_tarefa"
    except Exception as exc:                      # o run não fica órfão
        if operation:
            from src.casefile.accounting import ProviderUnavailable,UnknownProviderUsage
            from src.casefile.spending import SharedSpendingCap
            from src.infra.terminal import TerminalError
            from src.casefile.rounds import RoundTurnCapReached
            if isinstance(exc,RoundTurnCapReached): round_stop=exc.code
            if isinstance(exc,ProviderUnavailable): provider_rejection=exc
            if isinstance(exc,(ExecutionNeedsReview,UnknownProviderUsage,SharedSpendingCap)):execution_block=str(exc)
            if isinstance(exc,TerminalError):execution_block=str(exc)
        parada = provider_rejection.reason if provider_rejection else f"erro_do_modelo: {exc.__class__.__name__}: {exc}"
        falha = "erro_do_modelo"
    custo = uso.cost(modelo) or 0.0
    if operation:
        custo=float(repo.conn.execute("SELECT coalesce(sum(cost_usd),0) AS amount FROM operation_requests WHERE run_id=%s AND status='confirmed'",(run['id'],)).fetchone()['amount'])
    usage_unknown = operation and repo.run(run['id']).get('usage_state') in ('unknown','inflight')
    repo.fechar_sessao(session_id, parada, contado.turnos,
                       {**uso.to_dict(modelo), **({'billing_mode':'subscription','api_charge_usd':0,'subscription_charge_usd':None} if terminal else {})},
                       None if usage_unknown or terminal else custo, "")
    if perdido is not None:
        _custo_perdido(repo, unit_id, task, run, custo)
        raise perdido

    meta = {"model": modelo, "model_family": familia,
            "prompt_sha256": _sha(ctx["sistema"] + "\n\n" + ctx["tarefa"]),
            "tokens_in": uso.input + uso.cache_write + uso.cache_read,
            "tokens_out": uso.output, "cost_usd": custo}
    if round_stop:
        # Issue 08: the Round has no turn left. Nothing about the task is
        # wrong: it goes back to ready, uncounted, and the Case waits for
        # Renato to approve a new Round. The reason is the run's stop reason.
        with repo.transacao():
            # Nothing delivered means no output to judge: validity stays unset.
            t=repo.fechar_run(run['id'],worker,output_json=entrega['saida'],
                             output_valid=False if entrega['entregas'] else None,
                             validation_errors=[round_stop],stop_reason=round_stop,para='pronta',**meta)
            repo.operation_update(unit_id,execution_state='waiting')
            result={'tarefa':t,'run_id':run['id'],'erros':[round_stop],'teto_atingido':False,
                    'modelo':modelo,'custo_usd':custo,'parada':round_stop,'entregas':entrega['entregas'],
                    'gravados':[],'proposta_id':None,'limite_usd':limite,'licoes':ctx['licoes'],'indisponiveis':ctx['indisponiveis']}
            runtime.finalize(repo,task,result)
        return result
    if execution_block:
        with repo.transacao():
            t=repo.fechar_run(run['id'],worker,output_json=entrega['saida'],output_valid=False,
                             validation_errors=[execution_block],stop_reason=execution_block,para='bloqueada',**meta)
            from src.casefile.operations import has_unbounded_usage
            if execution_block!='provider_usage_requires_reconciliation' or has_unbounded_usage(repo,unit_id):
                repo.operation_update(unit_id,execution_state='waiting')
            repo.abrir_escalonamento(unit_id,task['id'],'execution_block',
                'A tarefa parou sem nova chamada: '+execution_block+'. Responsável: operação local / Renato. Corrigir a entrada ou reconciliar o uso antes de retomar.',
                ['corrigir entrada ou contrato','conferir custo e recibo'])
            result={'tarefa':t,'run_id':run['id'],'erros':[execution_block],'teto_atingido':False,
                    'modelo':modelo,'custo_usd':custo,'parada':execution_block,'entregas':entrega['entregas'],
                    'gravados':[],'proposta_id':None,'limite_usd':limite,'licoes':ctx['licoes'],'indisponiveis':ctx['indisponiveis']}
            runtime.finalize(repo,task,result)
        return result
    if falha == "teto_da_tarefa" and entrega["entregas"] == 0:
        if contado.turnos == 0 and _limitado_por_outros(conta):
            return _devolver("saldo_reservado_por_outros", parada, **meta)
        return _bloquear("teto_da_tarefa", parada, **meta)
    if provider_rejection:
        with repo.transacao():
            t=repo.fechar_run(run['id'],worker,output_json=None,output_valid=False,
                             validation_errors=[provider_rejection.reason],stop_reason=provider_rejection.reason,
                             para='bloqueada',**meta)
            repo.operation_update(unit_id,execution_state='waiting')
            instructions={
                'provider_credit_balance_insufficient':'A conta Anthropic está sem saldo. Renato deve regularizar o saldo ou configurar uma chave com saldo; compras exigem autorização própria.',
                'provider_credentials_invalid':'Renato deve conferir a credencial configurada antes de retomar.',
                'provider_access_denied':'Renato deve regularizar o acesso à API antes de retomar.',
                'provider_rate_limited':'O provedor recusou três chamadas sem cobrança por limite de acesso. Retomar após regularizar o limite.',
                'provider_overloaded':'O provedor recusou três chamadas sem cobrança por sobrecarga. Retomar quando o serviço estiver disponível.'}
            note=instructions.get(provider_rejection.reason,'Conferir a configuração da chamada e do modelo antes de retomar. Nenhum resultado foi produzido por esta chamada.')
            if not any(e['motivo']=='provider_access' for e in repo.escalonamentos(unit_id,abertos=True)):
                repo.abrir_escalonamento(unit_id,task['id'],'provider_access',note,['regularizar acesso','retomar dentro da autorização vigente'])
            result={'tarefa':t,'run_id':run['id'],'erros':[provider_rejection.reason],'teto_atingido':False,
                    'modelo':modelo,'custo_usd':custo,'parada':parada,'entregas':entrega['entregas'],'gravados':[],
                    'proposta_id':None,'limite_usd':limite,'licoes':ctx['licoes'],'indisponiveis':ctx['indisponiveis']}
            runtime.finalize(repo,task,result)
        return result
    if falha == "erro_do_modelo":
        motivo = falha
    elif entrega["entregas"] == 0:
        motivo = falha or "sem_entrega"
    else:
        motivo = ""
    gravados: list[int] = []
    gravar = handler[1] if handler else GRAVADORES.get(task["output_schema"])
    try:
        with repo.transacao():
            res = orq.entregar(repo, run["id"], worker, entrega["saida"],
                               teto=teto, raiz=raiz, validar_extra=validar_extra,
                               motivo_invalida=motivo, **meta)
            arquivo = None
            if operation and not res['erros']:
                # Only an accepted output file is applied; every row created
                # from here to commit cites its sha256 (issue 03).
                from src.casefile import function_files
                arquivo = function_files.begin_apply(repo, entrega.get('arquivo'))
            if not res['erros'] and gravar is not None:
                gravados = gravar(repo,task,entrega['saida'],session_id,
                                   teto=teto,raiz=raiz,run_id=run['id'])
            if operation and not res['erros']:
                runtime.finalize(repo,task,{'run_id':run['id'],'erros':[],
                    'tarefa':res['tarefa'],'gravados':gravados,'custo_usd':custo,'modelo':modelo,'parada':parada})
                function_files.finish_apply(repo, arquivo)
    except TransicaoInvalida:
        _custo_perdido(repo, unit_id, task, run, custo)
        raise

    except Exception as exc:
            res = {'tarefa':repo.fechar_run(run['id'],worker,output_json=entrega['saida'],output_valid=False,
                      validation_errors=[str(exc)],stop_reason='result_not_persisted',para='aguardando_operador',**meta),
                   'erros':[str(exc)],'teto_atingido':False}
            # validou na entrega e falhou ao gravar (o estado mudou no meio):
            # nada fica aceito por omissão — volta ao operador, com motivo.
            atual = repo.tarefa(task["id"])
            if atual["status"] != "aguardando_operador":
                res["tarefa"] = repo.transicionar_tarefa(
                    task["id"], (atual["status"],), "aguardando_operador",
                    ATOR, f"saida_valida_nao_gravada: {exc}")
            repo.abrir_escalonamento(
                unit_id, task["id"], "gravacao",
                f"A saída da tarefa {task['ref']!r} passou na validação mas "
                f"não pôde ser gravada: {exc}", ["reexecutar", "recusar"])
            res["erros"] = [f"saida_valida_nao_gravada: {exc}"]
            gravados = []
    proposta = gravados[0] if gravados and \
        task["output_schema"] == "plano_tarefas" else None
    result = {"tarefa": res["tarefa"], "run_id": run["id"],
            "erros": res["erros"], "teto_atingido": res["teto_atingido"],
            "modelo": modelo, "custo_usd": custo, "parada": parada,
            "entregas": entrega["entregas"],
            "gravados": [] if proposta else gravados,
            "proposta_id": proposta, "limite_usd": limite,
            "licoes": ctx["licoes"], "indisponiveis": ctx["indisponiveis"]}
    if operation:
        if result['erros']:
            runtime.finalize(repo,task,result)
        result['tarefa']=repo.tarefa(task['id'])
    return result


def _custo_perdido(repo: Any, unit_id: int, task: dict[str, Any],
                   run: dict[str, Any], custo: float) -> None:
    """Trava vencida e retomada por outro worker: a saída não vale, mas o
    gasto aconteceu e entra no livro da unit."""
    if custo:
        if hasattr(repo,'operations_installed') and repo.operations_installed():
            recorded=repo.conn.execute("SELECT coalesce(sum(cost_usd),0) AS amount FROM operation_requests WHERE run_id=%s AND status='confirmed'",(run['id'],)).fetchone()['amount']
            custo=max(0,custo-float(recorded))
        if not custo:
            return
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
        if got["parada"] == "saldo_reservado_por_outros":
            parada = "saldo da unit reservado por outros workers"
            break
    else:
        parada = f"limite de {max_tarefas} tarefas nesta chamada"
    return {"execucoes": execucoes, "parada": parada,
            "custo_usd": round(sum(e["custo_usd"] for e in execucoes), 4)}
