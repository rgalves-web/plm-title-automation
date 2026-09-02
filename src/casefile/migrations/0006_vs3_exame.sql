-- 0006 — VS3: exame canônico sob simulação (ordem integrada de 02/09/2026).
-- Verificação CEGA (o verificador nunca vê a resposta do examinador; o
-- veredito nasce da comparação DETERMINÍSTICA entre o valor do claim e o
-- valor extraído independentemente), posições canônicas por item de
-- população (item 12 da ordem) e células candidatas de DDR no próprio claim
-- (sem escrever no workbook).

CREATE TABLE verifications (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  claim_id       bigint NOT NULL REFERENCES claims,
  question       text NOT NULL,
  verdict        text NOT NULL CHECK (verdict IN
                   ('concordancia','divergencia','evidencia_insuficiente',
                    'nao_verificavel')),
  verifier_model text NOT NULL,
  verifier_value jsonb NOT NULL DEFAULT '{}',
  comparison     jsonb NOT NULL DEFAULT '{}',
  cost_usd       numeric(10,4) NOT NULL DEFAULT 0,
  session_id     bigint REFERENCES model_sessions,
  at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON verifications (claim_id);

CREATE TABLE population_positions (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id         bigint NOT NULL REFERENCES units,
  population_item text NOT NULL,
  classification  text NOT NULL CHECK (classification IN
                    ('comprovada','comprovada_com_ressalva','divergente',
                     'nao_verificavel_na_simulacao','fora_da_area_da_unit')),
  claim_ids       bigint[] NOT NULL DEFAULT '{}',
  note            text NOT NULL DEFAULT '',
  session_id      bigint REFERENCES model_sessions,
  at              timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id, population_item)
);

ALTER TABLE claims
  ADD COLUMN ddr_candidates jsonb NOT NULL DEFAULT '[]',
  ADD COLUMN limitations text NOT NULL DEFAULT '';
