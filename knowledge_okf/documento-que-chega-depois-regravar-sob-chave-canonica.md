---
concept: documento-que-chega-depois-regravar-sob-chave-canonica
type: regra
sources:
- '_cp1_sintetica: gravar_campo entidade "lease 0999001-005" × entidade usada na sessão
  anterior — 7/7 retornaram substituiu:null'
- 'identity-keys-lease (ontologia): eog_lease_number + recording_book_page'
links:
- identity-keys-lease
- resolver-identity-by-key-fixture
- manual-10-4-ciclo-de-vida-missing-files
- manual-7-3-chaves-de-reconciliacao
unit: ''
confidence: alta — observado diretamente (7 campos re-gravados, 7 × substituiu:null)
---

## Documento pendente que chega depois: regrave sob chave canônica e cheque `substituiu`

Quando um PEDIDO é cumprido numa sessão posterior, os campos daquela entidade **já existem na memória** — preenchidos por fonte substituta (Exhibit "A", ownership report) ou declarados em branco. Regravar com a fonte primária é certo; o perigo é **a string da entidade**.

### O sinal
`gravar_campo` devolve **`substituiu: null`** = criou registro novo. Ao regravar campo que você **sabia** existir, `null` não é sucesso: é aviso de que a string da entidade **não bate** com a da sessão anterior (`lease 0999001-005` × `0999001-005` × `lease 0999001-005 (elisa ramos)`). Resultado: **duas entidades para a mesma coisa** — linha duplicada no DDR, e brancos velhos convivendo com valores novos.

### Procedimento
1. **Antes** de regravar, leia a ficha da unidade e reuse **a string exata** já usada. Se não estiver registrada, é falha da ficha anterior — corrija.
2. Regrave assim mesmo (o dado primário vale mais que a estética da chave) e **confira o retorno**.
3. `substituiu: null` inesperado → **registre o conflito na ficha da unidade**, nomeando as duas strings, a chave de identidade que as funde e **qual versão prevalece**. Não deixe para o ship descobrir.
4. Regra de prevalência: **instrumento primário > transcrição** (Exhibit "A", schedule, ownership report). Brancos declarados sobre campos agora documentados ficam **superados** — diga isso com essa palavra.
5. Fundir só quando a chave de identidade da ontologia fecha e as versões **concordam** nos campos comuns. **Discordando, não funda**: é achado de curative, não problema de chave.
6. Na ficha da unidade, deixe a string canônica escrita para a próxima sessão.

### Efeito no censo
Documento atrasado que preenche linha **já declarada** mexe no **numerador**, nunca no denominador — o censo vem do que o registro declara (Exhibit "A"/"C"), não do que o corpus tem. Redeclare o censo só se ele revelar **lease/trato/poço que o registro não declarava**. Censo que não se move quando chega documento esperado é sinal de que foi bem tirado.
