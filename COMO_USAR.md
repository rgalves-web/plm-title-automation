# COMO USAR — minorh

## 1. Abrir o terminal na pasta certa
Explorador de Arquivos → `C:\Users\Renato\PURPLE LAND MGMT\plm-title-automation` →
clicar na barra de endereço → digitar `cmd` → Enter.

## 2. Rodar numa unidade
    minorh unidade "C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates\<NOME DA UNIDADE>"

Ao final aparecem os três números (`exige N · escrevi X · branco Y · faltam Z`) e o custo.
Na pasta da unidade surgem:
- **PEDIDOS.md** — o que buscar, onde e por qual método
- **PERGUNTAS.md** — o que só o operador decide

## 3. O ciclo
1. Buscar o que os pedidos mandam e jogar os arquivos em `FILES\` da unidade.
2. Responder as perguntas escrevendo embaixo de cada uma no `PERGUNTAS.md` (Bloco de Notas serve).
3.     minorh continuar
   Lê só o que é novo e mostra o delta. Repetir quantas vezes precisar.

A qualquer momento (sem custo):
    minorh estado
    minorh perguntas

## 4. Fechar
Quando o que existe for tudo:
    minorh ship
Sai em `_minorh\ship\` na pasta da unidade: `DDR.xlsx` (toda célula com fonte),
`AUDITORIA.json` (100% das células conferidas, uma a uma) e `MANIFESTO_LACUNAS.md`.

## Notas
- Cada comando gasta API; o custo aparece no fim. A unidade sintética inteira custou ~$6,59.
- Se a janela fechar no meio, nada se perde: o estado fica gravado e `minorh continuar` retoma.
- As respostas dadas em PERGUNTAS.md viram regra para as próximas unidades — cada pergunta se responde uma vez.
- Opcional: uma `OPENAI_API_KEY` no `.env` faz a auditoria rodar numa segunda família de modelo.
