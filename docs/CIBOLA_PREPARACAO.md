# Preparação do Case File para surface title

Incremento de 12/09/2026. O planejamento aceita um perfil explícito e versionado em uma decisão `project_profile` da unit. A seleção não depende de adivinhar nomes de pasta. Nenhuma unit existente é alterada pela instalação.

## Uso

O pacote local está em `C:/Users/Renato/PURPLE LAND MGMT/Land Cibola Surface Titles/00_Preparacao_2026-09-12`. Leia `LEIA_PRIMEIRO.md` e `VALIDACAO.json`. O JSON de perfil contém fontes com SHA-256 e os prompts de planejamento; o corpo fica preservado na decisão do banco ao configurar.

Validação local sem banco ou modelos:

```powershell
python -m src.casefile.project_profile "C:/Users/Renato/PURPLE LAND MGMT/Land Cibola Surface Titles/00_Preparacao_2026-09-12/perfil_cibola.json"
```

Após conhecer a atribuição e criar/identificar o Case File do tract correto, configurar explicitamente com seu ID real, revisor e motivo reais:

```powershell
python -m src.casefile.project_profile CAMINHO_DO_PERFIL --unit-id ID_REAL --reviewer NOME_REAL --reason "escopo confirmado para o tract"
```

Esses marcadores não são comandos prontos para copiar. O operador deve fornecer os valores reais. A configuração recusa unit fora da raiz do projeto, fonte alterada e decisão sem autor/motivo. Não muda lifecycle, orçamento ou estado de simulação. A execução posterior de `planejar` usa o perfil, mantém censo/triagem/claims/pedidos/proposta no Case File e continua sujeita às condições de custo e aprovação existentes.

Os arquivos de evidência do tract entram no acervo autorizado do Case File; os arquivos em `00_Preparacao_2026-09-12` são metodologia e contexto. A pasta local não é substituto do runsheet no Drive. O resolvedor de `indicar` precisa receber raiz explícita e pasta de tract apropriada; não usar seu default Emirates.

As 39 fichas são importadas no store separado `00_Preparacao_2026-09-12/knowledge_store`, por `Store.put`, com conferência de fonte/hash/trecho. Importação idêntica mantém versões. A publicação aprovada e sua ativação pela camada Training Suite dependem de decisão real; nenhum nome de revisor foi inventado. O perfil de planejamento funciona independentemente da publicação das candidatas, conservando sua própria decisão e fontes.

## Limite operacional deliberado

O incremento prepara o planejamento. A coleta/reconciliação/exame/avanço existentes assumem estruturas do pipeline de due diligence e ainda não executam surface title corretamente. Quando o perfil está selecionado, esses comandos recusam antes de efeitos externos, custo ou mudança de estado. Não se deve desligar o perfil para contornar a recusa.

Depois do acesso: inspecionar template/exemplo/Project Log, confirmar tract e cutoff, mapear os campos e responsabilidades; adaptar coleta manual e exame de surface com testes e verificação independente, e somente então liberar a próxima etapa. Não há adaptador de escrita no Google Drive entregue por este incremento. A execução completa e o aceite da entrega permanecem pendentes.

## Verificação

Baseline desta tarefa: 1.047 testes passaram. Resultado posterior e ensaio do pacote em `VALIDACAO.json`. Testes novos cobrem seleção explícita, isolamento por raiz, alteração de fonte, roteamento do planejador e recusa das etapas não adaptadas. São verificações de software; não demonstram qualidade de conclusões dominiais.

Nenhuma migração, unit operacional, publicação de conhecimento, modelo pago ou comunicação externa foi executada na preparação.

Validação concluída em 12/09: **1.054 testes passaram**, sem skips reportados; 7 novos testes de contrato. Importadas 39 fichas candidatas em store separado, com identidade/trecho, idempotência e isolamento conferidos. Sem publicação ou ativação operacional.
