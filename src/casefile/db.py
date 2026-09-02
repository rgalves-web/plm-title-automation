"""Conexão e migrações do Case File — PostgreSQL local, SQL à vista.

psycopg3 puro, sem ORM: o esquema é artefato auditável em
`src/casefile/migrations/*.sql`, aplicado em ordem numa transação por arquivo,
com checksum sha256 conferido na reaplicação — um arquivo de migração alterado
depois de aplicado é erro nomeado, nunca reaplicação silenciosa.

SQLite é rejeitado até para testes: dialeto diferente faria o teste provar
outro esquema que não o de produção. Testes de banco rodam contra
`CASEFILE_TEST_DSN` num schema temporário e skipam com motivo quando o DSN
não responde (a decisão está no plano do VS1).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class MigracaoAlterada(AssertionError):
    """Um arquivo de migração já aplicado mudou de conteúdo."""


def dsn() -> str:
    _carregar_dotenv()
    got = os.environ.get("CASEFILE_DSN", "")
    if not got:
        raise SystemExit(
            "CASEFILE_DSN nao esta definido (.env). Ex.:\n"
            "  CASEFILE_DSN=postgresql://plm:<senha>@localhost:5432/plm_casefile")
    return got


def connect(override: str | None = None) -> Any:
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(override or dsn(), autocommit=True,
                           row_factory=dict_row)


def _carregar_dotenv() -> None:
    # O dashboard/uvicorn pode subir com cwd fora do repo: o .env do
    # próprio repositório é sempre tentado além do do diretório corrente.
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(".env"))
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    except Exception:
        pass


# --- migrações ---------------------------------------------------------------

def _arquivos() -> list[tuple[int, str, Path]]:
    out = []
    for path in sorted(MIGRATIONS_DIR.glob("[0-9]*.sql")):
        numero, _, nome = path.stem.partition("_")
        out.append((int(numero), nome, path))
    return out


def _checksum(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _statements(sql: str) -> list[str]:
    """Divide um arquivo .sql em comandos. O protocolo estendido do psycopg3
    aceita um comando por execute; o divisor respeita strings ('' escapadas)
    e comentários de linha — o SQL daqui não usa dollar-quoting nem funções."""
    out, atual, em_string, em_comentario = [], [], False, False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if em_comentario:
            if ch == "\n":
                em_comentario = False
            atual.append(ch)
        elif em_string:
            atual.append(ch)
            if ch == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":
                    atual.append("'")
                    i += 1
                else:
                    em_string = False
        elif ch == "'":
            em_string = True
            atual.append(ch)
        elif ch == "-" and sql[i:i + 2] == "--":
            em_comentario = True
            atual.append(ch)
        elif ch == ";":
            texto = "".join(atual).strip()
            if texto:
                out.append(texto)
            atual = []
        else:
            atual.append(ch)
        i += 1
    resto = "".join(atual).strip()
    if resto:
        out.append(resto)
    return out


def migrar(conn: Any) -> list[str]:
    """Aplica as migrações pendentes; devolve os nomes aplicados agora."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version int PRIMARY KEY, name text NOT NULL,"
        " checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
    aplicadas = {r["version"]: r for r in conn.execute(
        "SELECT version, name, checksum FROM schema_migrations").fetchall()}
    novas: list[str] = []
    for versao, nome, path in _arquivos():
        texto = path.read_text(encoding="utf-8")
        soma = _checksum(texto)
        feita = aplicadas.get(versao)
        if feita:
            if feita["checksum"] != soma:
                raise MigracaoAlterada(
                    f"migracao {versao:04d}_{nome} ja aplicada com checksum "
                    f"{feita['checksum'][:12]}… mas o arquivo agora tem "
                    f"{soma[:12]}… — migracao aplicada nunca muda; crie uma nova.")
            continue
        with conn.transaction():
            for st in _statements(texto):
                conn.execute(st)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, checksum) "
                "VALUES (%s, %s, %s)", (versao, nome, soma))
        novas.append(f"{versao:04d}_{nome}")
    return novas


def estado_migracoes(conn: Any) -> list[dict[str, Any]]:
    existe = conn.execute(
        "SELECT to_regclass('schema_migrations') IS NOT NULL AS ok"
    ).fetchone()["ok"]
    if not existe:
        return []
    return conn.execute(
        "SELECT version, name, checksum, applied_at FROM schema_migrations "
        "ORDER BY version").fetchall()
