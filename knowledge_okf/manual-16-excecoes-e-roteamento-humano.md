---
concept: manual 16 excecoes e roteamento humano
type: regra-cliente
sources:
- Manual Técnico v1.0 (16/08/2026) cap. 16
- ingerida em 23/08/2026 (ordem CONSERTO_DEFINITIVO, etapa A2)
links: []
unit: ''
confidence: ''
---

## Exceções — resposta esperada

- TO coverage parcial → Missing TO; limitar conclusões; perguntar ao PM.
- Lease não consta do TO → rodar chain forward/backward; NÃO declarar uncovered automaticamente.
- TO tract ≠ unit tract → manter os dois campos e o crosswalk; exigir evidência.
- Verified < represented → Potential Defect com conta e fontes.
- Fórmula alterada → bloquear e restaurar cópia do template (propriedade da caneta).
- County record contradiz TO → preservar ambos; marcar conflito; decisão do operador.
- DPU ausente → Missing Item + reconciliação final bloqueada.
- RRC indisponível → retry controlado; Missing Item se não resolver.
- Reviewer já atribuído → nunca sobrescrever; coordenar.

ESCALONAMENTO: toda pergunta ao operador carrega unidade, lease/tract/well afetado, a pergunta decisória, evidências, regra aplicável, opções e o impacto de cada opção — nunca pergunta genérica. (É o formato de `perguntar`/PERGUNTAS.md.)
