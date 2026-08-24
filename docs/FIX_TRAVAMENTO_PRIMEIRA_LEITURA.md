# CORREÇÃO URGENTE — minorh travou em silêncio na primeira leitura da WEBB B UNIT

Reprodução real: `minorh unidade "C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates\WEBB B UNIT"`
→ 14+ minutos sem imprimir NADA e sem gravar NADA (só `_minorh/fichas/` vazia).
A pasta tem 2 XREFs de ~11 MB, Project Log de 773 KB, zip de 22 MB, PDF de 1 MB, 1 TIF.
Suspeito: indexação do corpus lendo planilha gigante inteira (ou o zip) sem limite, antes
do primeiro save e da primeira impressão.

## Ordens (branch `sistema-operavel`, direto)

1. **Sinal de vida obrigatório.** O console NUNCA fica mudo mais de ~10s. Imprimir, no
   mínimo: partida com contagem de arquivos, uma linha por arquivo indexado
   (`lendo 3/9: Lease to Well XREF ... 11 MB`), uma linha por turno do modelo
   (`turno 4 · 2 leituras · $0.12`). O operador vê a máquina trabalhar.

2. **Gravação imediata.** `estado.json` nasce na PARTIDA (antes de qualquer leitura),
   e se atualiza a cada arquivo indexado e a cada turno — não só no fim. Queda ou
   Ctrl+C em qualquer ponto nunca perde mais que o passo corrente.

3. **Arquivo grande não trava a rodada.** Indexação com orçamento por arquivo
   (ex.: 60s). Planilha >2 MB: indexar por nomes de abas + cabeçalhos + amostra de
   linhas, nunca o texto integral — o conteúdo integral é lido depois, sob demanda,
   quando o Examinador pedir a página/aba específica. Zip: listar o conteúdo sem
   extrair. Estourou o orçamento: o arquivo entra como
   `indexacao_parcial — motivo` (pendência declarada, o Examinador decide se pede
   leitura profunda), NUNCA silêncio, NUNCA crash.

4. **Ctrl+C limpo.** Capturar e imprimir "interrompido — estado salvo; retome com
   minorh continuar".

5. **Prova real, não sintética:** rodar `minorh unidade` na própria WEBB B UNIT.
   Aceitação: progresso visível desde o primeiro segundo; primeira rodada completa
   imprimindo os três números; `PEDIDOS.md` e `PERGUNTAS.md` gravados na pasta;
   custo impresso. Anexar a transcrição do console.

Depois da prova, o Renato repete o MESMO comando que já usou — ou apenas
`minorh continuar` na unidade.
