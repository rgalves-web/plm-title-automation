# PROMPT ÚNICO — construir o sistema operável de ponta a ponta, agora

Cole este prompt inteiro no Claude Code e deixe-o executar até o fim. Ele não depende de nenhum documento novo do operador: tudo se prova com uma unidade sintética criada pelo próprio build.

---

EXECUTE ESTA ORDEM INTEIRA NUMA ÚNICA SESSÃO, SEM DIVIDIR EM PRs. Branch `sistema-operavel` a partir de `r1-examinador-ia`. Ao final, commit único e os artefatos de prova anexados. Não pare para perguntar; toda decisão em aberto está resolvida abaixo.

## O QUE VOCÊ VAI ENTREGAR

Um comando que o operador usa numa pasta de unidade qualquer, quando os documentos dele chegarem:

    minorh unidade "<pasta da unidade>"   # lê tudo, monta censo, gera PEDIDOS.md e PERGUNTAS.md, para
    minorh continuar                      # lê só o que é novo em FILES/, atualiza, reporta o delta
    minorh estado                         # os três números, a qualquer momento
    minorh ship                           # escreve o DDR das memórias, audita 100% das células, monta o kit

REGRA INVIOLÁVEL (arquitetura LLM-first, docs/ARQUITETURA_LLM_FIRST.md): nenhuma decisão de title em Python. Python abre arquivo, renderiza página, chama modelo, salva bytes, serializa. Quem classifica, extrai, julga, escreve célula e audita é o modelo, pelas ferramentas já existentes do pacote da Rodada 1 (`corpus.py`, `cache.py`, `okf.py`, `ledger.py`, `loop.py`).

## AS 6 PEÇAS

1. **CENSO PELO MODELO.** Ao abrir a unidade, antes de qualquer célula, o Examinador (Opus 5) deriva e grava em ficha OKF o denominador da unidade: quantas leases (Exhibit "A" da DPU), quantos tratos (Exhibit "C"), quantos poços, e — do cabeçalho de cada aba do template — quais campos cada linha exige. Resultado: "esta unidade exige N campos". O censo é ficha escrita pelo modelo, NUNCA lista em Python. Todo comando termina imprimindo: `exige N · escrevi X (com citação) · branco declarado Y (motivo e dono) · pendente de documento Z`.

2. **MEMÓRIA COMO SUBSTRATO.** O modelo não escreve mais direto na célula. Trabalha em fichas OKF por entidade (lease, trato, poço, parecer, instrumento); cada campo carrega valor + citação literal (doc, página, trecho) + confiança, ou vazio com motivo e dono. O DDR é projeção das fichas, gerada no `ship`. As fichas da Rodada 1 e as 75 migradas continuam valendo.

3. **ESTADO PERSISTENTE.** `unidade` e `continuar` gravam, a cada turno: censo, fichas, lista do que já foi lido (por hash — o cache global já existe), pedidos emitidos, perguntas pendentes. `continuar` lê SÓ o que é novo em FILES/ e recalcula. Nada se relê, nada se perde entre comandos.

4. **PEDIDOS E PERGUNTAS EM ARQUIVO.** Campo do censo sem valor e sem documento → o modelo emite item em `PEDIDOS.md` (o que buscar, onde, por qual método, a qual campo responde — um item por decisão). Dúvida que só o operador resolve → `PERGUNTAS.md` (pergunta, candidatos, o que desempataria, espaço para resposta). `continuar` lê as respostas e as grava como precedente OKF, válido para as próximas unidades.

5. **SHIP COM AUDITORIA DE 100%.** `ship` aceita a qualquer momento (o operador decide que o que existe é tudo). Escreve o DDR a partir das fichas — todo campo não resolvido vira branco declarado com motivo e dono, nunca buraco silencioso. Em seguida, TODA célula não vazia é auditada, sem amostragem, por um modelo de família diferente do Examinador (usar o segundo provedor configurável; se não houver chave de outro provedor no .env, usar Sonnet 5 com contexto isolado e registrar essa limitação no relatório). O auditor vê só célula + valor + citação, reabre a página citada (cache) e responde: (a) a página sustenta o valor? (b) contradiz outra célula do arquivo? (c) é da unidade certa? Reprovada → volta ao Examinador com o motivo; reprovada 2ª vez → branco declarado ou pergunta. Nada embarca reprovado. O relatório da auditoria sai junto do DDR, célula a célula.

6. **CONTABILIDADE REAL.** O log por turno hoje registra `entrada: 2` — os tokens de entrada não estão sendo contados. Corrigir: entrada, saída, cache_escrita, cache_leitura e custo por turno e total, impressos ao final de cada comando. O operador precisa saber o custo de uma unidade antes de mandar trezentas.

TAMBÉM: corrigir `compare.py` para alinhar por identidade (lease/trato/poço/instrumento) antes de comparar campo a campo — diferença de posição de linha é layout, não erro. (Prova já feita externamente: realinhada, a Rodada 1 acertou 50 de 51 campos.)

## COMO PROVAR SEM DOCUMENTOS DO OPERADOR

Criar `tests/fixtures/unidade_sintetica/` com meia dúzia de documentos fabricados e ROTULADOS COMO SINTÉTICOS (uma DPU de 2 tratos e 5 leases com Exhibit "A", 3 leases em PDF de texto, 1 parecer curto com requirement, 1 CSV de poço). É material de teste do repo, não dado de cliente — o invariante "nunca invente arquivo" não se aplica a fixture declarada.

Roteiro de prova, executado de verdade e com a transcrição anexada:

1. `minorh unidade tests/fixtures/unidade_sintetica` → censo declarado pelo modelo (deve achar 5 leases e 2 tratos sozinho), PEDIDOS.md pede as 2 leases ausentes, PERGUNTAS.md existe.
2. Mover 1 das leases retidas para FILES/, responder 1 pergunta no arquivo → `minorh continuar` → o censo BAIXA e o delta bate com o que entrou.
3. `minorh ship` → DDR gerado das fichas, auditoria de 100% roda, relatório lista qualquer reprovação, kit montado com manifesto de lacunas.
4. Plantar 1 erro deliberado numa ficha (valor que contradiz a página) antes do ship de um segundo run → a auditoria TEM de pegá-lo. Se não pegar, a rodada não fecha.
5. `minorh estado` e `minorh perguntas` funcionam em qualquer ponto.
6. Bowen A e Maxwell A intocadas (frozen_paths); suíte inteira verde; custo real impresso.

## ACEITAÇÃO FINAL

- Os 4 comandos funcionam em pasta de unidade arbitrária, zero conhecimento da unidade em código.
- Censo derivado pelo modelo; três números em todo comando.
- Uma volta de laço demonstrada na sintética, com o censo caindo.
- Auditoria de 100% pega o erro plantado.
- Custo real com entrada e cache.
- Commit único em `sistema-operavel`, artefatos anexados: transcrição da sessão de operação, censo, DDR sintético, relatório da auditoria, custo.

Quando o operador colocar os documentos da primeira unidade real na pasta, o sistema já estará pronto: `minorh unidade` e ela começa.
