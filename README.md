# plm-title-automation

Local-first title automation for Purple Land Management: the **DD pipeline**
(per-unit Due Diligence Reports for Project Emirates) and the **MOR pipeline**
(Master Ownership Report / runsheet), operated through the **Minorh Title
Workbench**.

## Run

```bash
./minorh serve
```

Starts the local FastAPI workbench and opens the browser (units board →
six-stage case flow: OPEN / GATHER / DROP / RUN / REVIEW / SHIP). Copy
`config.example.yaml` to `config.yaml` and set your local paths first.

```bash
python -m pytest -q
```

The whole suite must be green before and after any change (see `CLAUDE.md`).

## Where things are

| Path | What |
|---|---|
| `CLAUDE.md` | Invariants — read first, they bind every session |
| `docs/WORKBENCH_STATUS.md` | Current state of what is built and proven |
| `docs/` | Architecture specs (flow, OKF, migration plan, workbench blueprint) |
| `src/flow/` | Case-flow spine: config, evidence ledger, unit state, runner, round-trip IO |
| `src/webapp/` | The workbench (FastAPI + front) |
| `src/dd/` | DD engine: manifest, parsers, aggregation, DDR writer, gates, packager |
| `src/` (root modules) | Shared + MOR pipeline |
| `app.py` | Frozen Streamlit fallback — do not extend, do not delete |
| `data/` | Client material and per-unit case files — **never committed** |

## Non-negotiables

Interest math is exact (`fractions.Fraction`), never LLM-computed. Every
deliverable value carries a source citation. Validation gates (structural +
source-truth) run on every write; `0 FAIL / 0 MISMATCH` or it does not ship.
Client data never leaves the machine. See `CLAUDE.md` for the full list.
