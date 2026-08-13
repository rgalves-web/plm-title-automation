# MANIFESTO DE LACUNAS — unidade_sintetica

O que este DDR declaradamente NAO contem, e por que. Um kit sem
manifesto esconde os buracos; este os numera.

- campos escritos e auditados: 55
- brancos declarados na memoria: 1
- pendentes de documento: 13
- perguntas abertas ao operador: 1
- pedidos abertos: 4

## Brancos e pendentes, campo a campo

- curative 1 (Requirement No. 1 — probate Ana Souza) :: Curative!STATUS (baixa do requirement) — PENDENTE do pedido PED-003
- curative 2 (conflito de registro — lease 0999001-003) :: Curative!REQUIREMENT (baixa) — PENDENTE do pedido PED-002
- lease 0999001-001 :: Lease Review!observacao de titulo (sujeito a claims dos herdeiros) — PENDENTE do pedido PED-003
- lease 0999001-003 :: Lease Review!REGISTRO — PENDENTE do pedido PED-002
- lease 0999001-004 :: Lease Review!REGISTRO (confirmacao) — PENDENTE do pedido PED-001
- lease 0999001-004 :: Lease Review!ROYALTY — PENDENTE do pedido PED-001
- lease 0999001-004 :: Lease Review!TERMO — PENDENTE do pedido PED-001
- lease 0999001-005 :: Lease Review!REGISTRO (confirmacao) — PENDENTE do pedido PED-001
- lease 0999001-005 :: Lease Review!ROYALTY — PENDENTE do pedido PED-001
- lease 0999001-005 :: Lease Review!TERMO — PENDENTE do pedido PED-001
- lease 0999001-005 :: ROYALTY — PENDENTE do pedido PED-004
- lease 0999001-005 :: TERMO — PENDENTE do pedido PED-004
- runsheet (aba) :: LINHAS DE INSTRUMENTO (NO., INSTRUMENTO, REGISTRO, DATA, PARTES) — BRANCO: Veredito do operador em P1: a Runsheet e cadeia SUPLEMENTAR — so entram instrumentos de registro POSTERIOR a data de certificacao do parecer controlador (June 1, 2011, titulo - original title opinion.pdf p.1). Os 6 instrumentos do corpus (5 leases, Vol. 100, Pgs. 1-5; DPU, Vol. 200, Pg. 50) sao todos de registro anterior — exclusao `pre_cert_date`. Aba sai VAZIA com a NOTA DA ABA gravada. Os 6 instrumentos permanecem na memoria com citacao literal e continuam sustentando Lease Review / Ownership / Unit and Pooling; a exclusao e so da Runsheet. (dono: Examinador (decidido) — veredito do operador P1, aplicado)
- runsheet item 3 (lease 0999001-003) :: Runsheet!REGISTRO — PENDENTE do pedido PED-002

## Limitacao da auditoria

LIMITACAO REGISTRADA: nenhuma chave de segundo provedor no .env — auditoria feita por claude-sonnet-5 (mesma familia do Examinador), em contexto isolado. Cabecas da mesma familia podem errar juntas.