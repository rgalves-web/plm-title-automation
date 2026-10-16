# Operação visual PLM — arquitetura vigente

**Transporte atualizado em 16/10/2026:** a operação usa Claude Code e Codex pelos terminais oficiais, sem chaves locais de API e sem fallback ao SDK. Leia [Execução terminal](EXECUCAO_TERMINAL.md). As descrições de API abaixo conservam os contratos e os custos históricos. A inicialização do Windows passa a chamar Python diretamente, evitando depender da execução de arquivos PowerShell.

Aplicação local: **http://127.0.0.1:8788**. Entrada: `python -m src.casefile.workbench serve`.
O serviço possui quatro executores e inicia ao entrar nesta conta do Windows. Fechar a página não encerra tarefas aprovadas. Cada chamada confere novamente pausa, orçamento e custo incerto.

## Uso

1. Escolher 1107, E, E-1 ou E-2. O painel consulta o Case File, com tarefas, arquivos, decisões, requisitos da versão e conhecimento.
2. Em **Configurar**, identificar template, exemplar vigente do Lead/PM e tratamento dos dados de exemplo. A ausência impede escrita, não é substituída por outro projeto.
3. Em **Iniciar agentes**, aprovar explicitamente fontes, through date, plano de operação e teto de API. A referência de US$ 50 por tract não constitui aprovação. Produção Claude e revisão OpenAI recebem os trechos necessários.
4. Conferir decisões e dependências. Evidências de PREP, Spell Check, SME e demais requisitos precisam de arquivo real, motivo e vínculo com a versão. A aplicação não transmite ao PREP ou a terceiros.
5. Revisar candidatas verificadas e aprovar em lote. A execução em curso conserva sua publicação; novas sessões recebem a publicação aprovada posteriormente.

## Núcleo

- `operations.py` e `operations_api.py`: comandos com identidade única e versão esperada; consulta e eventos SSE com recuperação.
- `supervisor.py` e `worker.py`: quatro conexões independentes, uma instância do serviço, leases, reservas, respostas contabilizadas antes das ferramentas e conclusão transacional com aplicação do resultado.
- `runtime.py`: contratos das dez funções. Observação de pesquisa não aprova title. A leitura independente não recebe o resultado primário; outra revisão por IA julga a concordância. Python não compara valores de title.
- `source_adapters.py`: catálogo local, Drive e fontes de portal por rotinas verificadas. Uma operação por sessão de portal; pesquisa comum pode ser reutilizada dentro do mesmo PID, com aplicação territorial pendente por tract.
- `report_writer.py`: projeção em cópia do template identificado, proveniência por célula, proteção de fórmulas, dados de exemplo e invalidação de Q1–Q6 quando muda a versão.
- `learning.py` e `training_runtime.py`: candidatas, revisão independente, aprovação humana, publicação e retirada. Manifestos conservam versões da função, pacote, lições e publicação utilizada.
- `spending.py` e `accounting.py`: limite adicional compartilhado entre casos, com reserva antes de cada chamada, consumo confirmado e custo incerto separados. Novas execuções econômicas usam Sonnet para coordenação/exame, Opus para arbitragem e OpenAI para revisão; a decisão de configuração é registrada por caso.
- `knowledge_registry.py`: versões de fichas de agentes, OKF e Training Suite preservadas por hash e origem. Importar conserva histórico e não ativa conhecimento. O painel mostra o registro e as candidatas da rodada separadamente.
- `src/infra`: leitura, renderização, cache, OCR, modelos e ferramentas de captura extraídos das gerações anteriores. O núcleo vigente não importa os motores históricos.

Correções ficam limitadas a duas novas tentativas. Falta de acesso e gasto incerto mantêm a tarefa afetada suspensa. Uma chamada incerta com reserva positiva conserva o saldo retido nos dois limites; outras tarefas podem executar. Sem reserva recuperável, o caso aguarda conferência. A tarefa incerta não é repetida automaticamente, inclusive após expiração de trava durante suspensão do Windows. Confirmação da cobrança exige recibo real; reserva não é cobrança. SDKs não acumulam retentativas com a aplicação.

## Dados e recuperação

Fontes originais, Project Log e entregas existentes permanecem sem escrita. Controles e novos resultados ficam em `../PLM_OPERACAO/casos/<id>/`. Os sete controles antigos do Cibola foram transferidos para `../PLM_OPERACAO/historico/controles_cibola/`, após conferência das cópias e restauração do banco em instância isolada. `migracao/aliases.json` resolve caminhos antigos por conteúdo e identidade; não converte registros históricos em aceite.

Recuperação inicial: `../PLM_OPERACAO/recuperacao/antes_esteira_2026-10-11/` contém código, alterações locais e banco anterior. Snapshots posteriores têm manifesto e prova de restauração. `python -m src.casefile.recovery` cria e verifica nova cópia com os casos pausados. Nunca restaurar sobre o banco operacional durante trabalho ativo.

O arquivo `docs/README_HISTORICO_2026-10-11.md`, as gerações congeladas e relatórios de avaliação anteriores são históricos. `app.py` foi retirado; `src.minorh` e `src.webapp` não iniciam motores antigos. Módulos congelados preservam testes e aprendizado até a validação do piloto real autorizar seu descarte definitivo.

## Estado demonstrado e pendências

Painel e quatro casos reais incorporados, contratos operacionais testados com respostas sintéticas, recuperação real do banco e disponibilidade dos modelos conferidas. O piloto pago começou com autorização de Renato. E e E-2 produziram planos e registros de pesquisa/acervo; E produziu 11 afirmações, ainda dependentes de revisão e decisão. Uma leitura independente real da OpenAI foi persistida com custo conhecido e aguarda comparação por IA. Nenhum relatório recebeu liberação de title. A reprodução sintética valida execução e persistência; não valida conclusões de title nem substitui o piloto real.

Renato aprovou inicialmente US$ 50 por tract e depois limitou o restante da implementação a **US$ 20 adicionais no total dos quatro casos**. O painel mostra consumo, reserva e saldo desse limite, sem apagar o consumo anterior. Duas chamadas anteriores expiraram em E-1 e 1107 (requests 108 e 111); esses casos aguardam recibos reais antes de nova execução. SDKs não repetem chamadas automaticamente. Referência sem página física bloqueia a revisão antes da API; citações com várias páginas exigem leitura de todas na mesma execução.

As fontes de portal ainda precisam de sessão e rotina verificadas. O Drive exige conexão operacional do serviço. A cópia local `DEREK_EXEMPLAR.xlsx` foi preservada por identidade (artifact:2437), vinculada aos quatro casos e **confirmada expressamente por Renato como vigente para Cibola**. A conformidade de cada relatório com seus exemplos ainda exige Q1 real. PREP, Spell Check, SME e liberação final permanecem requisitos com suas evidências e autorizações próprias.

Uma lição real percorreu proposta, revisão independente, correção, aprovação explícita de Renato e aplicação por Claude numa nova execução (sessão 185, tarefa 72). As propostas 2 e 3 foram recusadas por Renato. O identificador canônico de Cibola foi corrigido sem alterar o texto autorizado; versão anterior e publicações permanecem no histórico. A publicação `b30e42224f271a8d5d61ff299694eea9444bd8fb3d6d49b2d3f05dfc1632e3f6` está selecionada nos quatro casos, com sete orientações anteriores e a nova lição. A aprovação agora recusa escopo incompatível com a seleção do caso.

Os quatro pacotes de decisão WORKING DRAFT estão em `../PLM_OPERACAO/casos/<id>/pacotes/`, com referências conferidas por hash, custos, reservas, pesquisas e pendências. São retratos locais da operação, sem liberação de relatório. Os 19 roteiros específicos da implantação foram preservados com manifesto no histórico e retirados da pasta de comandos correntes.

Consumo do novo limite no fechamento desta rodada: **US$ 11,3597 confirmados**, **US$ 1,420223 reservados para sete chamadas incertas**, **US$ 7,220077 disponíveis**. Custos anteriores permanecem separados. Duas reservas anteriores foram recuperadas do próprio registro das execuções (US$ 7,6909 e US$ 4,7267), permitindo trabalho independente sem converter desconhecido em zero.

O aceite integral ainda depende da conclusão do piloto de title: acesso operacional às fontes, matriz nominal reconciliada, revisão das pendências materiais, escrita e Q1–Q6 sobre as versões reais dos relatórios. O comportamento de escrita e QA foi verificado com dados sintéticos; não equivale a conferência real dos relatórios Cibola. Os motores históricos congelados permanecem fora da operação até comprovar a cobertura necessária para descarte definitivo.
