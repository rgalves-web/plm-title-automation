-- 0005 — política simulation_mode (ordem do operador de 02/09/2026):
-- a execução da JOSH B UNIT é SIMULAÇÃO/GOLDEN REPLAY. Estado novo
-- COLETA_SIMULADA_CONCLUIDA (a coleta da simulação termina sem compra) e
-- status bloqueado_simulacao para itens de coleta paga
-- (required_in_production_but_unavailable_in_simulation).

ALTER TABLE units DROP CONSTRAINT units_state_check;
ALTER TABLE units ADD CONSTRAINT units_state_check CHECK (state IN
  ('INDICADA','PLANEJANDO','COLETANDO','COLETA_SIMULADA_CONCLUIDA',
   'EXAMINANDO','VERIFICANDO','PREENCHENDO','AUDITANDO',
   'AGUARDANDO_RENATO','LIBERADA','BLOQUEADA'));

ALTER TABLE collection_items DROP CONSTRAINT collection_items_status_check;
ALTER TABLE collection_items ADD CONSTRAINT collection_items_status_check
  CHECK (status IN ('pendente','staged','validado','promovido','falhou',
                    'requer_intervencao','cancelado','bloqueado_simulacao'));
