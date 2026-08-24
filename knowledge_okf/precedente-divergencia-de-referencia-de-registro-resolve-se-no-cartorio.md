---
concept: precedente-divergencia-de-referencia-de-registro-resolve-se-no-cartorio
type: veredito
sources:
- PERGUNTAS.md [P1] — resposta do operador, 24/08/2026 (unidade _cp1_sintetica, JOSH
  SINTETICO UNIT)
- 'dpu - josh sintetico unit - rec.pdf p.2 (Exhibit "A": lease 0999001-003, "Vol.
  100, Pg. 3")'
- '0999001-003 (carla nunes) lease.pdf p.1 (recital RECORDED: "Vol. 100, Pg. 33")'
- 'caso real invocado pelo operador: Webb B — Exhibit "A" Vol 180 × Schedule 1800,
  resolvido no cartório'
links:
- exhibit-a-da-dpu-vs-recital-recorded-do-lease
- category-to-ddr-lease-review
- exclusion-reasons-confirmar-no-cartorio
- sources-county-clerk-records
- identity-keys-lease
- manual-8-4-curative
- lease-mineral-schedule-recording-multi-condado
- runsheet-e-cadeia-suplementar-vazia-quando-nada-e-posterior-a-cert-date
unit: ''
confidence: alta — veredito expresso do operador (P1, 24/08/2026), declarado válido
  para todo o projeto
---

## VEREDITO DO OPERADOR (P1) — divergência de book/page: nenhuma fonte do maço prevalece; resolve-se no registro público

**Pergunta (_cp1_sintetica):** o Exhibit "A" da DPU diz que o lease 0999001-003 está em *Vol. 100, Pg. 3*; o recital RECORDED do próprio lease diz *Vol. 100, Pg. 33*. O campo REGISTRO sai (a) branco declarado, (b) com o valor do instrumento, ou (c) com ambos e nota de divergência? Qual fonte prevalece como regra geral?

**Resposta (24/08/2026):** **(a) branco declarado + pedido de verificação no cartório.**
> "Nenhuma das duas fontes prevalece por si. Divergência de referência de registro se resolve no registro público (índice/certidão do condado). Até lá: branco declarado + pedido de verificação no cartório."

Baseado no caso real da **Webb B** (Exhibit "A" Vol 180 × Schedule 1800, resolvido no cartório). **Vale para todas as 300 unidades do projeto.**

### A regra, em uma linha
**Book/page é fato do cartório, não fato do papel.** Nem a transcrição do operador (Exhibit "A", Schedule, ownership report) nem o recital do próprio instrumento são o registro — são *afirmações sobre* o registro. Quando duas afirmações colidem, só o índice/certidão do condado desempata.

### O que NÃO fazer (as três tentações rejeitadas)
1. **Não** preferir o recital do instrumento "porque é o instrumento". O recital de registro é escrito **antes** de o instrumento ser registrado (ou preenchido depois, à mão, por quem devolveu o papel) — ele é a fonte mais suscetível a erro de carimbo, não a mais forte.
2. **Não** preferir o Exhibit "A" "porque é o documento da unidade". É transcrição, e transcrições truncam dígitos (perfil observado aqui: 33 → 3, queda de dígito em página de 2+ dígitos).
3. **Não** publicar os dois valores com nota de divergência. Duas referências numa célula de REGISTRO não é transparência: é passar ao cliente a decisão que ele contratou o title para tomar, e ainda contamina qualquer busca automática por book/page. Uma célula, um fato — ou branco.

### Procedimento padrão (substitui o passo 2 da ficha `exhibit-a-da-dpu-vs-recital-recorded-do-lease`)
1. **Cotejar** sempre: Exhibit "A"/Schedule × recital RECORDED de cada instrumento. 1 leitura por lease.
2. **Coincidiu** → REGISTRO entra com confiança **alta**, e o valor registra que houve cotejo.
3. **Divergiu** → (i) **REGISTRO branco declarado**, motivo nomeando as DUAS referências e o veredito P1; (ii) item de **Curative**: "Conciliar referência de registro — verificação no índice do condado"; (iii) **pedido** de certidão/cópia certificada ao County Clerk **pelas duas referências** (pedir só uma volta "not found" e queima um ciclo).
4. **Chegou a certidão** → o valor do cartório entra com confiança **alta**, citando a certidão; o Curative fecha; a fonte errada fica registrada como erro de transcrição (útil para calibrar a confiança do resto daquele Exhibit "A").
5. O branco é **de REGISTRO apenas**. LESSOR, LESSEE, DATE, ROYALTY, TERMO do mesmo lease continuam valendo com suas próprias citações — divergência de book/page **não** contamina a linha inteira.

### Alcance (não é só lease × DPU)
Mesma regra para qualquer par que afirme book/page: Exhibit "A" × lease, Schedule × mineral deed, runsheet de terceiro × instrumento, title opinion × assignment, ownership report × probate. O desempate é sempre o índice/certidão do condado onde a terra está.

### Efeito no censo
**Nenhum.** O campo continua no denominador como branco declarado — some do numerador, não do denominador. Divergência não cria nem apaga linha.
