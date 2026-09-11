"""Build the local review package. Exact-source excerpts, no automatic promotion.

Run: python -m src.casefile.training_package SOURCE_ROOT [--store PATH]
Every source is inventoried; unresolved topics remain explicitly pending.
"""
import argparse
import json
import re
from pathlib import Path

from src.casefile.training import (ROOT, SCOPE_KEYS, Store, digest, file_hash,
                                    immutable, inventory, legacy_candidates)


# Proposed adaptations of inspected sections, not executable title rules.
# Scope '*' here is an explicit proposed general applicability, never a fallback
# for missing metadata. Publication still requires an operator review.
SPECS = [
    ('scope-certification', '## A. Title Work', 'Title Opinion coverage; scope; certification; liens e curative',
     'Confirmar client/seller, territorio, substancia, depths, periodo e limites; distinguir certification da data da carta. Registrar requisitos e documentos de atendimento.', '*', '*', 'oil and gas', 'bpm-plm-due-diligence-leasehold-escopo'),
    ('full-lease-fields', '## B. Oil and Gas Lease Review', 'Full OGL, memorandum e campos pendentes',
     'Solicitar o instrumento/termo nao demonstrado, mantendo cada campo sem prova como lacuna com responsavel. Revisar effective date, term, extensions, royalty, depths e Pugh.', '*', '*', 'oil and gas', 'manual-9-3-lease-review'),
    ('hbp-production', '## C. HBP Analysis', 'HBP, production, cessation, Pugh e shut-in evidence',
     'Reunir production history dos wells e evidencias de pagamento pertinentes. O modelo explica o efeito no periodo e no lease, sem tratar cadastro como production.', '*', '*', 'oil and gas', 'bpm-plm-due-diligence-leasehold-escopo'),
    ('backward-forward', '### Backward e forward indexing', 'Backward/forward, acreage splits, outsales, fracoes',
     'Pedir deed into cada grantor e deeds out de cada grantee, com ramos, severances e limites de pesquisa; distinguir fracao dos 8/8 da fracao do grantor.', '*', '*', 'oil and gas', None),
    ('runsheet-completeness', '### Checklist de conclusão', 'Runsheet, anexos e cobertura da cadeia',
     'Revisar quem transferiu quanto, de que, para quem e quando; vincular instrumentos e paginas. Nenhuma contagem de fichas comprova title.', '*', '*', 'oil and gas', None),
    ('indexing', '## Lição 1 Practical Indexing Guide', 'Indices, nomes, book/page, pesquisa negativa e cobertura',
     'Preparar receita para o portal aplicavel, ambos os indices e variacoes. Registrar intervalo, termos e cobertura online/offline, sem concluir ausencia absoluta por zero hits.', '*', '*', '*', None),
    ('reservation-ohio', '## Two Main Types of Mineral Language You’ll See', 'Nova reservation versus referencia anterior',
     'Distinguir nova severance de referencia; pedir o deed citado e seguir o ramo mineral. Material do curso de Ohio, sem exportar sua orientacao juridica para Texas.', '*', 'Ohio', 'oil and gas', None),
    ('reservation-reading', '## How to Identify Mineral Reservation Language in a Deed', 'Deed completo e limitacoes de summaries',
     'Examinar a linguagem integral e declarar ambiguidade; silencio sobre minerais nao basta para provar propriedade.', '*', 'Ohio', 'oil and gas', None),
    ('npri-fixed-floating', '## Fixed e floating NPRIs', 'NPRI fixed/floating e base da royalty',
     'Identificar base, instrumento e clausulas; harmonizar four corners. Clear fixed language e ambiguidades permanecem visiveis.', '*', 'Texas', 'oil and gas', None),
    ('npri-ambiguity', '## Regra operacional da PLM', 'Float it and note it: ressalva e clear fixed language',
     'Registrar hipotese e justificativa como interpretacao, nunca converter ambiguidade em fato definitivo; vincular a ficha fixed/floating.', '*', 'Texas', 'oil and gas', None),
    ('pearl-royalty', '## Ownership Tab: regras específicas do Pearl DD', 'Pearl: Sliding Scale, Arkansas, brine/lithium',
     'Instrucoes exclusivas do Pearl; nao preencher royalty ou aplicar 1955 em Emirates. Qualquer interpretacao juridica permanece datada e sujeita a revisao.', 'Pearl', 'Arkansas', 'brine/lithium', None),
    ('pearl-certification', '## PLM Title Review', 'Pearl: certification e backdating especifico',
     'Manter as datas e convencao da fonte exclusivamente no perfil Pearl; nao criar formula universal.', 'Pearl', 'Arkansas', 'brine/lithium', None),
    ('cortez-scope', '## 1. Project Scope Analysis — prioridade do escopo específico', 'Cortez: exemplo de alcance ate 1859',
     'Preservar a instrucao de escopo do exemplo Cortez. O PM define inicio, fontes, entregas e limites; 1859 nao e prazo universal.', 'Cortez', 'Ohio', 'oil and gas', None),
    ('prep-review', '## Relação entre critérios e descrições', 'PREP: clarity, organization, documents, excellence',
     'Registrar revisao com fonte e ressalva. Avaliacao proposta nao constitui title determination nem aceite oficial.', '*', '*', '*', None),
    ('sme-escalation', '## How to Ask an SME — Structured SME Communication', 'Pergunta estruturada ao SME',
     'Preparar problema, avaliacao inicial, verificacao feita e pedido especifico. Nao enviar comunicacao automaticamente.', '*', '*', '*', None),
    ('lease-status-evidence', '## Lease Status Check — transcrição estruturada do decision tree', 'Term, releases por WI owner, producao e Pugh',
     'Usar como roteiro de evidencias: cada current WI owner, primary/amended/extended term, quaisquer lands do lease e Pugh. Outras clausulas e o project scope podem alterar o resultado; nao executar a arvore como regra Python.', '*', '*', 'oil and gas', None),
    ('ownership-dimensions', '## 2. Run title back', 'Mineral estate, executive, bonus, rentals, royalty, depths e wellbore',
     'Preservar cada dimensao e fracao, sem condensar em percentual unico. O client pode limitar owners; declarar exclusoes. Rastrear ambos os lados da severance.', '*', '*', 'oil and gas', None),
    ('assignments-curative', '## 3. Run title forward', 'Assignments, outsales, liens e curative',
     'Confirmar alcance de active/expired leases com PM; seguir transferencias e encargos com instrumento, responsavel e prova de atendimento.', '*', '*', 'oil and gas', None),
    ('gis-descriptions', '## Deed Plot Folder e GIS', 'Legal descriptions, parent tract, acreage e GIS',
     'Relacionar descricoes e mudancas de acreage por fonte; solicitar GIS quando necessario. Coincidencia numerica ou de nomes nao prova amarracao.', '*', '*', '*', None),
]


def section(lines, header):
    start = next(i for i, line in enumerate(lines) if line.strip() == header)
    level = len(header) - len(header.lstrip('#'))
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r'^#{1,' + str(level) + r'} ', lines[i])), len(lines))
    return start, end, '\n'.join(lines[start:end]).rstrip()


def build(source_root, store= None):
    store = store or Store()
    root = Path(source_root).resolve()
    mid, manifest = inventory(root, store)
    src = root / 'TRAINING SUITE__ACRESCIMOS.md'
    lines = src.read_text('utf-8-sig').splitlines()
    sha = file_hash(src)
    refs, curated = [], []
    for rid, header, topic, interpretation, project, jurisdiction, substance, legacy in SPECS:
        start, end, literal = section(lines, header)
        course = next((line.lstrip('# ') for line in reversed(lines[:start]) if line.startswith('# ')), None)
        source_date = {'pearl-royalty':'2025-03-06', 'pearl-certification':'2025-03-06',
                       'prep-review':'2026-05-26', 'indexing':'2026-06-12',
                       'reservation-ohio':'2026-07-09', 'reservation-reading':'2026-07-09'}.get(rid)
        card = store.put({'rule_id': rid, 'literal': literal, 'interpretation': interpretation,
            'source_date': source_date, 'effective_date': None,
            'topic': topic, 'nature': 'project_instruction' if project != '*' else 'methodology', 'author': 'Codex: proposed adaptation',
            'scope': dict(project=[project], jurisdiction=[jurisdiction], substance=[substance],
                          stage=['planning', 'examination', 'collection', 'review'], work_type=['title', 'due_diligence']),
            'conditions': ['Aplicar somente no escopo acordado com o client/PM e apos revisao explicita.'],
            'exceptions': ['Treinamento nao substitui instrumento, evidencia ou revisao juridica atual.', interpretation],
            'relations': ([{'kind': 'complements', 'rule_id': legacy}] if legacy else []) +
                ([{'kind': 'scope_conflict', 'rule_id': 'emirates-memo', 'condition': 'different project'}] if rid == 'pearl-royalty' else []) +
                ([{'kind': 'scope_conflict', 'rule_id': 'scope-certification', 'condition': 'different project scope'}] if rid in ('pearl-certification', 'cortez-scope') else []) +
                ([{'kind': 'complements', 'rule_id': 'npri-fixed-floating'}] if rid == 'npri-ambiguity' else []),
            'sources': [{'path': str(src), 'sha256': sha, 'locator': f'lines:{start+1}-{end}',
                         'course': course, 'lesson': header.lstrip('# '), 'quote': literal}]})
        refs.append({'rule_id': rid, 'version': card['version']})
        curated.append({'topic': topic, 'source_heading': header, 'rule_id': rid, 'destination': 'complements' if legacy else 'new',
                        'legacy': legacy, 'review_status': 'proposed'})
    legacy_path = Path(__file__).resolve().parents[2] / 'knowledge_okf' / 'manual-9-3-lease-review.md'
    legacy_text = legacy_path.read_text('utf-8').rstrip()
    c = store.put({'rule_id': 'emirates-memo', 'literal': legacy_text,
        'interpretation': 'Reconciliacao com a ficha existente: MEMO_ONLY comprova apenas campos demonstrados; '
                          'royalty ausente continua em branco com pedido do full OGL. Nao usar Sliding Scale de Pearl.',
        'nature': 'project_instruction', 'scope': dict(project=['Emirates'], jurisdiction=['Texas'],
        substance=['oil and gas'], stage=['planning', 'examination', 'collection', 'review'], work_type=['title', 'due_diligence']),
        'conditions': ['Project Emirates; confirmacao do escopo pelo operador.'],
        'exceptions': ['Sem aprovacao retroativa do legado; proposta exige revisao.'],
        'relations': [{'kind': 'complements', 'rule_id': 'manual-9-3-lease-review'},
                      {'kind': 'scope_conflict', 'rule_id': 'pearl-royalty', 'condition': 'different project'}],
        'sources': [dict(path=str(legacy_path), sha256=file_hash(legacy_path), locator='whole-card', quote=legacy_text)]})
    refs.append({'rule_id': c['rule_id'], 'version': c['version']})
    base_src = root / 'TRAINING SUITE__texto_extraido_da_base.txt'
    base_lines = base_src.read_text('utf-8-sig').splitlines()
    start = base_lines.index('What is a Title Opinion?')
    end = base_lines.index('Lesson 2 of 2', start)
    base_literal = '\n'.join(base_lines[start:end]).rstrip()
    c = store.put({'rule_id': 'title-opinion-coverage', 'literal': base_literal,
        'interpretation': 'Separar legal description/depths, materiais examinados, certification date, '
                          'ownership por dimensao, lease analysis, assignments, unreleased leases e requirements. '
                          'TO e metodologia diferentes: este curso nao prova fatos de uma unit.',
        'nature': 'methodology', 'scope': dict(project=['*'], jurisdiction=['*'], substance=['oil and gas'],
        stage=['planning', 'examination', 'collection', 'review'], work_type=['title', 'due_diligence']),
        'conditions': ['Usar a opinion aplicavel segundo escopo e evidencias do caso.'],
        'exceptions': ['Nao usar exemplos de opinions da lesson seguinte como fatos de unidades.'],
        'relations': [{'kind': 'complements', 'rule_id': 'scope-certification'}],
        'sources': [dict(path=str(base_src), sha256=file_hash(base_src), locator=f'lines:{start+1}-{end}',
                         course='What is a Title Opinion?', lesson='Definition and Explanation', quote=base_literal)]})
    refs.append({'rule_id': c['rule_id'], 'version': c['version']})
    criteria_src = root / 'TRAINING SUITE__Title_Abstracting_Expectations__2026-09-09.md'
    for n, line in enumerate(criteria_src.read_text('utf-8-sig').splitlines(), 1):
        m = re.match(r'^([ACDFIL]\d+):\s*(.+)', line)
        if not m:
            continue
        rid = 'tae-' + m[1]
        c = store.put({'rule_id': rid, 'literal': line.rstrip(), 'interpretation':
            'Revisor declara atendido, falha, insuficiente ou nao aplicavel, com evidencia e justificativa. '
            + ('I3 nao libera documentos unrecorded para Runsheet Emirates; respeitar destino do projeto.' if m[1] == 'I3' else ''),
            'nature': 'review_criterion', 'scope': dict(project=['*'], jurisdiction=['*'], substance=['*'],
            stage=['review', 'examination'], work_type=['title', 'due_diligence']),
            'conditions': ['Revisar com o escopo do projeto; nao aplicavel exige justificativa.'],
            'exceptions': ['O material salta F9; nao inventar criterio nem aceite oficial.'],
            'relations': [], 'sources': [{'path': str(criteria_src), 'sha256': file_hash(criteria_src),
                           'locator': f'line:{n}', 'quote': line.rstrip()}]})
        refs.append({'rule_id': rid, 'version': c['version']})
    # All sections receive a destination, including unreviewed/admin/examples.
    reconciliation = []
    kb = Path(__file__).resolve().parents[2] / 'knowledge_okf'
    for source in manifest['sources']:
        path = Path(source['path'])
        if not source['coverage']['text_extracted'] or source['snapshot']:
            reconciliation.append({'source': source['relative_path'], 'destination': source['destination'],
                                   'reason': 'source retained; no semantic approval inferred'})
            continue
        if path.suffix.lower() == '.md':
            topics = [(n, l) for n, l in enumerate(path.read_text('utf-8-sig').splitlines(), 1) if l.startswith('#')]
        else:
            topics = [(None, path.stem)]
        for n, topic in topics:
            matching = [c for c in curated if c['source_heading'].casefold() == topic.casefold()]
            destination = ('administrative' if any(w in topic.lower() for w in
                            ('landboss', 'slack', 'paychex', 'survey', 'gmail', 'meet', 'timesheet'))
                           else (matching[0]['destination'] if matching else 'coverage_pending'))
            reconciliation.append({'source': source['relative_path'], 'line': n, 'topic': topic,
                                   'destination': destination, 'semantic_review': 'pending',
                                   'lexical_candidates_not_equivalence': legacy_candidates(kb, topic),
                                   'curated': matching})
        # Every fragment is accounted for, including lessons inside the base Word
        # and TXT that do not use Markdown headings. No theme silently vanishes.
        for fragment in source['fragments']:
            fragment_card = store.get(**fragment)
            reconciliation.append({'source': source['relative_path'],
                'locator': fragment_card['sources'][0]['locator'], 'fragment': fragment,
                'topic_hint': fragment_card['literal'].splitlines()[0][:160],
                'destination': 'coverage_pending', 'semantic_review': 'pending',
                'reason': 'Text addressable; semantic reconciliation not certified by lexical matching.'})
    package = {'inventory_id': mid, 'refs': refs, 'curated_reconciliation': curated,
               'source_topic_reconciliation': reconciliation,
               'status': 'candidate_package_requires_review',
               'limitations': ['Media not comprehensively examined.', 'LMS status is not content approval.',
                               'Uncurated source fragments are searchable locally but not released to models.',
                               'No real-model quality measurement or operational-unit modification.']}
    pid = digest(package)
    immutable(store.root / 'packages' / f'{pid}.json', package)
    summary = {'package_id': pid, 'inventory_id': mid, 'sources': len(manifest['sources']),
               'duplicate_sources': sum(bool(s['duplicate_of']) for s in manifest['sources']),
               'text_sources': sum(s['coverage']['text_extracted'] for s in manifest['sources']),
               'candidate_cards': len(refs), 'criteria': sum(r['rule_id'].startswith('tae-') for r in refs),
               'fragments': sum(len(s['fragments']) for s in manifest['sources']),
               'reconciliation_rows': len(reconciliation), 'approved_cards': 0}
    immutable(store.root / 'reports' / f'{pid}.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root', type=Path)
    parser.add_argument('--store', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(build(args.source_root, Store(args.store)), indent=2))
