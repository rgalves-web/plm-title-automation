---
concept: dpu-eog-exhibit-a-layout-e-custo-ocr-vs-imagem
type: layout
sources:
- k1402139 (decl of pooled unit- josh b unit-unit agreement)/unit dec - josh b unit
  - rec.tif p.1-5, comparando modo ocr e modo imagem na mesma página
links: []
unit: ''
confidence: alta
---

## Declaration of Pooled Unit da EOG — layout fixo e a armadilha de custo

### Layout (constante nos DPUs EOG do projeto josh/Montague-Cooke)
- **p.1** — corpo dispositivo. Traz, em UMA frase, três campos de ouro: nome do unit, acreagem ("shall be deemed to contain N acres") e a limitação de profundidade ("further limited in depth to the X formation only"). Cabeçalho carrega VOL/PAGE do recording. Condado no bloco STATE/COUNTY.
- **p.2** — assinaturas/reconhecimento.
- **p.3+** — **Exhibit "A"**: tabela `EOG LEASE NO. | LESSOR | LESSEE | DATE | VOL. | PAGE`, precedida da frase que fixa o condado de TODOS os recordings ("ALL REFERENCES TO RECORDING DATA ARE REFERENCES TO INSTRUMENTS FILED IN THE REAL RECORDS OF <CONDADO> COUNTY, TEXAS"). ~43 linhas por página. Lease no. no formato `NNNNNNN/NNN`, que nas pastas de FILES/ aparece como `NNNNNNN-NNN`.
- **penúltima** — **Exhibit "B"**: metes and bounds, abre com "Metes and Bounds Description of a N acre Pooled Unit located in the <survey>, A-NNN, ... in <condado> County, Texas." Amarra a Deed Records por Vol/Page.
- **última** — **Exhibit "C"**: plat.

### ARMADILHA DE CUSTO — não confie no OCR no Exhibit "A"
Na MESMA página (p.3), o modo `ocr` devolveu **808 caracteres e ~11 leases**, com lessores em branco, números de lease sumidos e volumes órfãos flutuando ("56", "434", "441 97"). O modo `imagem` devolveu **as 43 linhas completas**. O OCR colapsa tabelas de bordas finas com células multi-linha: ele perde LINHAS INTEIRAS silenciosamente e deixa fragmentos que parecem dados.
**Regra**: Exhibit "A" de DPU → ler em `imagem` de saída. Vale os ~4x: é o documento que fixa o denominador da unidade, e um lease perdido é uma linha inteira (40 campos) ausente do DDR sem ninguém notar. Corpo (p.1) e Exhibit "B" → `ocr` basta, são prosa corrida.

### Alterações manuscritas
Conferir a coluna VOL/PAGE contra a tipografia das linhas vizinhas. Uma célula em caligrafia num exhibit GRAVADO é alteração pós-datilografia: pode ser correção legítima ou erro introduzido. Nunca aceitar em silêncio — rebaixar a confiança e pedir cópia certificada. Sinal de apoio: Vol fora da sequência dos leases irmãos da mesma data (ex.: Vol 610 entre irmãos em Vol 439).
