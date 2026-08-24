---
concept: escopo-cruzado-quando-xref-e-schedule-nao-estao-no-corpus
type: regra
sources:
- '_cp2_sintetica: FILES/ com 6 documentos, sem XREF e sem Lease & Mineral Schedule'
- ficha global `lease-mineral-schedule-recording-multi-condado`
- PEDIDOS.md de _cp2_sintetica, itens P-5 e P-6
links:
- lease-mineral-schedule-recording-multi-condado
- cartorio-courthousedirect-arvore-e-busca
- precedente-divergencia-de-referencia-de-registro-resolve-se-no-cartorio
unit: ''
confidence: alta — procedimento derivado de fichas globais existentes, aplicado em
  _cp2_sintetica
---

## Unidade sem XREF e sem Lease & Mineral Schedule: o escopo cruzado NÃO se fecha — declare isso

O cruzamento exigido (Exhibit "A" × XREF aba 1 × XREF aba 2 × Schedule, county-aware) precisa de 4 fontes. Quando o corpus só tem a DPU, o cotejo **não é possível** — e a tentação é dizer "Exhibit A confere consigo mesmo".

### O que fazer (custa 1 branco declarado + 2 pedidos)
1. `declarar_branco` na entidade **"escopo cruzado da unidade"**, nomeando as três consequências concretas:
   - lease presente no XREF/Schedule e ausente do Exhibit "A" (ou vice-versa) permanece **invisível**;
   - a leitura county-aware da coluna RECORDING não pôde ser feita → **dual-recording não descartado** (padrão Webb B: Cooke + Montague). Um corpus que só menciona um condado **não prova** condado único;
   - **alocação lease→poço sem fonte**: a DPU põe N leases na unidade, mas não diz quais o poço atravessa. Não inferir da unidade.
2. Dois pedidos ao data room, com `onde` idêntico para empacotar a sentada.
3. **Exigir as DUAS abas** do XREF explicitamente e o **arquivo nativo** da Schedule (export para PDF trunca as células multi-linha da coluna RECORDING, que é justamente onde mora o segundo condado).

### Efeito no censo
Nenhum agora — mas **declare a ressalva**: se XREF ou Schedule trouxer lease/trato/poço a mais, o censo é redeclarado. Um censo que não avisa que pode subir se faz passar por fechado.
