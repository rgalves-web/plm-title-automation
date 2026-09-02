-- 0004 — determinações do operador de 02/09/2026 (rodada 2 do VS2).
-- (5) população nova `in_dpu_but_zero_unit_acres`: presença no Exhibit A
--     preservada, zero acres na unit — nunca alteração silenciosa do
--     denominador. Classificação só após a leitura da /006.
-- (4) status `cancelado` para itens de coleta substituídos pela pull list
--     reconciliada — nada some, tudo fica com nota.

ALTER TABLE population_members
  DROP CONSTRAINT population_members_population_check;
ALTER TABLE population_members
  ADD CONSTRAINT population_members_population_check CHECK (population IN
    ('dpu_exhibit_a','xref_encontrada','operacional',
     'candidate_out_of_scope','documentos_ausentes_incompletos',
     'in_dpu_but_zero_unit_acres'));

ALTER TABLE collection_items
  DROP CONSTRAINT collection_items_status_check;
ALTER TABLE collection_items
  ADD CONSTRAINT collection_items_status_check CHECK (status IN
    ('pendente','staged','validado','promovido','falhou',
     'requer_intervencao','cancelado'));
