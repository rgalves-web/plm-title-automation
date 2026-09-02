-- 0007 — veredito CTO de 02/09/2026: rastreabilidade da verificação cega e
-- lifecycle de entregáveis.
-- Toda verificação passa a carregar a identidade COMPLETA do que foi
-- entregue ao verificador (sha do documento, página, sha do payload de
-- evidência, sha do prompt, resposta bruta, request_id, modelo/parâmetros)
-- e um status: uma verificação errada vira `invalidada` com motivo —
-- nunca é apagada, nunca vira divergência de título.
-- Entregáveis ganham lifecycle (draft/partial/final) para nenhum consumidor
-- tratar artefato incompleto como "latest final".

ALTER TABLE verifications
  ADD COLUMN status text NOT NULL DEFAULT 'valida'
    CHECK (status IN ('valida','invalidada')),
  ADD COLUMN invalidation_reason text NOT NULL DEFAULT '',
  ADD COLUMN source_sha256 char(64),
  ADD COLUMN page text NOT NULL DEFAULT '',
  ADD COLUMN evidence_payload_sha256 char(64),
  ADD COLUMN prompt_sha256 char(64),
  ADD COLUMN raw_response text NOT NULL DEFAULT '',
  ADD COLUMN request_id text NOT NULL DEFAULT '',
  ADD COLUMN model_params jsonb NOT NULL DEFAULT '{}';

ALTER TABLE deliverable_versions
  ADD COLUMN lifecycle text NOT NULL DEFAULT 'final'
    CHECK (lifecycle IN ('draft','partial','final'));

-- Os artefatos VS3 existentes nasceram ANTES do exame completar: partial.
UPDATE deliverable_versions SET lifecycle = 'partial'
 WHERE kind IN ('title_examination_vs3','claims_ready_vs3','unresolved_vs3',
                'coverage_vs3','cost_vs3','chain_graph_vs3');
