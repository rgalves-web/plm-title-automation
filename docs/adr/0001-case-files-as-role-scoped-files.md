# Case Files live as role-scoped files; the database is a rebuildable index

Each Function receives one input file and writes one output file under the Case's folder (`PLM_OPERACAO/casos/<case-id>/_casefile/<stage>/<function>/<task>/`), and those files are the source of truth for the Case File. PostgreSQL becomes an index that can be rebuilt from them. We chose this so every step can be audited by opening a folder, and so each Function sees only its own input, which isolates context by construction (suggested by Guilherme Gomes de Lucas, accepted by Renato on 2026-10-16).

## Considered Options

- **Files only, no database**: rejected; the dashboard, queue and cross-Case queries need an index.
- **Database as source of truth, files only as hand-off packets** (the prior shape): rejected; state that only lives in rows cannot be audited by reading a folder, and a shared runtime mixes Function contexts.

## Consequences

- Case folders hold client data, so they stay outside the repository under invariant 8.
- Migrating the existing `src/casefile` tables to this shape is a separate, staged piece of work; until then the database remains authoritative for Cases already in flight.
