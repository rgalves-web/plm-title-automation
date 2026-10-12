# Training Suite no Case File

## Atualização local Cibola — 01/10/2026

**Seleção corrente 1.2:** publicação `ecf0bcfa759c42efea0c5304b505511d1fd7e140d76df8591ee2afb14e22ba99`, decisões **89/90/91**, units **2/3/4**. Q2 explicita pesquisa grantor/grantee de todas as partes da cadeia, variantes/períodos/fontes, resultados completos e reconciliação, sem substituir busca nominal por remissões. Sete fichas com fontes versionadas, seleção e estado conferidos. Trilha: `../Land Cibola Surface Titles/00_Governanca/atualizacao_v1.2_2026-10-01/`. A implantação 1.1 abaixo é histórica. Nenhum código de runtime ou estado da unit foi alterado; três achados de cobertura nominal por unit foram registrados separadamente como pesquisas abertas.

**Atualização vigente 1.1:** comunicado completo de Marc Reyes incorporado por continuidade da instrução de Renato para persistir o protocolo. Publicação `391d4b7845918365fb7ed948fcf2cea27016c4b45e844824a0c49865c9ba11b5`, decisões **86/87/88** para units **2/3/4**, sete fichas com fonte versionada e seleção conferida no banco. Exemplar Lead/PM por tipo, detalhes visuais explícitos, Spell Check de notas, consulta antecipada a SMEs e PREP localizado (ainda sem execução nos relatórios). Evidências em `../Land Cibola Surface Titles/00_Governanca/atualizacao_v1.1_2026-10-01/`. O parágrafo seguinte registra a implantação 1.0 anterior; sua publicação não é mais a seleção corrente dessas três units. Nenhum código do runtime foi alterado por esta atualização.

Por instrução explícita de Renato, foi publicada e selecionada nas units 2, 3 e 4 uma publicação específica do protocolo de submissão Cibola, com uma instrução e seis critérios. A fonte normativa e a trilha estão em `../Land Cibola Surface Titles/00_Governanca/README.md` (caminho relativo à raiz do repositório). A publicação é `24531b2ed0612f7b4786c00ead0d6ee0b5bde6e9c51bbf5f879151f642087a36`; decisões 83, 84 e 85. Não altera o estado das units, não aprova title e não aceita em lote as 61 candidatas anteriores. A seleção vale para próximas sessões integradas; não comprova consumo nem revisão já executada. Uploads de trabalho em andamento estão autorizados por Renato; nenhuma submissão parcial/final pode contrariar o protocolo. Project Log continua somente leitura.

O restante deste documento descreve a implementação e o inventário de 11/09/2026. Menções abaixo a ausência de aprovação referem-se àquele inventário histórico, não à publicação específica acima.

Implementação de 11/09/2026 na branch `training-suite-integration`, a partir de
`6374eb9c06c3340502471a24a408933e2ab083ab`. A branch `casefile-vs1` conserva o
ponto anterior. A integração oferece importação local, versões imutáveis,
consulta por assunto/escopo, publicação revisada, trilha no PostgreSQL e
revisão por critérios. Não constitui aceite de VS3 nem autorização de VS4.

## Estado da entrega

| Categoria | Resultado |
|---|---|
| Implementado | Inventário, fragmentos consultáveis, fichas versionadas, publicação/retirada, escopo por unit, consultas/aplicações/revisões no DAO, API e dashboard |
| Testado com simulação | Suíte técnica e ensaio separado de 12 casos; nenhum modelo pago |
| Avaliado com modelos reais | Não executado; qualidade de title, clareza, conclusões indevidas, dependências omitidas, perguntas ao operador e custo real continuam sem medição |
| Aprovado para uso | Nenhuma das novas fichas recebeu aprovação operacional; publicações do harness são exclusivamente sintéticas, em diretório próprio |
| Pendente | Revisão humana das 61 candidatas e seu escopo; reconciliação semântica dos demais fragmentos; inspeção/transcrição de mídia; autorização da publicação e da unit antes de ativar |

O inventário abrange toda a pasta fornecida, não apenas um curso piloto. Isso
**não significa que toda a suíte foi semanticamente integrada ou aprovada**.
O texto não revisado continua como fragmento com destino pendente, consultável
localmente pelo operador, mas não é automaticamente fornecido aos modelos.
Os relatórios deixam essa diferença explícita.

## Artefatos locais e cobertura

Os artefatos confidenciais vivem em `data/training_suite/`, ignorado pelo Git.
Nenhum original foi alterado; Word, snapshots, PDFs e mídia são lidos no lugar.

- Inventário: `inventories/7c9f6e184e9193de2f44a6048299731e62072477d8d0896b048c8ffe0215cf33.json`.
- Pacote: `packages/eba597338d732d23c6c47e8a2b93859c684d1214cb35f8a403bb0ea594655ccb.json`.
- Resumo: `reports/eba597338d732d23c6c47e8a2b93859c684d1214cb35f8a403bb0ea594655ccb.json`.
- Ensaio: `evaluation_final/*.json`; os dados da publicação fictícia ficam em `evaluation_final/fixture_store/`.
- Migração: `migration_report.json`; repetição de importação: `idempotence_report.json`.
- Revisão legível das candidatas: `REVIEW_PACKAGE.md`; estrutura de decisão com
  revisor/motivo/data intencionalmente vazios: `REVIEW_TEMPLATE.json`.

Foram inventariadas **788 fontes**, incluindo **23 duplicatas byte a byte**.
Há **652 fontes com extração textual**, contando snapshots; **2.618 fragmentos**
endereçáveis de fontes correntes. O Word contém 3.325 parágrafos e 82 mídias.
Mídia embutida tem hash próprio e estado `not_examined`; extração de texto não
declara imagem examinada ou vídeo transcrito. Datas sugeridas pelo nome do
arquivo são `capture_date_hint`, nunca datas de vigência. Conclusão no LMS
permanece desconhecida quando não houve validação individual da fonte.

O pacote contém **61 candidatas**, das quais **40 são critérios A/C/D/F/I/L**.
F9 não foi criado. As outras propostas incluem scope/certification, conteúdo de
Title Opinions da base original, backward/forward, indexing e buscas negativas,
descrições/GIS, reservations de Ohio, NPRI, full lease/fields, HBP/produção,
lease status, dimensões de ownership, assignments/curative, PREP e SME.
Pearl, Cortez e Emirates têm propostas específicas e relações de conflito de
escopo. A regra Emirates MEMO_ONLY preserva a origem da ficha antiga.

A reconciliação tem **4.021 entradas** de fontes, seções e fragmentos. Não são
4.021 temas independentes: há sobreposição de snapshots e do material cumulativo.
Correspondências por palavras com OKF são sugestões de revisão, **não prova de
equivalência semântica**. As relações curadas são identificadas separadamente.
Administrativo, exemplos/quizzes e cobertura pendente não viram evidência de unit.

## Como importar e consultar

Execute os comandos a partir da raiz do repositório, no Python do projeto.
Eles não fazem chamadas a modelos nem acessam LMS/portais.

```powershell
python -X utf8 -m src.casefile.training_package 'C:/Users/Renato/.codex/.chatgpt-projects/g-p-6a1ebf2064a08191b0ae034876b5a605'
python -X utf8 -m src.casefile.training candidates 'royalty memorandum'
python -X utf8 -m src.casefile.training --help
```

O inventário é um manifesto identificado pelo hash do próprio conteúdo. Não
usa a hora de execução como identidade. Mesmo conteúdo importado outra vez
não cria versões. Alteração de texto, metadados ou interpretação de uma ficha
cria outro hash e preserva os bytes anteriores. Snapshots e duplicatas mantêm
identidade e destino, sem reingerir todos os seus parágrafos.

Para nova extração semântica, prepare um JSON com uma lista de fichas e execute:

```powershell
python -X utf8 -m src.casefile.training import propostas.json
```

O contrato está em `src/casefile/training.py`. Campos: `rule_id`, `literal`,
`interpretation`, `nature`, `scope`, `conditions`, `exceptions`, `relations`,
`sources`; cada fonte exige `path`, `sha256`, `locator`, `quote`. A importação
confere hash e presença literal do trecho. Preserve o ID ao corrigir uma ficha.
`source_date`/`effective_date` desconhecidos ficam nulos. Um escopo vazio não é
global; `*` só deve ser uma declaração deliberada de aplicabilidade geral.
Não transforme fragmentos mecânicos em regras sem revisão semântica.

## Publicação e ativação explícitas

O pacote entregue é uma proposta de revisão. Não copie as publicações de
`evaluation_final/fixture_store` para a base operacional. Para publicar após
revisão, crie um JSON com esta estrutura; `refs` deve conter somente as versões
exatas aprovadas, disponíveis no pacote:

```json
{
  "refs": [{"rule_id": "ID_REVISADO", "version": "HASH_DA_VERSAO"}],
  "reviewer": "nome do revisor",
  "reason": "decisão e ressalvas da revisão",
  "reviewed_at": "data real da revisão",
  "inventory_id": "7c9f6e184e9193de2f44a6048299731e62072477d8d0896b048c8ffe0215cf33"
}
```

```powershell
python -X utf8 -m src.casefile.training publish revisao.json
```

O comando imprime o ID imutável da publicação. Fichas com escopo desconhecido,
fragments, quizzes, examples ou administrative são recusadas. Uma correção
gera outra publicação; não substitui a anterior. `withdraw retirada.json`
registra retirada com `release_id`, `reviewer`, `reason`, `reviewed_at` e impede
novas sessões usando aquela publicação; os contextos históricos ficam no banco.

A migração **0008_training_suite foi aplicada no banco local**. O relatório
confere igualdade dos registros de units, claims, sessões, custos e decisões
antes/depois. Em outra instalação, execute `python -m src.casefile db migrar`.
Reinicie o processo do dashboard para carregar a API/interface atualizadas.

Para ativar numa unit após decisão do operador, prepare `escopo.json`:

```json
{
  "release_id": "HASH_DA_PUBLICACAO_APROVADA",
  "reviewer": "nome do operador",
  "reason": "escopo acordado para esta unit",
  "scope": {
    "project": "Emirates",
    "jurisdiction": "Texas",
    "substance": "oil and gas",
    "work_type": "due_diligence"
  }
}
```

```powershell
python -X utf8 -m src.casefile.training activate ID_DA_UNIT escopo.json
```

Esse comando registra `operator_decisions.kind=training_scope`. Não altera o
estado da unit nem chama modelos. O estágio é determinado pelo comando real:
`planejar.examinador` recebe `planning`; `exame.vs3`, `examination`.
As demais dimensões são o contrato explícito do operador. O runtime não deduz
jurisdição/substância por nome da pasta. É possível escolher um store local
alternativo por `--store`; a ativação conserva seu caminho.

## Uso nas sessões e no dashboard

`sessao.rodar` prepara o contexto nos caminhos de planejamento/exame. A
publicação, escopo, aprovação, versões elegíveis e critérios esperados ficam
em `knowledge_contexts`. `knowledge_events` guarda ofertas, consultas,
aplicações, revisões, leituras OKF e novas propostas. O contexto inicial oferece
até quatro fichas, e consultas até oito, com limite de 24 mil caracteres por
oferta; omissões por limite são explícitas. Isso é orçamento de contexto, não
limiar de validade de title.

- `consultar_training(assunto)` consulta a publicação fixada e registra o retorno.
- `aplicar_training` exige versão realmente oferecida, razão, conflitos, lacuna
  e responsável. Pode vincular claim ou pesquisa da mesma unit.
- `revisar_training` aceita atendido/falha/insuficiente/não aplicável. Exige
  justificativa/responsável e, para atendido/falha, claims de evidência.

Retomadas mantêm a publicação explicitamente selecionada. Outra importação
não muda a versão em uso. Nova decisão de escopo/publicação aparece como mudança
de publicação no manifesto. Os bytes originais têm status `candidate`; a
aprovação pertence à publicação separada, sem alterar o hash da ficha.

Leitura OKF preserva as duas fichas de mesmo slug, local e global, seus bytes,
hashes e origens. Uma ausência oferece sugestões por palavras do corpo inteiro.
`write_knowledge` no Case File agora cria proposta imutável em
`_casefile/fichas_candidatas/`, preservando o legado. A proposta também fica
visível no evento do banco quando feita em sessão integrada. Nenhum módulo
congelado foi expandido para reintroduzir decisões de title.

O endpoint `/api/units/{id}/training` e a aba **Training Suite** mostram o
manifesto, versões, eventos e critérios faltantes. O drawer do claim separa
documento probatório de orientação aplicada, razão, lacuna e responsável.
O estado operacional segue **banco → API → interface**, não Markdown/logs.

## Confiabilidade e limites

O cliente da sessão contabiliza cada resposta recebida antes do dispatch de
ferramentas, incluindo respostas cuja ferramenta causa interrupção. `finally`
fecha a sessão com o uso confirmado; os logs são retidos por session ID e o
caminho antigo continua disponível como ponteiro de compatibilidade. Custo
desconhecido fica nulo na sessão. Uma queda abrupta do processo/SO ainda pode
impedir o `finally`; respostas já registradas conservam o custo. Falha da rede
antes de receber o usage pode exigir conciliação com o provedor.

O VS3 exige a população declarada inteira, posições pelo identificador exato
`population::member` (grupos antigos precisam de cobertura explícita por membro),
grafo, claim de corte e população de revisão preenchida. `final` exige também
uma decisão `vs3_acceptance` com `approved=true` e o `snapshot` devolvido por
`vs3_entregaveis.completude`. Mudança de dados invalida aquele aceite. Estados
insuficiente/falha não desaparecem por terem sido revisados. O código verifica
registros e o aceite, não julga title nem certifica a correção do grafo.

O roteiro antigo da Josh B foi conservado em `profile_josh_b.py`. A seleção
exige política `examination_profile=josh_b_golden` e a identidade `JOSH B UNIT`.
Essa política não foi ativada nesta entrega. O roteiro genérico usa somente
populações, claims e decisões da unit atual. Nenhuma versão de treinamento,
resposta do examinador ou gabarito foi adicionada ao verificador de família B.

## Verificação reproduzível

```powershell
python -m pytest -q --basetemp=.pytest-training-final
python -X utf8 -m evaluations.training_suite.run_contracts data/training_suite/packages/eba597338d732d23c6c47e8a2b93859c684d1214cb35f8a403bb0ea594655ccb.json data/training_suite/evaluation_final
```

Baseline: **1.018 testes passaram**. Após a integração: **1.047 passaram**,
incluindo PostgreSQL em schemas temporários. Sem skips nessa execução. As
tentativas iniciais no sandbox tiveram erros de permissão de temporários;
foram separadas dos resultados obtidos fora dele. O teste existente que contava
uma entrada de custo por sessão passou a conferir os totais por sessão, pois
agora o custo é persistido por resposta recebida.

O ensaio isolado cobre os 12 casos do diagnóstico: outros lands, gaps de
produção, prior reservation, memo, Pearl/Emirates, certification, parent tract,
busca negativa, escopo específico, vídeo parcial, grafo parcial e cegueira B.
Nos mesmos assuntos livres: **0/12 hits por slug antigo, 12/12 orientações
esperadas recuperadas**. Isso não representa ganho percentual de qualidade:
consultas por slug conhecido continuam possíveis no legado. O harness registra
evidência sintética igual nos dois braços, contexto, fontes, rubrica e resposta
roteirizada de aplicação. Não pontua conclusões jurídicas de mocks. Seus casos
e rubricas ficam em `evaluations/`, fora da ingestão e do contexto de ensino.

Futuro ensaio real exige autorização de custo e avaliação humana com as mesmas
evidências/condições: pertinência, uso fora de escopo, conclusões indevidas,
dependências omitidas, perguntas repetidas, clareza e custo incremental.
