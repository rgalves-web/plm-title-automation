"""Regras de FORMA da orquestração (ARQUITETURA_AGENTICA_v1 §6, etapa B).

As sete regras do §6, como encanamento:
1. tarefa só fica `pronta` com todas as dependências `aceita`;
2. worker pega tarefa com trava que expira; queda libera sem perda;
3. saída validada contra o esquema da função; inválida volta com erro
   nomeado, no máximo 2 novas tentativas, depois `recusada`;
4. função com verificação obrigatória só vai a `aceita` com verificação
   válida e concordante de cada claim, ou decisão do árbitro/operador;
5. teto da unit (mesmo livro de custo do Case File): ao bater, pendentes
   vão a `bloqueada` e o operador recebe escalonamento;
6. verificador nunca recebe a saída da tarefa verificada (quarentena
   mecânica, no espírito de `verificador.afirmar_identidade`);
7. todo run registra a versão (sha256) da ficha da função e do pacote.

Nada aqui decide title nem escolhe entre saídas: conta, compara identidade,
confere esquema e trava. Vale igual para `Repo` e para o `RepoFake`.
"""
from __future__ import annotations

import json
import re
import math
from pathlib import Path
from typing import Any

from src.casefile import agentes
from src.casefile.orquestracao_repo import TransicaoInvalida

ATOR = "process:orquestracao"
MAX_RETENTATIVAS = 2
LEASE_PADRAO_S = 900

# `verifica` da ficha → o que a tarefa exige depois de saída válida.
# Valores sem mapeamento explícito (amostral, gate_de_captura,
# auditoria_de_celulas, operador_em_material, amostral_e_material…) caem no
# modo conservador `operador` até o operador decidir o vocabulário.
VERIFICA_PARA_MODO = {
    "nao": "nenhuma",
    "nao_aplicavel": "nenhuma",
    "obrigatoria": "obrigatoria",
    "obrigatoria_e_operador": "obrigatoria_e_operador",
    "operador": "operador",
}
MODO_CONSERVADOR = "operador"
DESTINO_SAIDA_VALIDA = {
    "nenhuma": "aceita",
    "obrigatoria": "aguardando_verificacao",
    "obrigatoria_e_operador": "aguardando_verificacao",
    "operador": "aguardando_operador",
}
EM_ABERTO = ("planejada", "pronta", "em_execucao")
# Saídas que NUNCA se aceitam sem o operador, qualquer que seja o `verifica`
# da ficha: um grafo de tarefas decide o que a firma vai gastar e fazer.
ESQUEMAS_COM_ACEITE_HUMANO = frozenset({"plano_tarefas"})

CAMPOS_ENTRADA_VERIFICADOR = frozenset(
    {"tarefa_verificada", "claim_id", "claim_type", "source_sha256",
     "pagina", "pergunta"})
CHAVES_DE_RESPOSTA = frozenset(
    {"valor", "value", "trecho", "evidence", "output_json",
     "verifier_value"})
_ATOR_HUMANO = re.compile(r"^human:[\w.-]+$")


class PlanoInvalido(ValueError):
    """O plano não tem a forma, as referências ou o orçamento exigidos."""


class FichasInvalidas(ValueError):
    """As fichas de agentes/ não passam na validação; nada roda sobre elas."""


class TetoAtingido(RuntimeError):
    """Custo acumulado da unit >= teto: pendentes bloqueadas, operador avisado."""


class QuarentenaViolada(AssertionError):
    """A entrada do verificador carrega algo da resposta verificada."""


class DecisaoInvalida(ValueError):
    """Aceite ou recusa sem o ator, o estado ou a evidência exigidos."""


def modo_verificacao(verifica: Any) -> str:
    return VERIFICA_PARA_MODO.get(str(verifica or "").strip(),
                                  MODO_CONSERVADOR)


# --- fichas e versões ---------------------------------------------------------

def _fichas(raiz: str | Path | None) -> agentes.Resultado:
    r = agentes.validar(raiz)
    if not r.ok:
        erros = [f"{f.rel}: {a}" for f in r.fichas for a in f.erros] + \
            [str(a) for a in r.erros_esquemas]
        raise FichasInvalidas("fichas com erro: " + "; ".join(erros[:5]))
    return r


def registrar_versoes(repo: Any, raiz: str | Path | None = None
                      ) -> tuple[dict[str, str], dict[str, str]]:
    """sha256 de cada Role e Domain Pack, gravado com o conteúdo em
    role_versions. Devolve ({função: sha}, {pacote: sha})."""
    r = _fichas(raiz)
    funcoes: dict[str, str] = {}
    pacotes: dict[str, str] = {}
    for tipo, destino in (("Role", funcoes), ("Domain Pack", pacotes)):
        for f in r.por_tipo(tipo):
            sha = agentes.versao(f.caminho)
            repo.registrar_versao_ficha(
                sha, f.rel, tipo, f.nome,
                f.caminho.read_bytes().decode("utf-8"))
            destino[f.nome] = sha
    return funcoes, pacotes


# --- planejar -------------------------------------------------------------------

def _ordem_topologica(tarefas: list[dict[str, Any]],
                      existentes: set[str]) -> list[dict[str, Any]]:
    refs = [t["ref"] for t in tarefas]
    repetidas = sorted({r for r in refs if refs.count(r) > 1})
    if repetidas:
        raise PlanoInvalido(f"ref_duplicada no plano: {repetidas}")
    colisao = sorted(set(refs) & existentes)
    if colisao:
        raise PlanoInvalido(f"ref_duplicada: já existem na unit: {colisao}")
    no_lote = set(refs)
    for t in tarefas:
        faltam = [d for d in t["depends_on"]
                  if d not in no_lote and d not in existentes]
        if faltam:
            raise PlanoInvalido(
                f"dependencia_inexistente em {t['ref']!r}: {faltam}")
    pendentes = {t["ref"]: {d for d in t["depends_on"] if d in no_lote}
                 for t in tarefas}
    por_ref = {t["ref"]: t for t in tarefas}
    ordem: list[dict[str, Any]] = []
    while pendentes:
        livres = [r for r in refs if r in pendentes and not pendentes[r]]
        if not livres:
            raise PlanoInvalido(
                f"ciclo_de_dependencias entre {sorted(pendentes)}")
        for r in livres:
            ordem.append(por_ref[r])
            del pendentes[r]
        for deps in pendentes.values():
            deps.difference_update(livres)
    return ordem


def _checar(repo: Any, unit_id: int, plano: dict[str, Any], *, teto: float,
            pacote: str, raiz: str | Path | None, excluir_tarefa: int | None = None
            ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Toda a checagem de forma de um plano, sem gravar. Devolve a ordem
    topológica e as fichas de função; erro vira PlanoInvalido."""
    erros = agentes.validar_saida("plano_tarefas", plano, raiz)
    if erros:
        raise PlanoInvalido("plano fora do esquema: " + "; ".join(erros[:5]))
    r = _fichas(raiz)
    funcoes = {f.nome: f for f in r.por_tipo("Role")}
    pacotes = {f.nome for f in r.por_tipo("Domain Pack")}
    if pacote and pacote not in pacotes:
        raise PlanoInvalido(f"pacote_inexistente: {pacote!r}")
    tarefas = plano["tarefas"]
    for t in tarefas:
        if not math.isfinite(float(t['budget_usd'])) or t['budget_usd']<0:
            raise PlanoInvalido('orcamento_da_tarefa_nao_finito')
        if t["role"] not in funcoes:
            raise PlanoInvalido(f"funcao_inexistente: {t['role']!r}")
        if t["role"] == "verificador":
            extras = sorted(set(t["input_json"]) - CAMPOS_ENTRADA_VERIFICADOR)
            if extras:
                raise PlanoInvalido(
                    f"quarentena: entrada do verificador {t['ref']!r} com "
                    f"campos proibidos {extras}")
    existentes = repo.tarefas(unit_id)
    ordem = _ordem_topologica(tarefas, {t["ref"] for t in existentes})

    saldo = round(teto - repo.custo_acumulado(unit_id), 4)
    comprometido = sum(t["budget_usd"] for t in existentes
                       if t["status"] in EM_ABERTO and t['id'] != excluir_tarefa)
    novo = sum(t["budget_usd"] for t in tarefas)
    if comprometido + novo > saldo + 1e-9:
        raise PlanoInvalido(
            f"orcamento_do_plano_excede_saldo: novo ${novo:.2f} + em aberto "
            f"${comprometido:.2f} > saldo ${saldo:.2f} (teto ${teto:.2f})")
    return ordem, funcoes


def checar_plano(repo: Any, unit_id: int, plano: dict[str, Any], *,
                 teto: float, pacote: str = "",
                 raiz: str | Path | None = None, excluir_tarefa: int | None = None) -> list[str]:
    """Os erros de forma que `planejar` recusaria — lista vazia = grava.
    É o que o Coordenador recebe de volta ao entregar."""
    try:
        _checar(repo, unit_id, plano, teto=teto, pacote=pacote, raiz=raiz,excluir_tarefa=excluir_tarefa)
    except PlanoInvalido as exc:
        return [str(exc)]
    return []


def linhas_do_plano(repo: Any, unit_id: int, plano: dict[str, Any], *,
                    teto: float, pacote: str = "",
                    raiz: str | Path | None = None, excluir_tarefa: int | None = None) -> list[dict[str, Any]]:
    """Checa o plano e devolve as linhas prontas para `criar_tarefas`, em
    ordem topológica. Não grava."""
    ordem, funcoes = _checar(repo, unit_id, plano, teto=teto, pacote=pacote,
                             raiz=raiz,excluir_tarefa=excluir_tarefa)
    linhas = []
    for t in ordem:
        ficha = funcoes[t["role"]]
        linhas.append({
            "ref": t["ref"], "role": t["role"], "pack": pacote,
            "title": t["title"], "input_json": t["input_json"],
            "output_schema": ficha.front["saida_esquema"],
            "acceptance": t["acceptance"],
            "depends_on_refs": list(t["depends_on"]),
            "budget_usd": t["budget_usd"], "priority": t["priority"],
            "verificacao": modo_verificacao(ficha.front.get("verifica")),
            "pendencias": list(t.get("pendencias", [])),
            "justificativa": (f"[{t['gate']}] " if t.get("gate") else "")
            + t["justificativa"]})
    return linhas


def planejar(repo: Any, unit_id: int, plano: dict[str, Any], *,
             criado_por: str, teto: float, pacote: str = "",
             raiz: str | Path | None = None) -> list[dict[str, Any]]:
    """Grava o grafo de tarefas de um `plano_tarefas`. Tudo ou nada.
    Uso direto só por quem já tem a autoridade (operador, semeadura); a
    saída do Coordenador passa por `coordenacao.aprovar_proposta`."""
    linhas = linhas_do_plano(repo, unit_id, plano, teto=teto, pacote=pacote,
                             raiz=raiz)
    criadas = repo.criar_tarefas(unit_id, linhas, criado_por)
    repo.promover_prontas(unit_id, ATOR)
    return [repo.tarefa(t["id"]) for t in criadas]


# --- executar --------------------------------------------------------------------

def checar_teto(repo: Any, unit_id: int, teto: float) -> None:
    gasto = repo.custo_acumulado(unit_id)
    if gasto < teto:
        return
    nota = f"teto da unit atingido: ${gasto:.4f} >= ${teto:.2f}"
    repo.bloquear_pendentes(unit_id, ATOR, nota)
    if not any(e["motivo"] == "orcamento"
               for e in repo.escalonamentos(unit_id, abertos=True)):
        repo.abrir_escalonamento(
            unit_id, None, "orcamento",
            f"{nota}. Tarefas pendentes bloqueadas. Elevar o teto "
            f"(CASEFILE_TETO_UNIT_USD) ou encerrar?",
            ["elevar o teto", "encerrar a unit"])
    raise TetoAtingido(nota)


def pegar(repo: Any, unit_id: int, worker: str, *, teto: float,
          raiz: str | Path | None = None,
          lease_segundos: int = LEASE_PADRAO_S,
          excluir_roles: tuple[str, ...] = (), max_active_per_unit: int | None = None,
          somente_ids: list[int] | None = None
          ) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Libera travas vencidas, confere o teto, promove prontas e entrega a
    próxima (menor priority, depois id) com a versão das fichas no run.
    `excluir_roles`: funções que este worker não executa (ficam prontas).
    `somente_ids`: só estas tarefas podem ser entregues (foco da rodada)."""
    repo.liberar_leases_vencidos(unit_id, ATOR)
    checar_teto(repo, unit_id, teto)
    repo.promover_prontas(unit_id, ATOR)
    funcoes, pacotes = registrar_versoes(repo, raiz)
    if somente_ids is not None:
        return repo.pegar_tarefa(unit_id,worker,funcoes,pacotes,lease_segundos,tuple(excluir_roles),
                                 max_active_per_unit,somente_ids=list(somente_ids))
    if max_active_per_unit is None:
        return repo.pegar_tarefa(unit_id, worker, funcoes, pacotes,lease_segundos,tuple(excluir_roles))
    return repo.pegar_tarefa(unit_id,worker,funcoes,pacotes,lease_segundos,tuple(excluir_roles),max_active_per_unit)


def entregar(repo: Any, run_id: int, worker: str, saida: Any, *,
             teto: float, raiz: str | Path | None = None,
             validar_extra: Any = None, motivo_invalida: str = "",
             **meta: Any) -> dict[str, Any]:
    """Valida a saída contra o esquema da função (e, se dado,
    `validar_extra(task, saida) -> [erros]`, só quando o esquema passa),
    fecha o run e move a tarefa. Devolve {tarefa, erros, teto_atingido}."""
    run = repo.run(run_id)
    if run is None:
        raise TransicaoInvalida(f"run {run_id} inexistente")
    task = repo.tarefa(run["task_id"])
    erros = agentes.validar_saida(task["output_schema"], saida, raiz)
    if not erros and validar_extra is not None:
        erros = list(validar_extra(task, saida))
    if erros:
        invalidas = 1 + sum(1 for r in repo.runs_da_tarefa(task["id"])
                            if r["output_valid"] is False)
        esgotou = invalidas > MAX_RETENTATIVAS
        para = "recusada" if esgotou else "pronta"
        nota = (f"saida_fora_do_esquema ({invalidas}/"
                f"{MAX_RETENTATIVAS + 1}): {erros[0]}")
        motivo = motivo_invalida or "saida_invalida"
    elif task["output_schema"] in ESQUEMAS_COM_ACEITE_HUMANO:
        para, motivo = "aguardando_operador", "concluida"
        nota = "proposta aguarda aprovação explícita do operador"
    else:
        para = DESTINO_SAIDA_VALIDA[task["verificacao"]]
        nota, motivo = "", "concluida"
    task = repo.fechar_run(run_id, worker, output_json=saida,
                           output_valid=not erros, validation_errors=erros,
                           stop_reason=motivo, para=para, nota=nota, **meta)
    try:
        checar_teto(repo, task["unit_id"], teto)
        atingido = False
    except TetoAtingido:
        atingido = True
    return {"tarefa": task, "erros": erros, "teto_atingido": atingido}


# --- aceite ----------------------------------------------------------------------

def aceitar_por_verificacao(repo: Any, task_id: int) -> dict[str, Any]:
    """aguardando_verificacao → aceita só se CADA claim vinculado tem, como
    última verificação válida, `concordancia`. Tentativa não é concordância."""
    task = repo.tarefa(task_id)
    if task is None or task["status"] != "aguardando_verificacao":
        raise TransicaoInvalida(
            f"tarefa {task_id} não está aguardando_verificacao")
    claims = repo.claims_da_tarefa(task_id)
    if not claims:
        raise DecisaoInvalida(
            f"sem_claims_vinculados: tarefa {task_id} não tem o que verificar")
    pendentes, divergentes = [], {}
    for cid in claims:
        validas = [v for v in repo.verificacoes_do_claim(cid)
                   if v.get("status", "valida") == "valida"]
        if not validas:
            pendentes.append(cid)
            continue
        ultima = max(validas, key=lambda v: v["id"])
        if ultima["verdict"] != "concordancia":
            divergentes[cid] = ultima["verdict"]
    if pendentes or divergentes:
        return {"aceita": False, "tarefa": task, "sem_verificacao": pendentes,
                "nao_concordantes": divergentes}
    para = "aceita" if task["verificacao"] == "obrigatoria" \
        else "aguardando_operador"
    task = repo.transicionar_tarefa(
        task_id, ("aguardando_verificacao",), para, ATOR,
        f"{len(claims)} claims com verificação válida concordante")
    return {"aceita": para == "aceita", "tarefa": task, "sem_verificacao": [],
            "nao_concordantes": {}}


def decidir(repo: Any, task_id: int, *, aceitar: bool, ator: str,
            nota: str) -> dict[str, Any]:
    """Decisão explícita. `human:<id>` decide em aguardando_verificacao ou
    aguardando_operador; `tarefa:<id>` (Árbitro aceito, mesma unit) só
    substitui a verificação, nunca o aceite do operador."""
    task = repo.tarefa(task_id)
    if task is None:
        raise DecisaoInvalida(f"tarefa {task_id} inexistente")
    if not str(nota or "").strip():
        raise DecisaoInvalida("nota_ausente: decisão sem motivo registrado")
    estado = task["status"]
    if estado not in ("aguardando_verificacao", "aguardando_operador"):
        raise TransicaoInvalida(f"tarefa {task_id} está em {estado!r}")
    if _ATOR_HUMANO.match(ator or ""):
        para = "aceita" if aceitar else "recusada"
    elif (ator or "").startswith("tarefa:"):
        if estado != "aguardando_verificacao":
            raise DecisaoInvalida(
                "arbitro_nao_substitui_operador: tarefa aguarda o operador")
        arb = repo.tarefa(int(ator.split(":", 1)[1])) \
            if ator.split(":", 1)[1].isdigit() else None
        if arb is None or arb["role"] != "arbitro" or \
                arb["status"] != "aceita" or \
                arb["unit_id"] != task["unit_id"]:
            raise DecisaoInvalida(
                f"ator_invalido: {ator!r} não é tarefa de Árbitro aceita "
                f"desta unit")
        if not aceitar:
            para = "recusada"
        else:
            para = "aceita" if task["verificacao"] == "obrigatoria" \
                else "aguardando_operador"
    else:
        raise DecisaoInvalida(
            f"ator_invalido: {ator!r} (use human:<id> ou tarefa:<id>)")
    return repo.transicionar_tarefa(task_id, (estado,), para, ator, nota)


def desbloquear(repo: Any, unit_id: int, *, ator: str, teto: float
                ) -> list[int]:
    """bloqueada → planejada, só por humano e só com saldo."""
    if not _ATOR_HUMANO.match(ator or ""):
        raise DecisaoInvalida(f"ator_invalido: {ator!r} (só human:<id>)")
    gasto = repo.custo_acumulado(unit_id)
    if gasto >= teto:
        raise TetoAtingido(f"sem saldo: ${gasto:.4f} >= ${teto:.2f}")
    ids = [t["id"] for t in repo.tarefas(unit_id, "bloqueada")]
    for i in ids:
        repo.transicionar_tarefa(i, ("bloqueada",), "planejada", ator,
                                 f"desbloqueio com teto ${teto:.2f}")
    repo.promover_prontas(unit_id, ATOR)
    return ids


# --- quarentena do verificador ---------------------------------------------------

def _norm(texto: Any) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", str(texto).lower()).split())


def _folhas(no: Any, caminho: str, dentro: bool,
            out: list[tuple[str, str]]) -> None:
    if isinstance(no, dict):
        for k, v in no.items():
            if k == "tipo_resultado":
                continue
            _folhas(v, f"{caminho}/{k}", dentro or k in CHAVES_DE_RESPOSTA,
                    out)
    elif isinstance(no, list):
        for i, v in enumerate(no):
            _folhas(v, f"{caminho}/{i}", dentro, out)
    elif dentro and no is not None and not isinstance(no, bool):
        out.append((caminho, str(no)))


def afirmar_quarentena(entrada: dict[str, Any], saida_verificada: Any
                       ) -> None:
    """Afirmação MECÂNICA pré-chamada: a entrada do verificador só tem
    campos de identidade e a pergunta, e a pergunta não carrega nenhum
    valor ou trecho da resposta verificada."""
    extras = sorted(set(entrada) - CAMPOS_ENTRADA_VERIFICADOR)
    if extras:
        raise QuarentenaViolada(f"campos_fora_da_quarentena: {extras}")
    folhas: list[tuple[str, str]] = []
    _folhas(saida_verificada, "", False, folhas)
    pergunta = f" {_norm(entrada.get('pergunta', ''))} "
    for caminho, valor in folhas:
        n = _norm(valor)
        if len(n) >= 3 and f" {n} " in pergunta:
            raise QuarentenaViolada(
                f"pergunta_contem_resposta: {caminho} ({valor[:40]!r})")


def entrada_do_verificador(repo: Any, task: dict[str, Any]) -> dict[str, Any]:
    """A entrada que o worker pode entregar a uma tarefa de Verificador,
    depois da quarentena contra a última saída válida da tarefa verificada."""
    if task["role"] != "verificador":
        raise QuarentenaViolada(f"tarefa {task['id']} não é de Verificador")
    entrada = dict(task["input_json"] or {})
    alvo_id = entrada.get("tarefa_verificada")
    # id numérico, ou a `ref` do plano (o Coordenador não conhece ids)
    alvo = repo.tarefa(int(alvo_id)) if isinstance(alvo_id, int) else \
        repo.tarefa_por_ref(task["unit_id"], str(alvo_id or ""))
    if alvo is None or alvo["unit_id"] != task["unit_id"]:
        raise QuarentenaViolada(
            f"tarefa_verificada inválida: {alvo_id!r} (inexistente ou de "
            f"outra unit)")
    validas = [r for r in repo.runs_da_tarefa(alvo["id"])
               if r["output_valid"]]
    if not validas:
        raise QuarentenaViolada(
            f"tarefa_verificada {alvo['id']} sem saída válida")
    afirmar_quarentena(entrada, validas[-1]["output_json"])
    return json.loads(json.dumps(entrada))


# --- quarentena no arquivo de entrada (issue 04) ---------------------------------

FERRAMENTAS_DA_EXTRACAO_CEGA = frozenset({"entregar_saida",
                                          "ler_pagina_confirmada"})


def _saidas_verificadas(repo: Any, task: dict[str, Any]
                        ) -> tuple[list[Any], list[str]]:
    """O que a extração cega NÃO pode ver: o Claim verificado (valor e
    trecho) e o arquivo de saída que o produziu, com o sha256 dele."""
    from src.casefile import case_file_store
    entrada = task["input_json"] or {}
    claim = repo.claim(entrada.get("claim_id")) \
        if entrada.get("claim_id") is not None else None
    if claim is None or claim["unit_id"] != task["unit_id"]:
        raise QuarentenaViolada(
            f"claim_verificado_inexistente: {entrada.get('claim_id')!r}")
    saidas: list[Any] = [{"value": claim["value"],
                          "evidence": claim["evidence"]}]
    shas: list[str] = []
    if claim.get("output_sha256"):
        for f in repo.function_files(unit_id=task["unit_id"],
                                     sha256=claim["output_sha256"],
                                     direction="output"):
            documento = json.loads(case_file_store.read_bytes(
                task["unit_id"], f["relative"]))
            saidas.append(documento.get("output"))
            shas.append(f["sha256"])
    return saidas, shas


def _texto_da_aplicacao(payload: dict[str, Any]) -> str:
    """O texto que a aplicação escreveu nas mensagens do usuário: tarefa,
    entrada e avisos do loop. Fica de fora o que a fonte devolveu às
    ferramentas permitidas (tool_result) e o que a própria Função disse."""
    partes: list[str] = []
    for mensagem in payload.get("messages") or []:
        if mensagem.get("role") != "user":
            continue
        conteudo = mensagem.get("content")
        if isinstance(conteudo, str):
            partes.append(conteudo)
            continue
        for bloco in conteudo or []:
            if isinstance(bloco, dict) and bloco.get("type") == "text":
                partes.append(str(bloco.get("text", "")))
    return "\n".join(partes)


def afirmar_quarentena_do_arquivo(repo: Any, task: dict[str, Any],
                                  documento: dict[str, Any]) -> None:
    """Afirmação MECÂNICA pré-processo, sobre o arquivo de entrada já gravado
    (issue 04): a extração cega recebe só a ficha publicada da função, as
    ferramentas permitidas e uma entrada sem nenhum valor, trecho ou sha256
    da saída verificada. As quarentenas existentes rodam contra o mesmo
    Claim. Outras tarefas passam direto."""
    if task["role"] != "verificador" or task["output_schema"] != "extracao_cega":
        return
    from src.casefile import worker
    from src.infra.terminal import input_payload
    saidas, shas = _saidas_verificadas(repo, task)
    for saida in saidas:
        afirmar_quarentena(dict(task["input_json"] or {}), saida)
    payload = input_payload(documento["sent"])
    nomes = sorted({str(t.get("name")) for t in payload.get("tools") or []}
                   - FERRAMENTAS_DA_EXTRACAO_CEGA)
    if nomes:
        raise QuarentenaViolada(f"ferramenta_fora_da_quarentena: {nomes}")
    instrucoes = payload.get("instructions")
    if not isinstance(instrucoes, str):
        instrucoes = "\n".join(str(b.get("text", "")) for b in instrucoes or [])
    if instrucoes != worker.montar_contexto(task, blind=True)["sistema"]:
        raise QuarentenaViolada("instrucoes_fora_da_ficha_publicada")
    esquema = worker._esquema_com_refs(task["output_schema"],
                                       agentes.RAIZ_PADRAO)
    texto = f" {_norm(_texto_da_aplicacao(payload).replace(esquema, ' '))} "
    for saida in saidas:
        folhas: list[tuple[str, str]] = []
        _folhas(saida, "", False, folhas)
        for caminho, valor in folhas:
            n = _norm(valor)
            if len(n) >= 3 and f" {n} " in texto:
                raise QuarentenaViolada(
                    f"arquivo_de_entrada_contem_resposta: {caminho} "
                    f"({valor[:40]!r})")
    bruto = json.dumps(documento, ensure_ascii=False)
    for sha in shas:
        if sha in bruto:
            raise QuarentenaViolada(
                "arquivo_de_entrada_cita_a_saida_verificada")
