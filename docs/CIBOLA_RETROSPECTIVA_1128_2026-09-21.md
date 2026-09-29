# Retrospectiva operacional — Cibola BBT-SNN-1128

Data: 2026-09-21  
Natureza: memória operacional candidata; não é conclusão de title nem regra publicada.  
Escopo: lições reutilizáveis da execução do tract BBT-SNN-1128 / PID 16724.

## 1. Resultado da rodada

O pacote parcial foi organizado no padrão canônico da PLM, a planilha foi preenchida e validada, os documentos acessíveis foram pesquisados, o DR 50/611 foi reconstruído por captura integral e o Drive foi atualizado com 85 hyperlinks. O trabalho possível com os acessos atuais foi esgotado. A conclusão final continua condicionada às fontes externas e às decisões expressamente registradas no checkpoint.

O percentual útil deve distinguir duas métricas:

- montagem do pacote parcial;
- completude defensável do entregável final.

Percentuais sem uma matriz de blocos e evidências não devem ser usados.

## 2. Aprendizados que devem virar padrão

### Escopo e alvo

1. O exemplo canônico define a estrutura, a nomenclatura, as abas, a ordem e o nível de conteúdo do entregável.
2. Controles internos, checkpoints, planos e arquivos de fase ficam fora das seis pastas entregáveis. `Misc. Title Files` recebe apenas material do trabalho que não cabe nas demais categorias.
3. O tax card é uma semente e um checkpoint: tax card, tax map e deeds nele citados. Ele não substitui a pesquisa da cadeia desde janeiro de 1966 até a through date exigida.
4. Tracts do mesmo PID podem compartilhar a cadeia, mas continuam exigindo entregáveis separados e alocação territorial documentada. Instrumento parcial fica `tract allocation pending` quando a descrição não permite decidir.
5. O início operacional é janeiro de 1966. Documento anterior só é buscado quando necessário para provar o source of title do primeiro elo ou resolver ambiguidade.
6. Uma ausência só tem valor probatório quando a população pesquisada, o intervalo temporal, os tipos documentais, os nomes/variantes e a cobertura da fonte foram registrados.

### Pesquisa e coleta

1. A pull list e a lista de dependências externas devem nascer no primeiro dia, antes do preenchimento final da planilha.
2. CountyRecords deve ser pesquisado em lotes por: tax-card deeds, nomes e variantes, abstract, subdivision + lot, prior reference e tipos de gravame. O contador de resultados mede linhas de índice, não documentos.
3. Abrir `Document Info` pode consumir view mesmo sem baixar imagem. Registrar saldo inicial/final e tratar cada ficha inédita como custo potencial.
4. Para o CountyRecords, usar Preview e capturas integrais. Não baixar. A captura deve preservar margem direita, rodapé, todas as páginas e ordem. Captura incompleta é evidência inválida.
5. TexasFile serve para localizar/indexar; a cópia deve vir da fonte autorizada definida para o projeto.
6. A série de deeds of trust disponível no CountyRecords de Terrell começa em 06/11/1968. Gravames anteriores nessa série exigem County Clerk ou outra fonte declarada.
7. Cada documento deve ser nomeado, registrado, classificado, vinculado ao tract e comparado com a planilha imediatamente após a captura. Acumular documentos sem ledger gera retrabalho.

### Construção do entregável

1. A planilha deve ser construída durante a pesquisa, e não no fim.
2. Cada linha precisa de documento, página, citação/trecho, datas, partes, recording reference, legal description, efeito, alocação territorial, arquivo, link e pendência declarada.
3. O documento sobe primeiro; o link do Drive entra depois. A planilha é atualizada como nova versão do mesmo arquivo, preservando histórico e evitando duplicatas.
4. `PARTIAL` só sai depois da incorporação das respostas externas, QA integral e decisão da PLM sobre limitações/exceções.
5. Project Log continua somente leitura, salvo ordem explícita diferente da PLM.

## 3. O que atrasou esta rodada

1. O objetivo final e o modelo canônico não foram convertidos no início em uma checklist verificável.
2. Houve muitas microrrodadas com avanço pequeno e percentuais pouco auditáveis.
3. O checkpoint dos cinco itens do tax card foi inicialmente confundido com o escopo completo da cadeia de 60 anos.
4. Arquivos internos de fase foram colocados em `Misc. Title Files` e precisaram ser removidos.
5. Uma planilha-shell chegou a ser avaliada pelo PREP antes de conter a cadeia, gerando um falso marco de progresso.
6. Dependências de PACER, SOSDirect e outros condados foram consolidadas tarde.
7. A primeira técnica de captura cortou margens e rodapés; 18 imagens precisaram ser descartadas.
8. Downloads com custo zero foram feitos antes da reafirmação do procedimento Preview/print. Eles não entraram no pacote, mas o fluxo precisa impedir a ação desde o início.
9. O Drive link foi tratado no encerramento. O ledger deveria ter separado desde o começo `captured`, `saved locally`, `uploaded`, `linked`, `QA passed`.
10. Um mesmo agente acumulou pesquisa, interpretação, escrita e aprovação em parte da rodada. Isso reduz independência de QA.

## 4. Fluxo recomendado para o próximo tract

### Gate 0 — preflight

Antes de pesquisar:

- confirmar tract, PID, county, legal description, marco janeiro/1966 e through date;
- copiar localmente a árvore canônica vazia;
- identificar template e exemplo canônico;
- registrar sites, acessos, cobertura temporal, custo e regra de aquisição;
- criar fila externa para PACER, SOS, county/probate/court e demais jurisdições;
- abrir ledger de instrumentos, ledger de buscas negativas e matriz de cobertura;
- registrar orçamento e saldo dos portais.

### Gate 1 — seed package

- salvar tax card e tax map;
- capturar integralmente todos os deeds citados no tax card;
- lançar imediatamente esses deeds no runsheet;
- mapear owner atual, predecessor, abstracts, subdivision/lot, prior references e variantes de nomes.

### Gate 2 — cadeia e exceções

- pesquisar em lote por abstract e subdivision/lot;
- pesquisar backward/forward por partes e prior references;
- pesquisar gravames voluntários e involuntários, releases, easements/ROW, restrictions, probate/divorce/corporate authority;
- marcar gaps e emitir pedidos externos no mesmo dia;
- usar cadeia comum entre tracts do mesmo PID, preservando a alocação específica.

### Gate 3 — captura e reconciliação contínuas

Para cada documento: captura integral, QA visual, nome canônico, hash, ledger, linha da planilha, efeito e pendência. A cada lote lógico, reconciliar ledger × arquivos × planilha. Não esperar o fim.

### Gate 4 — dupla revisão de IA

1. Um modelo extrai e propõe.
2. Outro modelo, de família independente, revisa documento por documento e a continuidade da cadeia.
3. Divergência material vira questão explícita; não é resolvida por média ou por confiança numérica.
4. Conclusão final permanece com a coordenadora e, quando necessário, com decisão humana/PLM.

### Gate 5 — QA e upload

- conferir estrutura e formatação contra o canônico;
- conferir ordem cronológica, partes, datas, recording references, legal descriptions, duplicatas e alocação territorial;
- conferir um PDF por linha e uma linha por PDF aplicável;
- verificar fórmulas, merges, hyperlinks e ausência de dados de exemplo;
- confirmar que controles internos não estão no pacote;
- subir documentos, inserir links, salvar nova versão da planilha e verificar no Drive;
- manter `PARTIAL` enquanto houver dependência material.

## 5. Divisão entre modelos

### Coordenadora — Nilve Astra, esforço médio

Responsável por plano do tract, definição da próxima ação, continuidade da cadeia, resolução de conflitos, gestão de orçamento, status, critérios de parada e aceite final. Deve receber o ledger e trechos necessários, não documentos integrais sem necessidade.

### GPT mini — trabalho mecânico de baixo risco

Usar para OCR auxiliar, normalização de nomes, extração tabular preliminar, criação de índices, conferência de contagens, comparação de versões e busca de inconsistências. Toda saída que afete title precisa de revisão por modelo superior e citação ao documento.

### Claude — segunda família e contexto longo

Acionar quando houver:

- documento longo, manuscrito ou OCR difícil;
- reconciliação de cadeia com muitos instrumentos;
- descrição legal complexa ou conveyance parcial;
- trust, probate, foreclosure, divorce ou corporate authority;
- conflito entre fontes ou baixa confiança da coordenadora;
- revisão independente do pacote antes do upload/finalização.

Claude deve receber uma tarefa delimitada, o ledger atual, as páginas relevantes e um formato obrigatório de devolução. Sua saída é uma proposta auditável, não aprovação automática. O handover deve listar arquivos tocados, achados, fontes, incertezas e próximos passos.

### Regra de privacidade e custo

Enviar aos modelos somente os trechos e páginas necessários. Registrar modelo, finalidade, artefato recebido, custo e decisão tomada. O teto de API continua sendo aplicado por tract/rodada conforme autorização do operador.

## 6. Melhorias do sistema

1. Criar um perfil Cibola v2 com este fluxo, sem copiar fatos específicos do 1128 para outros tracts.
2. Tornar obrigatórios no Case File: source/access registry, instrument ledger, negative-search ledger, external-request queue e deliverable coverage matrix.
3. Mostrar progresso por blocos com evidência: setup, seed, chain, encumbrances, access, external dependencies, spreadsheet, document links e QA. Exibir separadamente `acessível concluído` e `final defensável`.
4. Adicionar estados por documento: `identified`, `previewed`, `captured complete`, `QA passed`, `filed`, `uploaded`, `linked`.
5. Adicionar gate de captura: número de páginas, margens/rodapé presentes, legibilidade e ordem.
6. Adicionar comparação automática da planilha contra o template: abas, merges, fórmulas, estilos, hyperlinks e dados de exemplo.
7. Criar fila externa já no preflight, com responsável, site, custo, pedido, status e impacto no deliverable.
8. Usar o 1128 como replay local confidencial para avaliar: omissão, precisão de extração, continuidade, falsas conclusões negativas, qualidade do handover, número de perguntas repetidas, custo e tempo.
9. Publicar aprendizados na Training Suite somente após revisão humana, com fonte, versão, escopo e exceções. Não existe aprendizagem silenciosa.
10. Registrar métricas da próxima unidade para comparar com o 1128: documentos úteis por sessão, retrabalho, capturas rejeitadas, divergências entre modelos, custo, tempo de operador e erros encontrados no QA.

## 7. Critério de sucesso na próxima unidade

A rodada terá produzido ganho real se o próximo tract:

- começar com dependências e cobertura das fontes mapeadas;
- preencher a planilha desde o primeiro lote;
- não misturar controles internos ao pacote;
- não repetir capturas por corte ou ilegibilidade;
- gerar pedidos externos antes de eles virarem bloqueio;
- mostrar percentuais calculados pela matriz de evidências;
- chegar ao upload com zero divergência entre arquivos, ledger, planilha e links;
- deixar um handover capaz de ser retomado por outro modelo sem nova pesquisa.

## 8. Status de governança

Este documento é uma retrospectiva candidata. Para virar conhecimento ativo da Training Suite, deve ser convertido em fichas com escopo, fontes, condições e exceções, revisado pelo operador e publicado pelo fluxo versionado. Fatos dominiais do 1128 permanecem no Case File do 1128 e não viram regras globais.
