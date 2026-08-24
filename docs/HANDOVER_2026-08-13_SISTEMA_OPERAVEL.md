# HANDOVER 13/08/2026 — o sistema operável existe e foi provado

**Pivô consumado (ordem do Renato, 12/08):** arquitetura LLM-first — a IA faz o trabalho, Python só instrumenta (abre arquivo, chama modelo, salva bytes, conta). Os ~20 módulos determinísticos de decisão estão fora do caminho; PR-12 guardado em `git stash`. Doc: `docs/ARQUITETURA_LLM_FIRST.md` (v3, com OKF do Google como formato da base de conhecimento).

## O que existe agora (branch `sistema-operavel`, commit 67cfb72, 894 testes)

CLI que o Renato opera numa pasta de unidade qualquer, sem nada da unidade em código:

- `minorh unidade "<pasta>"` — lê o corpus, deriva o CENSO pelo próprio modelo (denominador da unidade), escreve memórias OKF por entidade (campo = valor + citação literal + confiança, ou vazio com motivo e dono), gera `PEDIDOS.md` e `PERGUNTAS.md`, para.
- `minorh continuar` — lê só o que entrou de novo em `FILES/`, processa respostas do operador (viram precedente OKF global: "não pergunte de novo — aplique"), recalcula o censo, reporta delta.
- `minorh estado` / `minorh perguntas` — os três números e as perguntas, sem custo.
- `minorh ship` — projeta o DDR das memórias, audita **100% das células escritas** (segunda cabeça, contexto isolado), reprovada volta ao Examinador, reprovada 2× vira branco declarado. Kit: DDR + AUDITORIA.json célula a célula + MANIFESTO_LACUNAS.md.

## Prova executada (unidade sintética, verificada externamente nos bytes)

- Censo 89 → resposta do operador à P1 (Runsheet suplementar vazia) derrubou para 60 — o laço fecha e o denominador reage a veredito.
- As 3 iscas da fixture caíram (leases ausentes → PED-001; conflito de registro Pg. 3 vs Pg. 33 → pergunta de precedência + branco; probate → PED-003). O modelo ainda fez uma pergunta não plantada, avisando o impacto no denominador.
- Erro plantado (1/8→1/6) pego duas vezes: pela releitura na projeção e pelo auditor em chamada direta ("A pagina cita one-eighth (1/8), nao 1/6").
- **Verificação externa:** as 2 células reprovadas ao final estão EM BRANCO no DDR (nada embarca reprovado); as 55 aprovadas estão no arquivo com o mesmo valor, 55/55; nenhuma célula de dados fora da auditoria (só 4 rótulos de template). Trilha DD_Audit_Trail com valor/citação/confiança e brancos com motivo+dono.
- Custo real agora contado (entrada+cache): sintética completa ~$6,59 + prova de erro ~$2,5.

## Pendências reais

1. **Segunda chave de provedor no `.env`** (ramo OpenAI já implementado, não exercitado) — sem ela o auditor é Sonnet 5, mesma família do Examinador; limitação carimbada em todo relatório.
2. Auditor ainda produziu 1 veredito ilegível 2× (Curative!A3) mesmo após o fix de max_tokens — falhou na direção segura (virou branco declarado), mas fica anotado.
3. A trilha guarda entradas supersedidas da mesma célula sem marcador de supersessão (ex.: 2 valores históricos de Runsheet!A2 + o branco final). Cosmético, mas um auditor humano pode estranhar.
4. Rodada 1 da Josh B (corpus real): realinhada por identidade, 50/51 campos batem com o DDR à mão — precisão alta, cobertura 6% por falta do censo (agora existe). O `62 vs 67` (contradição interna) segue como caso de teste para o auditor em corpus real.
5. Cert dates 3/3/2010 (A-669) e 9/9/2010 (A-319): pergunta antiga ao Renato, continua aberta, agora entraria via PERGUNTAS.md.

## Como usar quando os documentos chegarem

    minorh unidade "C:\...\BKV122TX - Project Emirates\<UNIDADE>"
    (buscar o que PEDIDOS.md manda, jogar em FILES/, responder PERGUNTAS.md)
    minorh continuar        # repete quantas vezes precisar
    minorh ship             # DDR + auditoria de 100% + kit + manifesto

A medida que importa sai sozinha: horas do operador por unidade e custo real por unidade.
