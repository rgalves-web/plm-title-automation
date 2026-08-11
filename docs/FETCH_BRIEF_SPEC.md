# FETCH BRIEF — contrato do entregável de aquisição

**Data:** 2026-08-11 · **Origem:** decisão do Renato — o sistema **não busca documento; instrui a busca**. O Drive connector e os browser agents saem do caminho crítico; em troca, a instrução vira entregável de primeira classe. · **Companions:** `OKF_MIGRATION_PLAN.md` §3.1, `DDR_JOB_FLOW_SPEC.md` S3 GATHER, `WORKBENCH_BLUEPRINT.md` §4.3 (`checklist_builder`, já construído — este spec é o contrato de qualidade do que ele emite).

---

## 0. A regra

**Nenhum documento é declarado faltante sem local provável e termos exatos de busca.** Isso já era regra operacional; agora é **gate**: uma rodada com um item de brief incompleto não fecha. O motivo é econômico — o operador é o recurso escasso, e um brief vago transfere para ele o trabalho de descobrir o que procurar, que é justamente o trabalho que o sistema tem de fazer.

O brief é a **contrapartida** de não haver connector. Se o sistema não busca, ele tem de instruir tão bem que a busca fique mecânica.

---

## 1. Quando é gerado

- **A cada rodada**, ao fim do S6 RUN, junto com o DDR parcial (é o "13" do fluxo de 19 passos).
- Regenerado inteiro, nunca editado incrementalmente — é **projeção do ledger + do perímetro**, como o Missing Files report.
- Duas saídas do mesmo dado: `fetch_brief.yaml` (máquina, versionado no caso) e `FETCH BRIEF - <UNIT> - <data>.md` (humano, para o Renato ler no celular ou imprimir).

## 2. Campos obrigatórios por item

Todo item **exige os oito**. Falta de qualquer um = item inválido = rodada não fecha.

| Campo | Conteúdo | Exemplo real (Josh B) |
|---|---|---|
| `id` | estável entre rodadas, para o item ser rastreável | `lease_0220604-021` |
| `what` | o documento, com a identidade completa (chave do OKF L0, não o apelido) | "OGL Mallory W. Joiner, lease EOG 0220604-021, gravada Vol. 557 Pg. 240, 24/01/2011" |
| `where` | **locais ranqueados**, do mais provável ao menos, cada um com o caminho concreto | 1) Drive, pasta de lease `0220604-021`; 2) irmãs `0220604-017/-019/-020` (a pasta pode estar aninhada); 3) cartório de Montague por Vol/Pg |
| `how` | **termos exatos** e o caminho de query do portal — nunca "procure por Joiner" | TexasFile: grantor `JOINER, MALLORY W` + janela 01/2011–06/2011. **Nunca por abstract.** |
| `looks_like` | como reconhecer quando achar, e como reconhecer o falso positivo | "OGL 3 anos, lessee EOG Resources; **não confundir** com Joiner de outra unidade — só vale se Vol. 557 Pg. 240 bater" |
| `unlocks` | que células/abas do DDR o documento destrava (é a justificativa e a ordenação) | "Lease Review L21: royalty, termo, shut-in, pooling, continuous drilling" |
| `already_searched` | **onde já se olhou e não estava**, com data | "4ª rodada 05/08: Drive por nome 'DONALD/CHOCTAW/PRENDERGAST' → 12 resultados, todos A-730, fora do perímetro" |
| `blocking` | trava certificação, ou é desejável-não-bloqueante | `true` — sem ele Ownership-Wells O/Q não certificam |

## 3. Ordenação — por alavancagem, não por ordem alfabética

O brief abre com o que destrava mais. Critério, nesta ordem:
1. **Bloqueia certificação** (WI/NRI verificados do wellbore).
2. **Destrava mais células** por documento.
3. **Custo baixo de aquisição** (um portal, uma sentada) antes de custo alto (pedido a terceiro, correio).

Cada item traz o esforço estimado quando ele é conhecido — "6 leases saem em uma sentada no TexasFile, todas têm Vol/Pg" vale mais para o operador que seis itens soltos.

## 4. Agrupamento por fonte — "uma sentada, uma fonte"

O brief agrupa itens pela fonte que os resolve, para o operador não abrir o mesmo portal sete vezes:

```
RRC (webapps.rrc.texas.gov) — 4 itens, ~30 min
  Caminho: ewaMain.do → W-1 Query → API 33734773 → permit 730771
  ...
TexasFile — 6 itens, todos com Vol/Pg, ~1 sentada
  Método: grantor/grantee + janela de data. NUNCA por abstract.
  ...
Drive PLM — 3 itens
  ...
Terceiros (pedido, não busca) — 3 itens
  Ector County Clerk, Odessa · probate · $5/processo · EctorCountyClerk.Probate@ectorcountytx.gov
  Causas: 1449 (Yentes) · 3734-A (J.C. McConnell) · 16915-02 (Nellie McConnell)
  ...
```

## 5. Receitas de fonte — conhecimento, não improviso

Cada fonte conhecida tem uma **receita versionada em `knowledge/`** (`rules/sources.yaml`), com o caminho de navegação, o método de busca correto e o método **proibido**. Semente obrigatória, das três unidades:

| Fonte | Receita | Proibido |
|---|---|---|
| RRC | `ewaMain.do` → W-1 Query / Completion Query / Production Query, por API | — (registrar quando o site der *application error*: é estado do mundo, não falha do item) |
| TexasFile / CourthouseDirect | grantor/grantee + janela de data | **buscar por abstract** |
| Drive PLM | por nº de lease EOG; se a pasta não existir, olhar as **irmãs numericamente adjacentes** e pastas de **unidades vizinhas que tocam o mesmo trato** | buscar por nome do lessor (traz leases de outras unidades) |
| Cartório de Montague | por Vol/Pg | — |
| Terceiros (Clerk, Seller, examinador) | é **pedido**, não busca: quem, canal, custo, prazo | tratar como se fosse achável em portal |

Receita nova aprendida numa unidade entra como lição (L3) com fixture; nunca fica só no brief de uma unidade.

## 6. Conhecimento negativo — o campo que economiza mais tempo

`already_searched` existe por causa de um caso real: a 4ª rodada de Josh B trouxe **12 itens, nenhum aproveitável** — todos já sabidamente fora do perímetro. Um brief que não carrega o histórico de exclusão faz o operador repetir a busca errada.

Regra: **todo SKIP de triagem e toda exclusão de perímetro alimentam `already_searched`** do item correspondente, com data e motivo do vocabulário fechado. Se o sistema já provou que algo está fora, o brief diz isso **antes** de o operador pensar em procurar.

## 7. Itens que NÃO são busca

O brief separa explicitamente, porque a ação do operador é diferente:
- **`fetch`** — existe em algum lugar, é só ir buscar.
- **`request`** — depende de terceiro (Seller, Clerk, examinador): o brief traz o texto do pedido pronto, o canal e o custo.
- **`confirm`** — não falta documento, falta conferência (os 4 conflitos vol/página de Josh B; a divergência de perímetro DPU×XREF). O brief diz o que conferir, contra o quê, e qual valor o DDR adotou provisoriamente.
- **`unfindable`** — o operador já declarou não-localizável: sai do brief e entra no **Missing Files report** com todo o histórico de caça. Não desaparece: muda de lista.

## 8. Aceitação (o gate)

Um brief é válido quando:
1. **Cobertura total:** toda célula em branco do DDR aponta para exatamente um item de brief, ou tem motivo terminal (`fato_inexistente_no_registro` / declarado unfindable). Célula em branco órfã = FAIL.
2. **Completude por item:** os 8 campos preenchidos, `how` com termos literais, `where` com ao menos um local concreto.
3. **Sem método proibido:** nenhum `how` contradiz a receita da fonte (busca por abstract = FAIL).
4. **Idempotência entre rodadas:** item resolvido sai; item não resolvido reaparece **com o `already_searched` acrescido** da tentativa anterior.
5. **Rastreabilidade:** cada item cita o que o gerou (perímetro, gap-hunt, requirement de TO, divergência) com arquivo + página quando houver.

**Aceitação de replay (Checkpoint A):** o brief gerado no replay de Josh B, comparado ao gabarito escrito, tem de conter — sem ajuda — os 8 itens de lease sem pasta, o bloqueador do TO do Unit Tract 1 com os 5 locais alternativos, os 4 itens do RRC com o caminho de query, os 3 probates de **Ector County** (não Montague) com causas e canal, e os 4 conflitos vol/página como `confirm`. E tem de **não** propor busca por abstract nem por nome de lessor.

## 9. O que o brief nunca faz

Não estima, não infere documento que não foi citado por nenhuma fonte, não nomeia item sem local, não repete item já declarado unfindable, e não esconde que uma tentativa anterior falhou. Um brief honesto pode dizer "não sei onde está" — desde que diga onde já se olhou e o que isso elimina.
