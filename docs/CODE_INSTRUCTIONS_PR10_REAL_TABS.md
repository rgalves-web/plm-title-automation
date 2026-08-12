# ORDEM DE TRABALHO — PR-10 · As abas que nunca foram escritas, com dados reais da Josh B
_Emitida 2026-08-12 pela sessão Cowork, após ratificação externa do PR-9 (gate whitelist verificado célula a célula, md5 do artefato conferido contra o disco)._

**Branch:** `pr10-real-tabs` a partir de `pr9-whitelist-provenance`. O gate whitelist fica ativo o tempo todo: cada valor novo nasce com trilha, por construção. Quarentena do gabarito ativa: nenhum valor entra por ter sido visto no kit à mão.

## Regra que governa o PR inteiro

Só se escreve o que a rodada prova com citação. O que não se prova fica branco com motivo do vocabulário **e** dono (item de brief ou veredito). Correct-and-fewer beats plausible-and-wrong.

## Itens

1. **Summary.** Client / Acquisition / Operator / State / Counties vêm de dado declarado do engagement (L1 `project`, fonte citada — BPM, Project Log, DPU; ex.: Operator/Seller = EOG Resources, county = Montague, vêm de documento). O que não tiver fonte declarável (ex. DSU STR) fica branco com motivo. **Potential Defect(s) e Outstanding Curative Requirements derivados do gap-hunter**: os grupos de requirement vivos (A-319 Reqs 4/6/10/15/17, curativa do Tract 1, probates de Ector com as causas 1449 / 3734-A / 16915-02), cada um com citação. O supervisor da PLM mandou literalmente "note all this in your ddr" — é esta célula. Aceitação: Summary "Yes" na checklist derivada só se os campos nomeados estiverem preenchidos de fonte.

2. **Ownership - Worksheet.** As linhas por lease×trato com a aritmética ligada: MI da fórmula em prosa via `Fraction` (motor `interest_formula`/`unit_aggregation`, que existe e nunca foi ligado a este caminho). Somas por trato = 1 exato ou PENDING nomeado — nunca arredondamento. O ½ não arrendado do Tract 1 e o EOG WI 0,50 / NRI 0,40 (conclusão 12 do gabarito) devem SAIR da aritmética; a comparação com o gabarito é do harness externo, depois, nunca da rodada.

3. **Ownership - Wells.** Poço #1H API 42-337-34773. O que a DPU/TO provam (well name, unit 220,00 ac, formação Barnett) entra com citação; o que só o RRC prova fica branco com motivo + item de brief (o RRC segue fora do corpus — não inventar).

4. **Agreements.** Só se houver instrumento no corpus que prove um JOA/agreement da Josh B. Sem instrumento = aba em branco com motivo e item `request` ao Seller. Nenhum card de agreement nasce de recital.

5. **PLM Title Review.** Cert dates por trato: enquanto a pergunta ao operador não for respondida (origem de 3/3/2010 A-669 e 9/9/2010 A-319), usar a mesma disciplina da Runsheet A3 — base provisória declarada na célula, `requires_human_verdict`. Landman/Date: dado do operador declarado em config, com fonte.

6. **Checklist re-derivada dos bytes** ao final. A contagem de Yes só sobe onde os bytes provam.

7. **Regressão e prova.** Gate whitelist CLEAN no artefato final; comparação célula a célula das abas novas contra o DDR à mão (harness externo, populações declaradas); Bowen/Maxwell 0 FAIL / 0 MISMATCH em leitura; suíte verde. **Anexar artefato + relatório do gate + write_manifest. Relatório sem artefato não fecha.**

## Fora de escopo

Runsheet definitivo e Title Documents (dependem das cert dates por trato — pergunta aberta com o operador); RRC (aquisição é do operador, o sistema instrui via brief).

## Pendência que trava o item 5 (uma frase do operador resolve)

De onde vêm as cert dates **3/3/2010 (A-669)** e **9/9/2010 (A-319)** do runsheet à mão? Os candidatos do sistema (9/4/2010 e 21/5/2010) não batem. E a base é por trato — trato sem opinião não tem run?
