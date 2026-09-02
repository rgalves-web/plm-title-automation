-- 0003 — VS2 (coleta sob condições da aprovação de 02/09/2026).
-- Indexação local de workbooks (linhas recuperadas por chave, nunca janelas
-- em prompt), populações nomeadas com denominador preservado, busca negativa
-- auditável, e o ciclo staging -> validação -> promoção com hash e
-- procedência. Nenhuma tabela decide title.

CREATE TABLE xref_lookups (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id       bigint NOT NULL REFERENCES units,
  source_sha256 char(64) NOT NULL REFERENCES source_files (sha256),
  key_kind      text NOT NULL CHECK (key_kind IN
                  ('contract','unit_name','lease_no','recording')),
  key_value     text NOT NULL,
  rows_found    int  NOT NULL,
  at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id, source_sha256, key_kind, key_value)
);

CREATE TABLE xref_rows (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id       bigint NOT NULL REFERENCES units,
  source_sha256 char(64) NOT NULL REFERENCES source_files (sha256),
  sheet         text NOT NULL,
  row_number    int  NOT NULL,
  row           jsonb NOT NULL,
  matched_keys  text[] NOT NULL,
  at            timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id, source_sha256, sheet, row_number)
);
CREATE INDEX ON xref_rows (unit_id);

CREATE TABLE population_members (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id    bigint NOT NULL REFERENCES units,
  population text NOT NULL CHECK (population IN
               ('dpu_exhibit_a','xref_encontrada','operacional',
                'candidate_out_of_scope','documentos_ausentes_incompletos')),
  member     text NOT NULL,
  origem     text NOT NULL DEFAULT '',
  note       text NOT NULL DEFAULT '',
  at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id, population, member)
);

CREATE TABLE negative_searches (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id       bigint NOT NULL REFERENCES units,
  target        text NOT NULL,
  terms         jsonb NOT NULL,
  scope         text NOT NULL,
  names_scanned int NOT NULL DEFAULT 0,
  hits          jsonb NOT NULL DEFAULT '[]',
  result        text NOT NULL DEFAULT 'pendente_julgamento'
                CHECK (result IN ('nao_encontrado','encontrado',
                                  'pendente_julgamento')),
  evidence      text NOT NULL DEFAULT '',
  session_id    bigint REFERENCES model_sessions,
  at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE collection_items (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id          bigint NOT NULL REFERENCES units,
  research_item_id bigint REFERENCES research_items,
  title            text NOT NULL,
  method           text NOT NULL,
  target           jsonb NOT NULL DEFAULT '{}',
  status           text NOT NULL DEFAULT 'pendente'
                   CHECK (status IN ('pendente','staged','validado',
                                     'promovido','falhou',
                                     'requer_intervencao')),
  staged_path      text NOT NULL DEFAULT '',
  promoted_path    text NOT NULL DEFAULT '',
  sha256           char(64),
  provenance       jsonb NOT NULL DEFAULT '{}',
  cost_usd         numeric(10,4) NOT NULL DEFAULT 0,
  note             text NOT NULL DEFAULT '',
  at               timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON collection_items (unit_id, status);

-- As leituras dirigidas da aprovação registram fatos de leitura.
UPDATE claim_types SET active = true WHERE claim_type = 'fact';
