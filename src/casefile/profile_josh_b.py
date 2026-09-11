"""Historical Josh B simulation fixture; selected by explicit operator profile."""
from typing import Any
from src.casefile.exame_vs3 import _digest_claims

def task_josh_b(repo: Any, unit: dict[str, Any]) -> str:
    posic = repo.populacoes_contagens(unit["id"])
    return "\n\n".join([
        f"UNIDADE: {unit['canonical_name']} — VS3, exame canonico sob "
        f"simulacao. Populacoes: {posic}. Documentos indisponiveis na "
        f"simulacao: 441.275 (Prior Lease BRA-DE), 514.412 (lease "
        f"0220953/005), DOTO/DOI, Quitclaim/Affidavit/Landman Statement "
        f"Stewart.",

        "DIGEST DOS CLAIMS ATIVOS (sua materia-prima; NAO releia o que ja "
        "esta aqui):\n" + _digest_claims(repo, unit),

        "DEVERES, nesta ordem:\n\n"
        "1. DATA DE CORTE: determine a data de corte do golden case por "
        "FONTE AUTORIZADA (spec BPM, workbooks de referencia datados, "
        "notas datadas, XREF 06-16-2026...). Registre claim fact entidade "
        "'data de corte do exame' com a data, a fonte e o trecho. NUNCA "
        "assuma a data atual de 2026 nem 'ate o presente'. Se "
        "indeterminavel, pedir_intervencao.\n\n"
        "2. GRAFO DE TITULO (`propor_grafo`): por tract, lease e "
        "interesse — baseline dos TOs com certification date, instrumentos "
        "posteriores, mineral owners, lessors/lessees, assignments, "
        "profundidades, top leases, ORRI/NPRI, direitos executivos/nao "
        "executivos, pooling consent, releases, gaps, curatives. Toda "
        "aresta com claim_id + documento.\n\n"
        "3. TO 155ac x UNIT TRACT 2: investigue a relacao entre o parent "
        "tract de 155 ac e o Tract 2 de 80,02 ac por legal descriptions e "
        "metes and bounds (Exhibit B da DPU cita adjoiners com acreagens; "
        "o TO p.1 lista 4 tratos: 119.62+33.72+0.38+1.28). COINCIDENCIA DE "
        "NOMES NAO PROVA amarracao. So registre "
        "`diferenca_gross_explicada` se DEMONSTRAR documentalmente; senao "
        "a amarracao PERMANECE parcial/confianca media (registre o que "
        "falta).\n\n"
        "4. BRA-DE: separe o que os documentos locais PROVAM (top leases "
        "2011, assignment K1401501, ORRI/piso 75%, depths do assignment de "
        "2008) do que fica `impedido_pela_simulacao` sem a Prior Lease "
        "441/275 (vigencia efetiva, termos da prior). \n\n"
        "5. STEWART: separe o que o release-of-suspense prova (em pay, "
        "curative recebido) do que NAO prova (registro); o Quitclaim/"
        "Affidavit/Landman Statement sao `documento_ausente`.\n\n"
        "6. SERIE 0220936: mantenha 67 no Exhibit A, 7 "
        "in_dpu_but_zero_unit_acres (A-811), 60 potencialmente "
        "contribuintes — nada some do Lease Review nem da trilha.\n\n"
        "7. POSICOES (`classificar_populacao`): TODA populacao material "
        "termina classificada — os 5 tracts, o poco, a cadeia BRA-DE, "
        "cada TO, o DOTO/DOI, o release Stewart, e as leases por GRUPO "
        "homogeneo (ex.: '60 leases contribuintes com instrumento no "
        "corpus', 'serie 0220936 (7)', '4 leases so na entrega'...) — "
        "grupos cobrindo as 67, sem excecao silenciosa.\n\n"
        "8. CLAIMS PRONTOS PARA DDR (`propor_claims_ddr`): para os claims "
        "que alimentarao o DDR, celulas/abas candidatas (fichas "
        "ddr-template-structure-* ajudam) e limitacoes. NAO escreva no "
        "workbook.\n\n"
        "Leituras novas: SOMENTE para a data de corte e o item 3 (e o "
        "estritamente necessario). O orcamento e curto e o cache e seu "
        "aliado. Ao final, resuma o que ficou aberto.",
    ])
