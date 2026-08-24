---
concept: manual 15 catalogo de validacoes
type: regra-cliente
sources:
- Manual Técnico v1.0 (16/08/2026) cap. 15
- ingerida em 23/08/2026 (ordem CONSERTO_DEFINITIVO, etapa A2)
links: []
unit: ''
confidence: ''
---

## VAL-001..017 — o que conferir antes de submeter (perguntas, não gates de código)

No fluxo LLM-first estas validações são PERGUNTAS que Examinador e Auditor respondem com citação — nunca `if` em Python decidindo title. As de bytes (VAL-003, VAL-013) são propriedades da caneta.

Bloqueantes: VAL-001 cada XREF lease in-scope em Ownership E Lease Review · VAL-002 todos os leases do DPU/amendments classificados (zero UNKNOWN) · VAL-003 fórmulas das células azuis idênticas ao template (hash — a caneta prova) · VAL-004 runsheet cobre certification→cutoff · VAL-005 cada linha do runsheet tem documento em Title Documents (1:1 ou justificativa) · VAL-006 cada TO usado com cópia única em Title Opinions · VAL-008 full OGL ausente no Missing Files e na Summary quando material · VAL-009 produção verificada desde completion · VAL-011 variance negativa material explicada como Potential Defect · VAL-012 outstanding exclui Advisory only · VAL-013 pasta de submissão na estrutura com Unit Name correto · VAL-015 correção under review coordenada com o reviewer.

Avisos: VAL-007 memo-only sem valor inferido · VAL-010 zero ≠ missing data · VAL-014 documento achado encerra o item sem apagar histórico · VAL-016 headers com o unit survey · VAL-017 sem hard returns, spell-check, auto-fit.

Política de submissão: zero erro bloqueante, zero decisão humana pendente, integridade de evidência e estrutura do pacote PASS; warning só permanece documentado, aceito pelo responsável e registrado.
