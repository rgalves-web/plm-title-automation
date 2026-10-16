# Validação operacional por terminal — 16/10/2026

Renato solicitou validar imediatamente uma tarefa real antes de iniciar outro tract. A rodada utilizou pendências existentes do Case File, com uma única tarefa selecionada por vez e bloqueio temporário do despacho geral. O painel permaneceu disponível. Nenhuma transmissão PREP, compra, comunicação ou liberação de pacote foi realizada.

## Resultado observado

- Claude Code leu uma fonte real em imagem, corrigiu uma afirmação cujo alcance não estava sustentado e entregou uma saída válida. O Case File conservou a afirmação anterior como substituída e vinculou a nova.
- Codex realizou extração independente sem receber a resposta primária. Uma segunda etapa da família independente leu a fonte e comparou as leituras; registrou concordância. A tarefa primária permanece aguardando decisão humana.
- Outra revisão independente já pendente também foi concluída e aplicada, sem refazer a produção anterior.
- O ciclo corrigido de produção, leitura cega e comparação levou aproximadamente 3 minutos e 27 segundos nesta amostra. Isso não é previsão de duração de outro documento ou tract.
- Treze chamadas de terminal concluídas nas seis execuções da validação têm recibos persistidos, incluindo a primeira tentativa que escalou uma limitação de ferramentas. O livro histórico permaneceu com 527 chamadas de API: nenhuma nova. Uso de assinatura não representa cobrança API nem garantia de custo total zero.
- Cada etapa foi pausada e retomada por comando identificado e versionado. A reapresentação do mesmo comando retornou o recibo anterior. Após reiniciar o serviço, quatro executores voltaram, os resultados permaneceram disponíveis e nenhuma tarefa foi repetida. As quatro units ficaram pausadas.
- A reconexão SSE recuperou o evento seguinte ao cursor informado. Artefatos de execução foram relidos e conferidos por SHA-256.

Os comprovantes e dados do cliente ficam somente em `PLM_OPERACAO/casos/2/validacao/`, fora do Git. A restauração do banco em instância isolada também foi executada após a rodada, incluindo contagens explícitas dos 13 recibos de terminal e das 92 revisões preservadas; o banco operacional não foi substituído.

Testes: 62 contratos afetados passaram antes da alteração; 83 passaram após a correção. A suíte completa final terminou com **1.362 testes aprovados**, sem skips reportados, usando diretório temporário fora do repositório. A primeira tentativa de baseline completo usou temporários dentro do repositório e parou na proteção existente de saída confidencial dos replays (263 testes aprovados antes dessa recusa); não foi tratada como suíte verde.

## Falha encontrada e correções

A primeira execução confundiu nomes históricos indisponíveis com a capacidade de leitura existente e escalou a limitação, sem exame próprio. Essa tentativa foi preservada. O caminho de leitura passou a expor também o nome declarado na ficha; o contexto lista explicitamente as ferramentas reais e explica que `entregar_saida` encaminha a persistência validada, sem depender de um segundo comando histórico `registrar_*`.

O contrato de arbitragem agora recusa manter ou corrigir uma afirmação sem recibo de leitura da página na própria execução e confere a identidade da afirmação e da revisão solicitadas. Esse controle verifica rastreabilidade; não julga o conteúdo de title. Uma impossibilidade de leitura ainda pode ser escalada com a limitação explícita.

O transporte também conserva objetos de mensagens do SDK, do CLI e dos replays como JSON estruturado entre turnos. IDs de chamadas e anexos de imagem não são convertidos em representações textuais de objetos.

## Alcance do aceite

Demonstrada a integração real entre terminais, ferramentas protegidas, gravação no Case File, revisão independente e fila humana. O ensaio permite continuar um piloto acompanhado, com identidade, escopo, fontes e conhecimento selecionados para o caso.

Não demonstra um tract completo pronto para submissão, pesquisa nominal integral, acesso validado a todos os portais, escrita de um relatório real com Q1–Q6 nem queda durante uma chamada real em andamento. Falhas de executor, interrupções e contratos de escrita continuam cobertos pelos testes isolados; não devem ser descritos como experimentos reais desta rodada. A inicialização de um novo tract exige seu cadastro e perfil próprios; não herdar conclusões nem through date de outro caso.
