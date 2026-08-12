# ORDEM DE TRABALHO — PR-12 · A linha que nunca foi emitida
_Emitida 2026-08-12 pela sessão Cowork, após verificação externa do artefato PR-11 (md5 `3841291cb489edd1af684b7164516ff3`)._

**Branch:** `pr12-row-completeness` a partir de `pr11-crosstab-consistency`.

## Ratificado nos bytes — os três defeitos do PR-11 estão fechados

- **Registro corrigido e consistente:** Runsheet C5 `Vol. 567, Pg. 170` e C6 `Vol. 571, Pg. 343`, batendo com a Lease Review e com o documento à mão. Testei a consistência por conta própria, comparando as 60 leases entre Lease Review e Ownership - Worksheet: **0 inconsistências de registro**. O gate novo funciona.
- **Captura:** 0 citações de captura de tela no artefato inteiro.
- **Recap:** A5 = 220,00 com citação da DPU; B5:E5 brancas com `nao_computavel` e dono. Adivinhar ali seria o pior lugar possível — a decisão está certa.
- **Denominadores:** 1.178 escritas-com-trilha + 144 estrutura = **1.322**, exatamente as células não vazias do arquivo. As 144 fora da trilha são todas estrutura de verdade. A conta fecha.

## O defeito desta rodada: o gate mede o que foi escrito; o erro agora é o que não foi

Os dois gates novos comparam **células que existem** e cobrem **regiões declaradas**. Uma linha que nunca foi emitida não tem célula para comparar nem cai em região nenhuma. É a mesma lição outra vez, virada do avesso.

### 1. BLOQUEANTE — o Runsheet omite instrumentos que o próprio artefato declara de registro e pós-piso, sem motivo embarcado

Sete leases cuja linha da Lease Review afirma registro em volume 561–610 (posterior ao piso provisório de abril/2010) **não aparecem no Runsheet**:

| lease | registro declarado na Lease Review |
|---|---|
| 0220604-022 | Vol. 561, Pg. 757 |
| 0220604-023 | Vol. 562, Pg. 895 |
| 0220604-025 | Vol. 567, Pg. 216 |
| **0220604-026** | **Vol. 569, Pg. 324** |
| 0220750-018 | Vol. 572, Pg. 118 |
| **0222981-056** | **Vol. 581, Pg. 14** (Choctaw) |
| 0220750-008 | Vol. 610, Pg. 245 |

`0220604-026` é a prova mais dura: o runsheet à mão a traz como entrada **14** (`Vol. 569, Pg. 324, Instr. 115447`), entre as duas que o sistema **incluiu** — 567.170 (entrada 12) e 571.343 (entrada 15). Mesma família, mesmo intervalo, volumes adjacentes: duas entram, a do meio some. Não é filtro de escopo; é seleção com buraco.

O caso Choctaw tem causa conhecida e conclusão errada. O gate de citação recusou a captura de tela — **correto**. A rodada então **apagou a linha inteira**, e recusar a fonte virou negar o fato: a Lease Review C61/F61 e a Ownership - Worksheet E67/K67 continuam afirmando que o instrumento existe e está registrado em Vol. 581, Pg. 14. Fonte inadmissível gera **item de leitura** (`extract` — o instrumento está nos zips Choctaw de `FILES/`), nunca ausência silenciosa. Invariante 21, na forma que ainda não tinha sido escrita: recusar a evidência não é provar a ausência.

**Ordem:** gate de completude por linha. Toda entidade que o artefato declara em qualquer aba (lease de registro, instrumento, poço) é (a) linha emitida na aba que a espera, ou (b) exclusão registrada com motivo do vocabulário fechado **e** dono. Aceitação: sobre o artefato PR-11, o gate reporta as 7 acima; sobre o novo, 0 sem conta.

### 2. A conta de exclusões tem de embarcar no artefato

O PR-7 já contava 210 excluídos com motivo, mas isso vive no arquivo lateral da aba. O invariante 21 diz que a evidência embarca **no** artefato: um DDR cujas razões vivem num case file não é auditável sozinho, e é o DDR que vai ao cliente. O Runsheet declara a base provisória em A3 — declare do lado, na mesma disciplina, quantos instrumentos foram examinados, quantos entraram e o total excluído por motivo.

### 3. Depois disso, e só depois, a cobertura real do Runsheet

Com o gate de completude verde, o alvo é honesto: **3 entradas contra 23**. Não perseguir o número — perseguir a conta fechada: cada um dos 23 do documento à mão ou é linha emitida, ou é exclusão com motivo, ou é instrumento fora do corpus com item de brief. Um Runsheet que sobe pelo motivo errado é pior que um curto.

## Também neste PR

4. **`0220604-010`** — o diagnóstico está certo e é o melhor achado da rodada: `1/10 × 1/8 + (1/8 × 1/5 × 1/2)` = 0,0125 + 0,0125, dois componentes de origens distintas, e a mão atribui só um à lease. Fica em veredito. Registrar a lição com fixture: **soma de componentes do mesmo dono não é o interesse da lease** — é o mesmo padrão dos direitos executivos, terceira aparição.

5. **Regra permanente para o vocabulário de motivos:** todo motivo novo (`captura_de_tela` entrou nesta rodada) nasce com a pergunta "isto gera item de trabalho para quem?". Motivo sem dono é buraco com nome bonito.

## Aceitação

Completude por linha CLEAN; exclusões contadas dentro do artefato; os quatro gates do PR-11 seguem CLEAN; Bowen/Maxwell 0 FAIL / 0 MISMATCH em leitura; suíte verde. **Artefato + relatório + write_manifest anexados.**

## Travado no operador, sem mudança

Cert dates **3/3/2010 (A-669)** e **9/9/2010 (A-319)**: origem? Candidatos do sistema 9/4/2010 e 21/5/2010 não batem. É o piso do Runsheet e o que destrava Title Documents (1/19).
