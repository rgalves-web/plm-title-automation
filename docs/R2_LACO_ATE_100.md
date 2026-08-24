# RODADA 2 — o sistema pronto para o Renato usar
_Ordem de 12/08/2026. Branch `r2-sistema-operavel` a partir de `r1-examinador-ia`. Regra da arquitetura mantida: nenhuma decisão em Python._

**O entregável desta rodada não é um número contra o gabarito. É um sistema que o Renato aponta para uma unidade nova e opera até o DDR sair.** A Josh B serve só de banco de provas da máquina, porque é o corpus que está no disco. Bowen e Maxwell ficam em leitura, como controle.

---

## 1. O que o Renato faz, do começo ao fim

```
minorh unidade "C:\...\BKV122TX - Project Emirates\<NOVA UNIT>"
```

O sistema lê tudo o que existe na pasta, monta as memórias, calcula o censo da unidade e **para**, com duas coisas na tela:

```
CENSO — <NOVA UNIT>
  a unidade exige      1.284 campos
  escrevi                 402  (todos com citação)
  declarei em branco       88  (motivo e dono)
  dependem de documento   794

PEDIDOS  →  PEDIDOS.md   (11 itens, 2 telas)
PERGUNTAS →  PERGUNTAS.md (3 esperando você)
```

O Renato busca os documentos, joga em `FILES/`, responde as perguntas no arquivo, e:

```
minorh continuar
```

O sistema lê **só o que é novo**, atualiza as memórias, recalcula o censo e devolve o delta: *fechei 310 campos, restam 484, destes 300 dependem de documento que continuo pedindo.* Repete quantas vezes for preciso.

Quando não houver mais o que buscar, ou quando o Renato decidir que aquilo é tudo que existe:

```
minorh ship          # escreve o DDR e audita 100% das células
```

Sai o DDR com toda célula rastreada, o relatório da auditoria, o kit na árvore da PLM e o manifesto de cada lacuna com dono.

Comandos de apoio: `minorh estado` mostra os três números a qualquer momento, `minorh perguntas` lista o que está esperando resposta.

---

## 2. O que falta construir para isso existir

### 2.1 O censo — a peça que faltou na Rodada 1

O modelo escreveu 6% do documento e disse "terminei". Não faltou orçamento: usou 34 turnos de 400. Faltou saber o tamanho do que faltava.

**Ordem:** antes da primeira célula, o modelo produz o censo da unidade a partir do que leu — o Exhibit "A" da DPU diz quantas leases existem, o cabeçalho de cada aba diz quais colunas cada linha exige, o Exhibit "C" diz quantos tratos, o RRC diz quantos poços. Disso sai o denominador.

O censo é ficha OKF escrita pelo modelo. **Não pode ser lista em Python** — seria portão com outro nome, e o valor está justamente em ele derivar o denominador do documento que leu, em qualquer unidade, sem ninguém programar a unidade.

### 2.2 A memória como substrato, a planilha como projeção

Hoje o modelo escreve direto na célula, e por isso o trabalho não sobrevive entre rodadas.

**Ordem:** ele trabalha em fichas OKF por entidade — uma por lease, trato, poço, parecer, instrumento. Cada campo carrega valor, citação literal e confiança, ou fica vazio com motivo e dono. O DDR é escrito **a partir das fichas**, no `ship`. Uma lacuna passa a ser campo vazio numa ficha, que é o que a torna contável de uma rodada para a outra.

### 2.3 Pausa e retomada com estado

`minorh continuar` só existe se o estado persistir: censo, fichas, o que já foi lido, o que foi pedido, o que foi respondido. O ledger da Rodada 1 já grava a cada turno; agora o censo e as fichas entram junto, e o que já foi lido não se relê.

### 2.4 As perguntas em lugar que o Renato responde

Na Rodada 1 o modelo fez duas perguntas boas e elas morreram no ledger. `PERGUNTAS.md` recebe pergunta, candidatos e o que desempataria; o Renato escreve a resposta na linha de baixo; `minorh continuar` lê e **grava como precedente** em OKF. Respondida uma vez, vale para as próximas unidades.

### 2.5 Auditoria de 100%, sem amostragem

Toda célula, uma a uma, por modelo de família diferente, que não vê o raciocínio do autor — só a célula, o valor e a citação. Reabre a página citada e responde: a página sustenta este valor? contradiz outra célula deste arquivo? é da unidade certa?

A segunda pergunta não é teórica. Na Rodada 1, `Unit and Pooling Agreements!B8` diz "**62** leases pooled per Exhibit A", `Runsheet!J4` diz "Pools **67**" e `Summary!B13` diz "**67**". Mesma DPU citada, dois números, mesmo arquivo. A verdade é 67. Auditoria de 100% pega; amostragem não.

Reprovada, a célula volta ao examinador com o motivo. Reprovada de novo, vira branco declarado ou pergunta. **Nada embarca sem auditoria aprovada.**

Custo: ~2.900 células em lotes de 25 dão ~120 chamadas com as páginas já em cache. **$10 a $15 por unidade.**

### 2.6 A régua, para quando houver o que medir

A comparação da Rodada 1 mede por coordenada, e o modelo escolheu outra ordem de linhas. Realinhado por identidade de lease: **17 leases escritas, 51 campos comparáveis, 50 concordam**, e a única divergência é a mão ter escrito `Dundley (Dudley) Edward Jordan` contra `Dundley Edward Jordan`.

As 84 divergências do relatório são quase todas artefato de régua. **O problema da Rodada 1 não é precisão, é cobertura.** `compare.py` alinha por identidade antes de comparar, e diferença de posição de linha é relatada como layout, nunca como erro de fato.

### 2.7 O custo, contado direito

O log traz `entrada: 2` nos 34 turnos: tokens de entrada não estão sendo contados. Os $2,85 não são piso conservador, são conta errada. Sem isso o Renato não sabe o que uma unidade custa antes de mandar trezentas.

---

## 3. Como se prova que está pronto

**Não é score contra gabarito.** É a máquina rodando o laço inteiro:

1. `minorh unidade` no corpus da Josh B → censo declarado, três números, `PEDIDOS.md` e `PERGUNTAS.md` gerados.
2. Uma volta completa: alguns arquivos movidos para dentro de `FILES/`, uma pergunta respondida, `minorh continuar` → **o censo tem de baixar**, e o delta tem de bater com o que entrou.
3. `minorh ship` → DDR escrito das fichas, auditoria de 100% executada, relatório listando o que reprovou, kit montado, manifesto com dono em cada lacuna.
4. Bowen e Maxwell em leitura, inalteradas.
5. Custo real reportado.

Passando isso, o sistema está pronto para o Renato apontar para a primeira unidade de verdade, e a medida que importa aparece sozinha: **quantas horas dele a unidade consome.**

---

## 4. Aceitação

- `minorh unidade`, `continuar`, `estado`, `perguntas`, `ship` funcionam numa pasta de unidade qualquer, sem nada codificado sobre a unidade.
- Censo derivado pelo modelo, com o denominador declarado.
- Uma volta de laço demonstrada, com o censo caindo.
- DDR escrito das fichas, toda célula com citação.
- Auditoria de 100% executada, com a lista de reprovações.
- O `62 contra 67` resolvido pela auditoria, não por conserto manual.
- Custo real, com entrada e cache.

**Anexar:** o log da sessão de operação (os comandos e o que apareceu na tela), o censo, o DDR, o relatório da auditoria, o kit, o custo. Relatório sem artefato não fecha.
