---
concept: runsheet-vazia-por-pre-cert-date-em-unidade-so-com-original-opinion
type: regra
sources:
- PERGUNTAS.md [P1] — resposta do operador (unidade_sintetica)
- 'runsheet_style (ficha global): never_enters / pre_cert_date'
- titulo - original title opinion.pdf p.1 (certification date June 1, 2011)
- 'dpu - josh sintetico unit - rec.pdf p.2 (Exhibit A: leases Vol. 100, Pgs. 1-5,
  jan-mar 2011)'
links:
- runsheet-e-cadeia-suplementar-vazia-quando-nada-e-posterior-a-cert-date
- runsheet-style
- exclusion-reasons-pre-cert-date
- category-to-ddr-runsheet
unit: ''
confidence: alta — RESOLVIDO por veredito do operador (P1)
---

## RESOLVIDO — unidade cujo unico parecer e o ORIGINAL title opinion

**A pergunta que esta ficha levantava foi respondida pelo operador (P1): a aba sai VAZIA com a nota.** Veredito completo em `runsheet-e-cadeia-suplementar-vazia-quando-nada-e-posterior-a-cert-date`. **Nao pergunte de novo** — aplique.

### A colisao
`runsheet_style` so admite instrumentos de registro **posterior** a certificacao do parecer controlador. Numa unidade cujo unico parecer e o **original**, certificado depois da formacao da unidade, **todos** os instrumentos do corpus (leases + DPU) sao `pre_cert_date` → Runsheet **vazia**, mesmo com corpus completo. Nao e falha de cobertura: e o desenho da regra.

### Procedimento (ja com o veredito)
1. Data de certificacao do parecer controlador × data de registro do instrumento mais recente. **Se nenhum for posterior, a aba esta decidida antes da primeira leitura.**
2. Grave **so a NOTA DA ABA**, citando literalmente a frase da certificacao no parecer: "nenhum instrumento de registro posterior a &lt;data&gt;".
3. Declare **branco com dono** para o bloco de linhas, motivo `pre_cert_date`, para o projetor nao emitir linhas.
4. No censo, a aba vale **0 linhas** (na unidade_sintetica: 89 → 60, contando 1 celula de nota).

### Custo aprendido
Na unidade_sintetica eu gravei os 6 instrumentos com citacao literal **antes** do veredito, como seguro. Com o veredito na mao isso e **trabalho desnecessario**: os mesmos documentos ja sao lidos para Lease Review, e as linhas de Runsheet nao serao projetadas. Nas proximas unidades, faca o passo 1 primeiro.
