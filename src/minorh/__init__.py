"""minorh — o sistema operável: quatro comandos sobre uma pasta de unidade.

    minorh unidade "<pasta>"   lê tudo, monta censo, gera PEDIDOS.md e
                               PERGUNTAS.md, para
    minorh continuar           lê só o que é novo em FILES/, atualiza, reporta
                               o delta
    minorh estado              os três números, a qualquer momento
    minorh ship                escreve o DDR das memórias, audita 100% das
                               células, monta o kit

Regra inviolável (docs/ARQUITETURA_LLM_FIRST.md): nenhuma decisão de title em
Python. Este pacote abre arquivo, renderiza página, chama modelo, salva bytes e
serializa. Quem classifica, extrai, julga, escreve célula e audita é o modelo,
pelas ferramentas da Rodada 1 (`src/examinador/`).

O que o pacote acrescenta à Rodada 1 é operabilidade, não juízo:

  - o CENSO é declarado pelo modelo e fica gravado, então "terminei" deixa de
    ser opinião — todo comando imprime exige/escrevi/branco/pendente;
  - a MEMÓRIA (fichas por entidade) é o substrato; o DDR é projeção dela;
  - o ESTADO persiste entre comandos: nada se relê, nada se perde;
  - PEDIDOS.md e PERGUNTAS.md são a fronteira com o operador;
  - o SHIP audita 100%% das células escritas com um segundo modelo, e nada
    embarca reprovado.
"""
