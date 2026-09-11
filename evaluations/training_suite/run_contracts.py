"""Held-out evaluation harness. Never imported or offered by model runtime.

No calls to model providers. Observations measure retrieval/transport contracts,
not the correctness of simulated title answers. Source/quote identity is verified.
"""
import argparse
import json
from pathlib import Path

from src.casefile.training import Store, digest, immutable, applicable
from src.casefile.training_runtime import prepare
from src.examinador.okf import KnowledgeBase
from tests.helpers_casefile import RepoFake, unit_de_teste


CASES = [
    ('other-lands', 'lands lease release producing Pugh', 'lease-status-evidence', 'Emirates', 'Texas', 'oil and gas',
     'Lease fixture cobre dois parcels; o subject nao tem well.', 'Investigar todos os lands e units do lease, sem concluir open pela falta local.'),
    ('production-gap', 'production history cessation shut-in', 'hbp-production', 'Emirates', 'Texas', 'oil and gas',
     'Cadastro fixture: Producing; relatorio de producao com meses ausentes.', 'Separar cadastro da producao, periodo, clausulas e pagamentos.'),
    ('prior-reservation', 'Reference Prior Reservation deed', 'reservation-ohio', 'General', 'Ohio', 'oil and gas',
     'Deed fixture cita reserva anterior, sem instrumento anexo.', 'Pedir instrumento original e preservar ramo mineral.'),
    ('memo-missing-fields', 'MEMO_ONLY royalty full OGL', 'emirates-memo', 'Emirates', 'Texas', 'oil and gas',
     'Memo fixture omite royalty e term.', 'Campos nao demonstrados permanecem pendentes com pedido especifico.'),
    ('pearl-isolation', 'Sliding Scale brine royalty', 'pearl-royalty', 'Pearl', 'Arkansas', 'brine/lithium',
     'Mesmo memo fixture sob escopo Pearl.', 'Convencao especifica nao aparece sob escopo Emirates.'),
    ('certification', 'title certification date coverage', 'scope-certification', 'Emirates', 'Texas', 'oil and gas',
     'Carta fixture posterior a certification declarada no corpo.', 'Distinguir carta, certification, coverage e data de corte.'),
    ('parent-tract', 'Legal descriptions acreage GIS', 'gis-descriptions', 'Emirates', 'Texas', 'oil and gas',
     'Duas descricoes fixture com acreage distinto.', 'Reunir descricoes e outsales; numeros/nomes nao provam amarracao.'),
    ('negative-search', 'indexing names online coverage', 'indexing', 'Emirates', 'Texas', 'oil and gas',
     'Busca fixture em um indice online por intervalo limitado sem hits.', 'Explicitar limites, variantes e cobertura offline.'),
    ('project-scope', 'scope client title certification', 'scope-certification', 'Emirates', 'Texas', 'oil and gas',
     'PM fixture restringe a pesquisa, treinamento geral descreve alcance maior.', 'Expor ambos, registrar escopo e conflito sem apagar fontes.'),
    ('video-gap', 'PREP clarity organization', 'prep-review', 'Emirates', 'Texas', 'oil and gas',
     'Curso fixture concluido; video sem transcricao.', 'LMS nao equivale a cobertura de video nem conhecimento aprovado.'),
    ('partial-graph', 'A1 subject leases', 'tae-A1', 'Emirates', 'Texas', 'oil and gas',
     'Fixture com uma posicao, restante da populacao ainda nao revisada.', 'Preservar criterios faltantes e lifecycle partial.'),
    ('blind-review', 'NPRI fixed floating language', 'npri-fixed-floating', 'Emirates', 'Texas', 'oil and gas',
     'Verificador fixture recebe apenas pergunta e evidencia.', 'Nao oferecer resposta do examinador ou gabarito de quiz a familia B.'),
]


def run(package_path, output):
    store = Store(package_path.parent.parent)
    package = json.loads(package_path.read_text('utf-8'))
    if digest(package) != package_path.stem:
        raise ValueError('package_hash_mismatch')
    fixture_store = Store(output / 'fixture_store')
    for ref in package['refs']:
        fixture_store.put(store.get(**ref))
    release = fixture_store.publish(package['refs'], reviewer='SIMULATED HARNESS ONLY',
                                    reason='No operational approval', reviewed_at='2026-09-11')
    kb = KnowledgeBase(Path(__file__).resolve().parents[2] / 'knowledge_okf')
    rows = []
    for cid, query, target, project, jurisdiction, substance, evidence, rubric in CASES:
        context = dict(project=project, jurisdiction=jurisdiction, substance=substance,
                       stage='examination', work_type='title')
        repo = RepoFake(); unit = unit_de_teste(repo, output/cid)
        repo.decisions.append(dict(id=1, unit_id=unit['id'], kind='training_scope', decided_at='fixture',
            answer=json.dumps({'release_id': release, 'scope': context})))
        sid = repo.abrir_sessao(unit['id'], 'exame.vs3', 'SIMULATED')
        initial, _, dispatch = prepare(repo, unit, sid, 'exame.vs3', fixture_store)
        old = kb.read(query)
        new = dispatch['consultar_training'](query)
        cards = new['cards']
        chosen = next((c for c in cards if c['rule_id'] == target), None)
        if chosen:
            # The scripted response declares only routing, never title correctness.
            dispatch['aplicar_training'](chosen['rule_id'], chosen['version'],
                'Synthetic applicability declaration; human judgement not measured', [],
                'fixture unresolved', 'SIMULATED REVIEWER')
        rows.append({'case': cid, 'same_evidence_for_both_arms': evidence, 'rubric_for_future_human_review': rubric,
                     'query': query, 'context': context, 'old_slug_found': old['encontrado'],
                     'new_returned': [c['rule_id'] for c in cards], 'expected_method_retrieved': bool(chosen),
                     'out_of_scope_returns': sum(not applicable(c, context) for c in cards),
                     'new_context_chars': len(initial) + len(json.dumps(new)),
                     'old_context_chars': len(json.dumps(old)),
                     'methodology_citations': [c['sources'] for c in cards],
                     'trace': repo.knowledge_audit(unit['id']),
                     'actual_cost_usd': 0, 'title_quality': 'not_measured',
                     'improper_conclusions': 'not_measured', 'omitted_dependencies': 'not_measured',
                     'repeated_operator_questions': 'not_measured', 'clarity': 'not_measured'})
    result = {'mode': 'scripted_contracts_only', 'case_count': len(rows),
              'old_slug_hits': sum(r['old_slug_found'] for r in rows),
              'new_expected_hits': sum(r['expected_method_retrieved'] for r in rows),
              'out_of_scope_returns': sum(r['out_of_scope_returns'] for r in rows),
              'real_models_evaluated': False, 'quality_improvement_demonstrated': False,
              'sources_package': package_path.stem, 'cases': rows}
    immutable(output / f'{digest(result)}.json', result)
    print(json.dumps({k:v for k,v in result.items() if k != 'cases'}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args(); run(args.package, args.output)
