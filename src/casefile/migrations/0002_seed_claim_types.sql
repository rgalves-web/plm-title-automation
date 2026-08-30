-- 0002 — vocabulário de claims. Os ativos são os que o VS1 usa; os inativos
-- nascem para o esquema não travar o VS2/VS3 (ativá-los é UPDATE, não migração).
-- required_fields são as chaves exigidas em claims.value — contrato de FORMA,
-- nunca inspeção de valor.

INSERT INTO claim_types (claim_type, description, required_fields, active) VALUES
  ('unit_identity',     'perímetro declarado da unit (DPU achada, contrato)', '["fonte_autoridade"]', true),
  ('xref_row',          'linha do XREF atribuída à unit',                     '["lease_no","record_type"]', true),
  ('lease_in_unit',     'lease do Exhibit A da DPU',                          '["lease_no","lessor"]', true),
  ('tract',             'tract do Exhibit C',                                 '["tract_no"]', true),
  ('legal_description', 'legal description por tract/lease',                  '["texto"]', true),
  ('seller_interest',   'seller/interesse identificado',                      '["party","papel"]', true),
  ('title_opinion',     'title opinion listada (T0...)',                      '["to_id"]', true),
  ('to_coverage',       'o que cada title opinion cobre',                     '["to_id","cobre"]', true),
  ('document_present',  'documento esperado que EXISTE no acervo',            '["logical_name"]', true),
  ('document_missing',  'documento exigido pelo registro e sem arquivo',      '["esperado","exigido_por"]', true),
  ('divergence',        'divergência entre fontes (DPU x XREF x Schedule)',   '["fontes"]', true),
  ('well',              'poço da unit',                                       '["api"]', false),
  ('lease_amendment',   'amendment/memo de lease',                            '["lease_no"]', false),
  ('assignment',        'assignment na cadeia',                               '["grantor","grantee"]', false),
  ('production_status', 'status de produção',                                 '["api"]', false),
  ('fact',              'fato de exame documental',                           '[]', false),
  ('conclusion',        'conclusão de exame',                                 '[]', false);
