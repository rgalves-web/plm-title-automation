---
okf_version: "0.2"
---
# agentes

Fichas das funções da firma de agentes (núcleo) e pacotes de domínio. Proposta de 27/09/2026, ver `docs/ARQUITETURA_AGENTICA_v1.md`.

## Núcleo

- [Coordenador](/nucleo/coordenador.md) — Decompõe o projeto em tarefas com dependências, aloca orçamento, decide a próxima ação e declara parada.
- [Pesquisador](/nucleo/pesquisador.md) — Executa buscas numa fonte específica e registra resultados positivos e negativos com população, intervalo e termos.
- [Arquivista](/nucleo/arquivista.md) — Captura integralmente, confere a qualidade da captura, nomeia pelo padrão do pacote, calcula hash e registra no ledger.
- [Classificador](/nucleo/classificador.md) — Diz o que cada documento é e a que unidade ou tract se vincula, sempre com trecho literal.
- [Examinador](/nucleo/examinador.md) — Lê documentos e emite claims de fato, efeito, cadeia e ônus com citação literal.
- [Verificador](/nucleo/verificador.md) — Confere às cegas cada claim material a partir apenas do documento e da página, em família de modelo independente.
- [Árbitro](/nucleo/arbitro.md) — Examina divergências entre Examinador e Verificador e resolve com citação ou escala ao operador.
- [Redator](/nucleo/redator.md) — Projeta claims aceitos no template do entregável, célula a célula, com proveniência.
- [Controlador de qualidade do pacote](/nucleo/qa_pacote.md) — Confere entregável, template, ledger, arquivos e links antes da entrega.
- [Retrospectivo](/nucleo/retrospectivo.md) — Extrai lições da rodada e as propõe como fichas OKF candidatas.

## Pacotes

- [title-texas-surface](/pacotes/title-texas-surface/index.md) — surface title no Texas (Cibola, BBT-SNN)
- [title-texas-oil-gas-dd](/pacotes/title-texas-oil-gas-dd/index.md) — due diligence de unidades de óleo e gás (Project Emirates, DDR)
