"""Replay ISOLADO da etapa D sobre um snapshot de leitura de uma unit real.

    python -X utf8 -m src.casefile.replay_coordenador "JOSH B UNIT" --saida=DIR

O que faz, e só isso:
1. lê a unit do banco de PRODUÇÃO numa conexão marcada somente-leitura
   (`default_transaction_read_only`) — apenas SELECT;
2. copia as linhas da unit (ids preservados: `pesquisa:1` continua sendo a
   pesquisa 1) para um schema TEMPORÁRIO no Postgres de TESTE
   (`CASEFILE_TEST_DSN`), migrado até a 0009 — a produção não recebe a 0009;
3. no schema temporário, semeia o Coordenador e o roda pelo worker REAL com
   um cliente ROTEIRIZADO (nenhuma chamada de API; custo US$ 0,00): a 1ª
   entrega é propositalmente parcial (demonstra a recusa por cobertura), a
   2ª cobre os alvos; em seguida recusa (simulada) uma proposta e aprova
   (simulada) outra;
4. escreve relatório .md e .json numa pasta FORA do repositório (contém
   títulos de pesquisas do cliente — invariante 8) e apaga o schema.

A proposta roteirizada é montada pelo replay a partir dos alvos (uma tarefa
de Pesquisador por pesquisa aberta). Ela NÃO é saída de modelo e não prova
nada sobre a qualidade de um grafo que o Coordenador real proporia.
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.casefile import coordenacao as co
from src.casefile import custo, worker as wk

REPO_ROOT = Path(__file__).resolve().parents[2]
ATOR_SIMULADO = "human:replay-simulado"
PACOTE_PADRAO = "title-texas-oil-gas-dd"


# --- cliente roteirizado (sem API) --------------------------------------------

@dataclass
class _Uso:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _Msg:
    content: list[Any]
    usage: _Uso = field(default_factory=_Uso)
    stop_reason: str = "end_turn"


@dataclass
class _Use:
    name: str
    input: dict[str, Any]
    id: str
    type: str = "tool_use"


@dataclass
class _Texto:
    text: str
    type: str = "text"


class ClienteRoteirizado:
    """Devolve respostas pré-escritas; registra o que o worker enviou."""

    def __init__(self, roteiro: list[list[Any]]) -> None:
        self.roteiro, self.chamadas = list(roteiro), []
        self.messages = self

    def create(self, **kw: Any) -> _Msg:
        self.chamadas.append({"system": kw["system"][0]["text"],
                              "tarefa": kw["messages"][0]["content"][0]["text"],
                              "ferramentas": [t["name"] for t in kw["tools"]],
                              "ultima": _ultima(kw["messages"])})
        return _Msg(content=self.roteiro.pop(0))


def _ultima(mensagens: list[dict[str, Any]]) -> Any:
    c = mensagens[-1]["content"]
    if isinstance(c, list) and c and isinstance(c[0], dict) and \
            c[0].get("type") == "tool_result":
        return c[0]["content"]
    return None


# --- snapshot ------------------------------------------------------------------

def _json(v: Any) -> Any:
    from psycopg.types.json import Json
    return Json(v) if isinstance(v, (dict, list)) else v


def _copiar(origem: Any, destino: Any, tabela: str, where: str,
            params: tuple, *, sem: tuple[str, ...] = ()) -> int:
    rows = origem.execute(f"SELECT * FROM {tabela} WHERE {where} ORDER BY 1",
                          params).fetchall()
    for r in rows:
        cols = [c for c in r if c not in sem]
        destino.execute(
            f"INSERT INTO {tabela} ({', '.join(cols)}) OVERRIDING SYSTEM "
            f"VALUE VALUES ({', '.join(['%s'] * len(cols))})",
            [_json(r[c]) for c in cols])
    return len(rows)


def _ajustar_identidade(destino: Any, tabela: str) -> None:
    destino.execute(
        f"SELECT setval(pg_get_serial_sequence('{tabela}', 'id'), "
        f"GREATEST((SELECT coalesce(max(id), 0) FROM {tabela}), 1))")


def copiar_unit(origem: Any, destino: Any, unit_nome: str) -> dict[str, Any]:
    """Copia a unit e o que a entrada do Coordenador lê. Só SELECT na origem."""
    unit = origem.execute(
        "SELECT * FROM units WHERE upper(canonical_name) = upper(%s)",
        (unit_nome,)).fetchone()
    if unit is None:
        raise SystemExit(f"unit {unit_nome!r} não existe na origem")
    uid = unit["id"]
    n: dict[str, int] = {}
    for ct in origem.execute("SELECT * FROM claim_types").fetchall():
        destino.execute(
            "INSERT INTO claim_types (claim_type, description, "
            "required_fields, active) VALUES (%s, %s, %s, %s) ON CONFLICT "
            "(claim_type) DO UPDATE SET description = EXCLUDED.description, "
            "required_fields = EXCLUDED.required_fields, "
            "active = EXCLUDED.active",
            (ct["claim_type"], ct["description"], _json(ct["required_fields"]),
             ct["active"]))
    n["projects"] = _copiar(origem, destino, "projects", "id = %s",
                            (unit["project_id"],))
    n["units"] = _copiar(origem, destino, "units", "id = %s", (uid,))
    n["source_files"] = _copiar(
        origem, destino, "source_files",
        "id IN (SELECT source_file_id FROM file_sightings WHERE unit_id = %s "
        "OR unit_id IS NULL) OR sha256 IN (SELECT source_sha256 FROM claims "
        "WHERE unit_id = %s)", (uid, uid))
    n["file_sightings"] = _copiar(origem, destino, "file_sightings",
                                  "unit_id = %s OR unit_id IS NULL", (uid,))
    n["model_sessions"] = _copiar(origem, destino, "model_sessions",
                                  "unit_id = %s", (uid,))
    n["claims"] = _copiar(origem, destino, "claims", "unit_id = %s", (uid,),
                          sem=("superseded_by",))
    for c in origem.execute("SELECT id, superseded_by FROM claims WHERE "
                            "unit_id = %s AND superseded_by IS NOT NULL",
                            (uid,)).fetchall():
        destino.execute("UPDATE claims SET superseded_by = %s WHERE id = %s",
                        (c["superseded_by"], c["id"]))
    for tabela in ("research_items", "investigation_plans",
                   "operator_decisions", "cost_entries"):
        n[tabela] = _copiar(origem, destino, tabela, "unit_id = %s", (uid,))
    for tabela in ("projects", "units", "source_files", "file_sightings",
                   "model_sessions", "claims", "research_items",
                   "investigation_plans", "operator_decisions",
                   "cost_entries"):
        _ajustar_identidade(destino, tabela)
    return {"unit": dict(unit), "linhas_copiadas": n}


# --- roteiro ------------------------------------------------------------------------

def proposta_roteirizada(repo: Any, uid: int, alvos: list[str], *,
                         saldo: float, omitir_ultimo: bool = False
                         ) -> dict[str, Any]:
    """Uma tarefa de Pesquisador por pesquisa aberta do plano. Montagem
    MECÂNICA do replay, marcada como tal — não é um grafo de modelo."""
    pesquisas = {f"pesquisa:{r['id']}": r for r in repo.pesquisas(uid)}
    usar = alvos[:-1] if omitir_ultimo and alvos else alvos
    verba = round(min(0.20, max(saldo, 0) / (len(usar) + 1)), 2) if usar \
        else 0.0
    return {"tarefas": [{
        "ref": f"replay-pq-{a.split(':')[1]}", "role": "pesquisador",
        "title": f"[ROTEIRO DO REPLAY] {pesquisas[a]['title'][:80]}",
        "input_json": {"pesquisa": a}, "acceptance": "resultado_pesquisa",
        "depends_on": [], "budget_usd": verba, "priority": i + 1,
        "gate": "2 Coleta", "pendencias": [a],
        "justificativa": "tarefa montada pelo roteiro do replay (não é "
                         "saída de modelo)"} for i, a in enumerate(usar)]}


# --- execução -----------------------------------------------------------------------

def _conectar(dsn: str, *, somente_leitura: bool) -> Any:
    import psycopg
    from psycopg.rows import dict_row
    conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row,
                           connect_timeout=5)
    if somente_leitura:
        conn.execute("SET default_transaction_read_only = on")
    return conn


class DestinoIgualOrigem(SystemExit):
    """O DSN de destino aponta para o MESMO banco da origem."""


def identidade_do_banco(conn: Any) -> tuple[str, str, str]:
    """(banco, porta, início do postmaster): igual só no mesmo banco do
    mesmo servidor — independe de como o host foi escrito no DSN
    (localhost × 127.0.0.1 × ::1)."""
    r = conn.execute(
        "SELECT current_database() AS db, current_setting('port') AS port, "
        "pg_postmaster_start_time()::text AS inicio").fetchone()
    return (r["db"], r["port"], r["inicio"])


def exigir_bancos_distintos(origem: Any, destino: Any) -> None:
    a, b = identidade_do_banco(origem), identidade_do_banco(destino)
    if a == b:
        raise DestinoIgualOrigem(
            f"destino_igual_a_origem: o DSN de destino aponta para o mesmo "
            f"banco da origem ({a[0]}, porta {a[1]}); o replay só escreve "
            f"num banco diferente (o de teste)")


def executar_replay(origem: Any, destino_dsn: str, unit_nome: str,
                    saida: Path, *, teto: float | None = None,
                    orcamento: float = 1.5,
                    pacote: str = PACOTE_PADRAO) -> dict[str, Any]:
    """Entrada pública: recusa destino no mesmo banco da origem ANTES de
    criar qualquer schema, e saída dentro do repositório."""
    saida = Path(saida).resolve()
    if saida == REPO_ROOT or saida.is_relative_to(REPO_ROOT):
        raise SystemExit(f"saída dentro do repositório recusada ({saida}): o "
                         f"relatório contém dados do cliente (invariante 8)")
    origem.execute("SET default_transaction_read_only = on")
    destino = _conectar(destino_dsn, somente_leitura=False)
    try:
        exigir_bancos_distintos(origem, destino)
    except BaseException:
        destino.close()
        raise
    return _replay(origem, destino, unit_nome, saida, teto=teto,
                   orcamento=orcamento, pacote=pacote)


def _replay(origem: Any, destino: Any, unit_nome: str, saida: Path, *,
            teto: float | None, orcamento: float,
            pacote: str) -> dict[str, Any]:
    """Núcleo, SEM a guarda de bancos distintos (use `executar_replay`).
    Os testes o chamam direto porque o ambiente de teste tem um único banco
    disponível; o isolamento ali é o schema temporário."""
    from src.casefile.db import migrar
    from src.casefile.repo import Repo
    saida = Path(saida).resolve()
    if saida == REPO_ROOT or saida.is_relative_to(REPO_ROOT):
        raise SystemExit(f"saída dentro do repositório recusada ({saida}): o "
                         f"relatório contém dados do cliente (invariante 8)")
    teto = custo.teto_unit() if teto is None else teto
    origem.execute("SET default_transaction_read_only = on")
    schema = f"replay_d_{uuid.uuid4().hex[:8]}"
    destino.execute(f'CREATE SCHEMA "{schema}"')
    destino.execute(f'SET search_path TO "{schema}"')
    try:
        migrar(destino)
        snap = copiar_unit(origem, destino, unit_nome)
        repo = Repo(destino)
        unit = repo.obter_unit_por_nome(unit_nome)
        uid = unit["id"]
        rel: dict[str, Any] = {
            "gerado_em": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "unit": unit["canonical_name"], "schema_temporario": schema,
            "snapshot": snap["linhas_copiadas"], "teto_usd": teto,
            "gasto_da_unit_no_snapshot": repo.custo_acumulado(uid)}

        alvos = co.alvos_do_plano(repo, uid)
        rel["alvos"] = alvos
        rel["pesquisas_alvo"] = [
            {"id": f"pesquisa:{r['id']}", "status": r["status"],
             "titulo": r["title"]}
            for r in repo.pesquisas(uid)
            if f"pesquisa:{r['id']}" in alvos["alvos"] + alvos["canceladas"]]

        # 1ª rodada: parcial → recusa mecânica → completa → PROPOSTA #1
        t1 = co.semear_coordenador(repo, unit, pacote=pacote, teto=teto,
                                   orcamento_usd=orcamento,
                                   criado_por=ATOR_SIMULADO,
                                   ref="coordenador-replay-1")
        entrada = t1["input_json"]
        saldo = entrada["orcamento_usd"]["saldo_para_novas_tarefas"]
        parcial = proposta_roteirizada(repo, uid, alvos["alvos"], saldo=saldo,
                                       omitir_ultimo=True)
        completa = proposta_roteirizada(repo, uid, alvos["alvos"],
                                        saldo=saldo)
        c1 = ClienteRoteirizado([
            [_Use("ler_case_file", {"secao": "pesquisas", "limite": 5}, "l1")],
            [_Use("entregar_saida", {"saida": parcial}, "e1")],
            [_Use("entregar_saida", {"saida": completa}, "e2")],
            [_Texto("proposta entregue")]])
        r1 = wk.executar_uma(repo, uid, "replay", teto=teto, client=c1)
        rel["entrada"] = {
            "manifesto": entrada["manifesto"],
            "caracteres_sistema": len(c1.chamadas[0]["system"]),
            "caracteres_tarefa": len(c1.chamadas[0]["tarefa"]),
            "tokens_estimados": (len(c1.chamadas[0]["system"])
                                 + len(c1.chamadas[0]["tarefa"])) // 3,
            "pendencias_abertas": [p["id"] for p in
                                   entrada["pendencias_abertas"]],
            "decisoes": len(entrada["decisoes_do_operador"]),
            "orcamento_usd": entrada["orcamento_usd"],
            "ferramentas_expostas": c1.chamadas[0]["ferramentas"],
            "ferramentas_indisponiveis": r1["indisponiveis"]}
        rel["rodada_1"] = {
            "consulta_ler_case_file": json.loads(c1.chamadas[1]["ultima"])
            ["total"],
            "erro_da_entrega_parcial": json.loads(c1.chamadas[2]["ultima"]),
            "status_do_coordenador": r1["tarefa"]["status"],
            "proposta_id": r1["proposta_id"], "custo_usd": r1["custo_usd"],
            "tarefas_criadas_antes_da_decisao": [
                t["ref"] for t in repo.tarefas(uid)
                if t["role"] != "coordenador"]}
        p1 = repo.proposta(r1["proposta_id"])
        rel["proposta_1"] = {"cobertura": p1["coverage"],
                             "tarefas": [t["ref"] for t in
                                         p1["plan"]["tarefas"]]}
        co.recusar_proposta(repo, p1["id"], ator=ATOR_SIMULADO,
                            nota="recusa SIMULADA pelo replay (auditoria)")
        p1 = repo.proposta(p1["id"])
        rel["recusa_simulada"] = {
            "status": p1["status"], "decidido_por": p1["decided_by"],
            "decidido_em": str(p1["decided_at"]),
            "nota": p1["decision_note"],
            "plano_preservado": len(p1["plan"]["tarefas"]),
            "status_coordenador": repo.tarefa(p1["task_id"])["status"],
            "tarefas_criadas": [t["ref"] for t in repo.tarefas(uid)
                                if t["role"] != "coordenador"]}

        # 2ª rodada: completa → PROPOSTA #2 → aprovação simulada
        co.semear_coordenador(repo, unit, pacote=pacote, teto=teto,
                              orcamento_usd=orcamento,
                              criado_por=ATOR_SIMULADO,
                              ref="coordenador-replay-2")
        c2 = ClienteRoteirizado([
            [_Use("entregar_saida", {"saida": completa}, "e3")],
            [_Texto("proposta entregue")]])
        r2 = wk.executar_uma(repo, uid, "replay", teto=teto, client=c2)
        criadas = co.aprovar_proposta(
            repo, r2["proposta_id"], ator=ATOR_SIMULADO,
            nota="aprovação SIMULADA pelo replay", teto=teto)
        p2 = repo.proposta(r2["proposta_id"])
        rel["aprovacao_simulada"] = {
            "proposta_id": p2["id"], "status": p2["status"],
            "decidido_por": p2["decided_by"],
            "decidido_em": str(p2["decided_at"]), "nota": p2["decision_note"],
            "cobertura": p2["coverage"],
            "tarefas_criadas": {t["ref"]: t["status"] for t in criadas},
            "status_coordenador": repo.tarefa(p2["task_id"])["status"]}
        rel["historico_de_propostas"] = [
            {"id": p["id"], "status": p["status"],
             "decidido_por": p["decided_by"]} for p in repo.propostas(uid)]
        rel["custo_total_do_replay_usd"] = round(
            r1["custo_usd"] + r2["custo_usd"], 4)
        rel["chamadas_de_api"] = 0
    finally:
        destino.execute("SET search_path TO public")
        destino.execute(f'DROP SCHEMA "{schema}" CASCADE')
        destino.close()
    rel["schema_removido"] = True
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "replay_etapa_d.json").write_text(
        json.dumps(rel, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    (saida / "replay_etapa_d.md").write_text(relatorio_md(rel),
                                             encoding="utf-8")
    return rel


PROVA = """## O que este replay prova

- A entrada do Coordenador é montada do Case File real (snapshot) com o manifesto declarado, e as ferramentas expostas são as da ficha que o código implementa.
- Os alvos saem mecanicamente do plano aprovado: pesquisas abertas da sessão do plano; canceladas ficam fora e não podem ser citadas.
- Uma proposta que não cobre todos os alvos é recusada na entrega, com erro nomeado devolvido ao modelo no mesmo run.
- Uma saída válida vira PROPOSTA: nenhuma tarefa é criada nem fica executável antes da decisão humana.
- A recusa preserva a proposta, com autor, data e nota. A aprovação cria as tarefas numa transação e registra autor, data, nota e ids.
- Nada disso chamou API (custo US$ 0,00) nem escreveu no banco de produção (conexão de origem somente leitura; schema temporário apagado).

## O que só um modelo real pode demonstrar

- Se o Coordenador real produz um grafo SENSATO: tarefas bem cortadas, funções certas, dependências e orçamentos razoáveis. A proposta aqui é um roteiro mecânico (uma tarefa de Pesquisador por pesquisa), não um plano.
- Se o vínculo tarefa → pesquisa que ele declarar é substantivo. O código só confere IDs e estados; o mérito é do operador.
- O custo real em tokens (cache, tamanho da resposta) e se o teto da tarefa basta.
- Se ele usa bem a consulta `ler_case_file` e respeita o saldo sem precisar da recusa mecânica.
"""


def relatorio_md(rel: dict[str, Any]) -> str:
    e, a = rel["entrada"], rel["alvos"]
    linhas = [
        f"# Replay isolado da etapa D — {rel['unit']}",
        "",
        f"Gerado em {rel['gerado_em']}. Schema temporário `"
        f"{rel['schema_temporario']}` no Postgres de teste, removido ao fim. "
        f"Chamadas de API: **{rel['chamadas_de_api']}**; custo "
        f"**US$ {rel['custo_total_do_replay_usd']:.2f}**.",
        "",
        "## Snapshot (somente leitura da produção)",
        "",
        "| tabela | linhas |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in rel["snapshot"].items()],
        "",
        f"Gasto da unit no snapshot: US$ {rel['gasto_da_unit_no_snapshot']}"
        f" de US$ {rel['teto_usd']}.",
        "",
        "## Entrada do Coordenador",
        "",
        f"- sistema {e['caracteres_sistema']} + tarefa "
        f"{e['caracteres_tarefa']} caracteres (≈ {e['tokens_estimados']} "
        f"tokens, estimativa por caracteres/3)",
        f"- pendências abertas integrais: {len(e['pendencias_abertas'])} "
        f"({', '.join(e['pendencias_abertas'])})",
        f"- decisões do operador: {e['decisoes']}; truncadas: "
        f"{e['manifesto']['truncado']['decisoes_truncadas'] or 'nenhuma'}",
        f"- orçamento: {json.dumps(e['orcamento_usd'])}",
        f"- ferramentas expostas: {', '.join(e['ferramentas_expostas'])}; "
        f"indisponíveis: {', '.join(e['ferramentas_indisponiveis'])}",
        "",
        "Manifesto (o que é integral, contagem, truncado, consulta, "
        "quarentena):",
        "", "```json",
        json.dumps(e["manifesto"], ensure_ascii=False, indent=1), "```",
        "",
        f"## Alvos — plano v{a['plano_versao']} ({a['plano_status']})",
        "",
        f"**{len(a['alvos'])} pesquisas abertas** a cobrir; canceladas fora "
        f"do alvo: {', '.join(a['canceladas']) or 'nenhuma'}.",
        "",
        "| pesquisa | status | título |", "|---|---|---|",
        *[f"| {p['id']} | {p['status']} | {p['titulo']} |"
          for p in rel["pesquisas_alvo"]],
        "",
        "## Rodada 1 — proposta parcial recusada, completa aceita como "
        "proposta",
        "",
        f"- consulta `ler_case_file(pesquisas)`: total "
        f"{rel['rodada_1']['consulta_ler_case_file']}",
        f"- erro devolvido à entrega parcial: "
        f"`{rel['rodada_1']['erro_da_entrega_parcial']['erros']}`",
        f"- Coordenador: {rel['rodada_1']['status_do_coordenador']}; "
        f"proposta #{rel['rodada_1']['proposta_id']}; tarefas criadas antes "
        f"da decisão: {rel['rodada_1']['tarefas_criadas_antes_da_decisao'] or 'nenhuma'}",
        f"- cobertura da proposta #1: "
        f"{len(rel['proposta_1']['cobertura']['cobertos'])}/"
        f"{rel['proposta_1']['cobertura']['alvos']} "
        f"(completa: {rel['proposta_1']['cobertura']['completa']})",
        "",
        "## Recusa simulada",
        "",
        *[f"- {k}: {v}" for k, v in rel["recusa_simulada"].items()],
        "",
        "## Aprovação simulada (proposta #"
        f"{rel['aprovacao_simulada']['proposta_id']})",
        "",
        *[f"- {k}: {v}" for k, v in rel["aprovacao_simulada"].items()
          if k not in ("cobertura", "tarefas_criadas")],
        "",
        "| pesquisa | tarefas que a citam |", "|---|---|",
        *[f"| {k} | {', '.join(v)} |" for k, v in
          rel["aprovacao_simulada"]["cobertura"]["cobertos"].items()],
        "",
        "Tarefas criadas (só no schema temporário, nenhuma executada): "
        + ", ".join(f"{k} ({v})" for k, v in
                    rel["aprovacao_simulada"]["tarefas_criadas"].items()),
        "",
        f"Histórico de propostas: {rel['historico_de_propostas']}",
        "",
        PROVA,
    ]
    return "\n".join(linhas)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("unit")
    p.add_argument("--saida", required=True, type=Path)
    p.add_argument("--orcamento", type=float, default=1.5)
    args = p.parse_args()
    from src.casefile.db import dsn, _carregar_dotenv
    _carregar_dotenv()
    destino = os.environ.get("CASEFILE_TEST_DSN", "")
    if not destino:
        raise SystemExit("CASEFILE_TEST_DSN ausente: o replay só escreve no "
                         "Postgres de teste")
    origem = _conectar(dsn(), somente_leitura=True)
    try:
        rel = executar_replay(origem, destino, args.unit, args.saida,
                              orcamento=args.orcamento)
    finally:
        origem.close()
    print(json.dumps({"alvos": len(rel["alvos"]["alvos"]),
                      "cobertura_final":
                          rel["aprovacao_simulada"]["cobertura"]["completa"],
                      "chamadas_de_api": rel["chamadas_de_api"],
                      "custo_usd": rel["custo_total_do_replay_usd"],
                      "saida": str(args.saida)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
