# SISTEMA OPERÁVEL — prova executada na unidade sintética

_Branch `sistema-operavel`, 13/08/2026. Roteiro de `docs/PROMPT_UNICO_SISTEMA_FUNCIONAL.md`,
executado de verdade, com Opus 5 como Examinador. Transcrição completa em
`tests/fixtures/unidade_sintetica/transcricao_prova.txt`._

## O que existe agora

`minorh` (wrapper `minorh.cmd` / `minorh` na raiz) com cinco comandos sobre
uma pasta de unidade arbitrária: `unidade`, `continuar`, `estado`,
`perguntas`, `ship`. Zero conhecimento de unidade em código; o pacote
`src/minorh/` só abre arquivo, chama modelo, persiste e conta. As 6 peças da
ordem:

1. **Censo pelo modelo** — `declarar_censo` grava o denominador e a ficha OKF
   com a conta inteira. Todo comando fecha com
   `exige N · escrevi X (com citação) · branco declarado Y (motivo e dono) ·
   pendente de documento Z`.
2. **Memória como substrato** — `gravar_campo`/`declarar_branco` escrevem
   fichas por entidade (`_minorh/memoria.json` + fichas OKF); o DDR é
   projeção no `ship`.
3. **Estado persistente** — `_minorh/estado.json`: censo, lidos por hash,
   pedidos, perguntas, custo. `continuar` lê SÓ o que é novo.
4. **PEDIDOS.md e PERGUNTAS.md** — emitidos pelo modelo via ferramenta;
   respostas viram precedente OKF global.
5. **Ship com auditoria de 100%** — projeção → toda célula escrita auditada
   por segunda cabeça → reprovada volta ao Examinador → reprovada 2x vira
   branco declarado. Nada embarca reprovado.
6. **Contabilidade real** — `entrada_total` = entrada + cache; custo por
   comando e acumulado por unidade impressos sempre.

Também: `compare.py` agora alinha linhas por identidade (lease/API/tract)
antes de comparar campo a campo — posição de linha é layout, não erro.

## O roteiro, com os números reais

### 1. `minorh unidade tests/fixtures/unidade_sintetica`

O Examinador **achou sozinho as 5 leases e os 2 tratos** e declarou:

> `exige 89 · escrevi 83 (com citação) · branco declarado 0 · pendente de documento 11`

A ficha do censo mostra a conta aba por aba (89 = 4 + 35 + 8 + 30 + 6 + 6).
As três iscas plantadas na fixture caíram todas:

- **PED-001** pede as duas leases ausentes (0999001-004 e -005), com Vol/Pg
  do Exhibit "A" e o método de busca;
- **PED-002 / P2** pegou a divergência deliberada da lease -003 (Exhibit "A"
  diz Pg. 3, o instrumento diz Pg. 33) e perguntou qual fonte prevalece —
  deixando branco declarado até a certidão;
- **PED-003** pede o probate de Ana Souza exigido pelo requirement do parecer.

E uma pergunta que eu não plantei (P1): a Runsheet de uma unidade cujo único
parecer é o original fica vazia por `pre_cert_date`? — avisando que a
resposta **mudaria o denominador em 30 campos** e valeria para as 300.

Custo: **$1.70** (entrada_total 685.166 · saída 41.096).

### 2–3. lease retida movida + P1 respondida → `minorh continuar`

> `delta: censo 89 → 60 · escritos 83 → 91 · pendentes 11 → 13 ·
> documentos novos processados: 1 · respostas processadas: 1`

**O censo BAIXOU** (89 → 60) porque a resposta da P1 esvaziou a Runsheet — o
delta que a ordem exige. A lease -004 rendeu +8 campos com citação. A
resposta virou ficha global com "**Não pergunte de novo — aplique**"
(`knowledge_okf/runsheet-e-cadeia-suplementar-vazia-...`). Custo: **$0.49**.

### 4. `minorh ship`

> `rodada 1: 57 auditadas, 3 reprovadas · rodada 2: 2 reauditadas, 1 segue
> reprovada · REGRA DE EMBARQUE: 1 célula rebaixada a branco declarado`

Cobertura declarada no relatório: 85 células não vazias = 55 vivas escritas
(100% auditadas, sem amostragem) + 30 de estrutura do template (cabeçalhos,
sem citação para conferir — contadas e declaradas). Kit:
`_minorh/ship/DDR.xlsx` + `AUDITORIA.json` (célula a célula) +
`MANIFESTO_LACUNAS.md`. Limitação registrada: sem chave de segundo provedor,
o auditor é Sonnet 5 em contexto isolado — mesma família, declarado no
relatório e no manifesto. Custo: **$2.18** (Examinador) + **$0.74** (auditor).

### 5. O erro plantado — pego duas vezes

Num segundo run (cópia da unidade), `Lease Review!ROYALTY` da lease -001 foi
corrompido de `1/8` para `1/6` na memória, contradizendo a página citada.

- **Ponta a ponta:** a projeção releu a página, escreveu `1/8 (one-eighth)`
  com a citação literal e rebaixou a confiança para "media" exatamente nessa
  célula — o erro plantado nunca chegou ao arquivo (rodada 1 do run com erro:
  7 reprovadas, contra 3 do run limpo). Artefatos em
  `tests/fixtures/unidade_sintetica/prova_erro_plantado/`.
- **Prova direta do auditor** (chamada real, na transcrição): valor `1/6`
  contra a página que diz `one-eighth (1/8)` →
  `"aprovada": false — "A pagina cita royalty de one-eighth (1/8), nao 1/6
  como escrito na celula."`

Nada embarca reprovado: no run limpo, a célula que as duas cabeças
disputaram até o fim (a nota da Runsheet vazia) foi **rebaixada a branco
declarado** pela regra de embarque, com o motivo na trilha.

### 6. `minorh estado` e `minorh perguntas`

Funcionam em qualquer ponto, sem chamada de modelo, e fecham com os três
números. Estado atual da sintética:

> `exige 60 · escrevi 91 (com citação) · branco declarado 1 · pendente de
> documento 13 · acumulado da unidade: $6.59`

(91 > 60 porque a memória guarda também os 30 campos da Runsheet gravados
antes do veredito da P1 — provados, não projetados. O censo é o denominador
do ENTREGÁVEL; a memória pode saber mais do que ele.)

## Aceitação, item a item

| critério | resultado |
|---|---|
| 4 comandos em pasta arbitrária, zero conhecimento em código | ✔ (+ `perguntas`) |
| censo derivado pelo modelo; três números em todo comando | ✔ — 89, com a conta na ficha |
| uma volta de laço com o censo caindo | ✔ — 89 → 60, delta bateu |
| auditoria de 100% pega o erro plantado | ✔ — projeção corrigiu; auditor, chamado direto, reprova com o motivo certo |
| custo real com entrada e cache | ✔ — `entrada_total` por turno, por comando e acumulado |
| Bowen/Maxwell intocadas; suíte verde | ✔ — 894 testes, nada tocado fora do branch |

**Custo total da unidade sintética, tudo somado: ~$9.09** (inclui o ship
refeito após um defeito de harness: o `max_tokens=400` do auditor truncava o
JSON do veredito e reprovava por "ilegível" — falhando na direção segura;
corrigido para 900 com reforço na segunda tentativa).

## O que fica aberto, dito com todas as letras

- O auditor de família diferente está implementado (ramo OpenAI por
  `OPENAI_API_KEY`) mas **não foi exercitado** — não há segunda chave neste
  ambiente. Toda auditoria desta prova é Sonnet 5, e isso está carimbado em
  cada relatório.
- A prova ponta a ponta do erro plantado mostrou defesa em profundidade (a
  projeção corrigiu antes do auditor). A prova de que o AUDITOR pega foi
  feita por chamada direta. Num run em que a projeção não releia a página, o
  auditor é a única linha — e é por isso que ele existe.
- A unidade sintética é pequena e de texto limpo. O custo real de uma
  unidade de produção (1.100+ documentos escaneados) será dominado por
  leitura de página, não pelo laço — a Rodada 1 da Josh B custou ~$3 só de
  leitura com 27 páginas abertas.
