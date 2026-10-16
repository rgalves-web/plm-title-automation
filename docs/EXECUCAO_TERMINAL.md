# Execução por Claude Code e Codex — 16/10/2026

Renato solicitou retirar e apagar as chaves de API do sistema, executar Claude e ChatGPT pelo terminal e publicar o código em `github.com/rgalves-web/plm-title-automation`.

O painel, PostgreSQL, ferramentas protegidas, fila única, publicações de conhecimento e revisão independente continuam no mesmo núcleo. O transporte passa a usar os executáveis oficiais Claude Code e Codex. Claude faz a produção; Codex faz a leitura e revisão independente. O chat do navegador não é automatizado.

## Preparação local

1. Instalar Python e dependências do repositório, PostgreSQL e os dois CLIs oficiais.
2. Autenticar Claude Code com a conta Claude e Codex com ChatGPT (`claude auth login`, `codex login`). O PLM não extrai nem copia tokens OAuth.
3. Criar `.env` a partir de `.env.example`, com os dados do PostgreSQL local. Não inserir chaves de modelos. `PLM_API_DISABLED=1` bloqueia a fábrica de clientes SDK.
4. Executar `python -m scripts.configure_terminal`. O comando recusa uma execução aberta, instala a migração 0013, apaga variáveis de API dos arquivos `.env*`, remove variáveis persistidas desta conta somente quando contêm a mesma chave local e configura os casos da esteira para terminal, pausados. Não apaga credenciais de outros projetos ou revoga chaves na conta do provedor.
5. Iniciar o serviço com `python scripts/run_workbench.py`. Conferir os logins no painel antes de retomar tarefas aprovadas. A inicialização automática pode ser instalada com `python -m scripts.configure_workbench_launcher --install-startup`; usa Python sem console diretamente, sem mudar a política PowerShell. Para login, executar o Claude Code oficial com `auth login`. O auxiliar PowerShell opcional só funciona onde scripts são permitidos.

## Contratos

- Cada processo recebe somente o contexto selecionado pela tarefa. Chaves de API e variáveis de autenticação manual são excluídas de seu ambiente. A sessão oficial de cada CLI continua sob controle do próprio cliente.
- Os modelos devolvem texto e solicitações de ferramentas em JSON validado. Apenas o PLM despacha as ferramentas autorizadas pela função, aplica os resultados e fecha a tarefa. Os CLIs não recebem autorização geral para editar arquivos do cliente.
- Claude inicia sem personalizações, ferramentas nativas ou MCP externos. Codex usa sandbox somente leitura, shell desativado e mapas de conectores substituídos somente no processo. Não se usam opções para ignorar sandbox ou aprovações.
- Cada processo tem limite de tempo de dez minutos; cada tarefa tem até 40 turnos. Erro, limite de acesso, saída inválida ou interrupção bloqueiam a tarefa para conferência, sem repetição automática do turno. As correções de saída seguem os contratos existentes.
- `operation_terminal_calls` conserva recibos de uso e interrupção, separado de `operation_requests`, o livro histórico das APIs. Tokens de assinatura não são convertidos em cobrança API. Estimativas monetárias retornadas pelo CLI não são tratadas como recibos de pagamento.
- Assinaturas e seus limites seguem as regras das contas. Isso não significa uso ilimitado ou garantia de custo total zero. O PLM não compra créditos nem muda opções de faturamento. As cobranças de API antigas, inclusive as incertas, permanecem intactas.
- Esta versão reinicia um processo de raciocínio por turno com contexto explícito. O Case File mantém a continuidade; não depende da memória de uma conversa de terminal. Otimização por sessões persistentes requer um contrato posterior para não misturar tracts ou revisões cegas.

## Verificação

Os dois clientes foram autenticados com suas contas. Codex devolveu `terminal_ready` numa execução real sem dados de cliente; Claude Code devolveu a solicitação JSON `confirmar_transporte` com o argumento esperado. A instrução da aplicação é fornecida ao campo oficial de sistema do Claude. Usa-se `--safe-mode`, porque `--bare` exclui o login da assinatura. Os testes verificam chamadas, contratos, recibos, remoção de chaves, ausência de reserva de dinheiro API e interrupção sem repetição automática. Nenhum desses ensaios aprova conclusões de title ou substitui Q1–Q6.

Referências oficiais: [Codex não interativo](https://developers.openai.com/codex/noninteractive), [autenticação Codex](https://developers.openai.com/codex/auth), [Claude Code programático](https://code.claude.com/docs/en/headless).

### Rodada operacional real — 16/10/2026

Após o diagnóstico de autenticação, uma pendência existente percorreu produção Claude Code, fonte em imagem, correção aplicada e revisão independente Codex com concordância. Foram preservados fonte/página, saídas, recibos e vínculo entre a afirmação substituída e a atual. O resultado continua aguardando decisão humana. A fila geral permaneceu pausada fora das etapas selecionadas; não houve nova chamada de API. [Comportamento demonstrado e limites](VALIDACAO_TERMINAL_REAL.md).
