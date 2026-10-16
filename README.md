# PLM — esteira visual de agentes

Abra **http://127.0.0.1:8788**. O painel opera o Case File em PostgreSQL e conserva a trilha de tarefas, arquivos, revisões, custos e conhecimento.

Execução vigente: **Claude Code na produção e Codex na revisão, pelo terminal**, autenticados nas contas das assinaturas. As chaves locais de API foram removidas; a operação não volta automaticamente ao SDK. Veja [configuração e limites](docs/EXECUCAO_TERMINAL.md). Os registros de cobrança anteriores continuam preservados.

```powershell
python -m src.casefile.workbench serve
```

O serviço inicia automaticamente ao entrar no Windows. Fechar a página mantém trabalhos aprovados em execução. O piloto contém 1107/PID 16142 e E/E-1/E-2/PID 16237. Renato autorizou o piloto local e depois limitou o restante da implementação a **US$ 20 adicionais no total das APIs dos quatro casos**, com reserva por chamada. O painel separa custos conhecidos e incertos; os casos afetados aguardam recibos reais. O exemplar de Derek foi confirmado para Cibola.

A arquitetura vigente, o uso, a recuperação e as pendências estão em [Operação visual](docs/OPERACAO_VISUAL.md). Leia também [CLAUDE.md](CLAUDE.md), [AGENTS.md](AGENTS.md) e a [arquitetura governante](docs/ARQUITETURA_GOVERNANTE.md). Requisitos de Cibola permanecem no protocolo obrigatório do projeto.

Controles internos ficam em `../PLM_OPERACAO/casos/<id>/`; controles anteriores ficam no histórico recuperável. O Project Log, as fontes originais e os pacotes entregues permanecem sem escrita.

O README anterior está em [histórico](docs/README_HISTORICO_2026-10-11.md). A interface Streamlit foi retirada e os comandos de inicialização dos motores anteriores foram desativados. Os módulos congelados preservam regressões e aprendizado até concluir a validação do piloto real.
