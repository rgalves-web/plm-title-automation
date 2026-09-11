"""Bounded context and declared applications. No knowledge enters family B."""
import json
import re

from src.casefile.training import Store, applicable, digest


def _schema(name, description, properties, required):
    return {'name': name, 'description': description, 'input_schema': {
        'type': 'object', 'properties': properties, 'required': required}}


TOOLS = [
    _schema('consultar_training', 'Busca orientacao metodologica na publicacao fixada. '
            'Nao e evidencia documental. Explique condicoes, excecoes e conflitos.',
            {'assunto': {'type': 'string'}}, ['assunto']),
    _schema('aplicar_training', 'Declara uso de uma versao consultada, com motivo, '
            'conflitos, lacuna e responsavel. Nao substitui documento/pagina/trecho do claim.',
            {'rule_id': {'type': 'string'}, 'version': {'type': 'string'},
             'razao': {'type': 'string'}, 'conflitos': {'type': 'array', 'items': {'type': 'string'}},
             'lacuna': {'type': 'string'}, 'responsavel': {'type': 'string'},
             'claim_id': {'type': 'integer'}, 'research_id': {'type': 'integer'}},
            ['rule_id', 'version', 'razao', 'conflitos', 'lacuna', 'responsavel']),
    _schema('revisar_training', 'Registra criterio exigido com evidencias ou justificativa '
            'de insuficiencia/nao aplicabilidade. Julgamento do revisor, sem aceite automatico.',
            {'rule_id': {'type': 'string'}, 'version': {'type': 'string'},
             'estado': {'type': 'string', 'enum': ['atendido', 'falha', 'insuficiente', 'nao_aplicavel']},
             'claim_ids': {'type': 'array', 'items': {'type': 'integer'}},
             'razao': {'type': 'string'}, 'responsavel': {'type': 'string'}},
            ['rule_id', 'version', 'estado', 'claim_ids', 'razao', 'responsavel'])]


def prepare(repo, unit, sid, command, store=None):
    uid = unit['id']
    # Only an answered, explicit operator decision enables a publication.
    decisions = [d for d in repo.decisoes_da_unit(uid)
                 if d.get('kind') == 'training_scope' and d.get('answer') and d.get('decided_at')]
    decision = decisions[-1] if decisions else None
    old = repo.knowledge_audit(uid)['contexts']
    previous = next((c['manifest'] for c in reversed(old)
                     if c['manifest'].get('command') == command), None)
    cards, release, scope, approval = [], None, {}, None
    if decision:
        config = json.loads(decision['answer'])
        from src.casefile.training import ROOT
        store = store or Store(config.get('store_root', ROOT))
        release, scope = config['release_id'], dict(config['scope'])
        # Stage is the actual session stage, not inherited from a prior command.
        scope['stage'] = {'planejar.examinador': 'planning', 'exame.vs3': 'examination'}[command]
        approval, all_cards = store.release(release)
        cards = [c for c in all_cards if applicable(c, scope)]
    criteria = [c['rule_id'] for c in cards if c['nature'] == 'review_criterion']
    manifest = {'release_id': release, 'release_approval': approval, 'scope': scope, 'command': command,
                'decision_id': decision['id'] if decision else None, 'cards': cards,
                'expected_criteria': criteria, 'previous_release': previous.get('release_id') if previous else None,
                'release_changed': bool(previous and previous.get('release_id') != release),
                'status': 'configured' if decision else 'pending_operator_scope_and_release'}
    repo.knowledge_context(uid, sid, manifest)
    offered = set()

    def event(kind, detail):
        repo.knowledge_event(uid, sid, kind, detail)

    def offer(found):
        bounded, size = [], 0
        for c in found:
            length = len(json.dumps(c, ensure_ascii=False))
            if size + length > 24000:
                break
            size += length
            bounded.append(c)
        for c in bounded:
            offered.add((c['rule_id'], c['version']))
        event('offered', {'versions': [{'rule_id': c['rule_id'], 'version': c['version']} for c in bounded],
                          'omitted_by_context_budget': len(found) - len(bounded)})
        return bounded

    def consult(assunto):
        terms = set(re.findall(r'\w+', assunto.casefold()))
        scored = [(len(terms & set(re.findall(r'\w+', (c['rule_id'] + ' ' + c['literal'] + ' ' + c['interpretation']).casefold()))), c)
                  for c in cards]
        found = [c for n, c in sorted(scored, key=lambda x: (-x[0], x[1]['rule_id'])) if n][:8]
        supplied = offer(found)
        event('queried', {'query': assunto, 'matched_count': len(found), 'result_count': len(supplied)})
        return {'release_id': release, 'cards': supplied,
                'publication_approved': approval is not None,
                'omitted_by_context_budget': len(found) - len(supplied), 'methodology_only': True}

    def checked(rule_id, version):
        if (rule_id, version) not in offered:
            raise ValueError('version_not_offered_in_session')
        return next(c for c in cards if c['rule_id'] == rule_id and c['version'] == version)

    def apply(rule_id, version, razao, conflitos, lacuna, responsavel, claim_id=None, research_id=None):
        checked(rule_id, version)
        if not razao.strip() or not responsavel.strip():
            raise ValueError('reason_and_owner_required')
        detail = dict(rule_id=rule_id, version=version, razao=razao, conflitos=conflitos,
                      lacuna=lacuna, responsavel=responsavel, claim_id=claim_id, research_id=research_id)
        event('applied', detail)
        return {'registered': True, 'methodology_only': True}

    def review(rule_id, version, estado, claim_ids, razao, responsavel):
        c = checked(rule_id, version)
        if c['nature'] != 'review_criterion' or rule_id not in criteria:
            raise ValueError('criterion_not_expected')
        if estado not in ('atendido', 'falha', 'insuficiente', 'nao_aplicavel'):
            raise ValueError('invalid_review_state')
        if not razao.strip() or not responsavel.strip() or (estado in ('atendido', 'falha') and not claim_ids):
            raise ValueError('review_evidence_or_reason_required')
        if any(not repo.claim_existe(uid, cid) for cid in claim_ids):
            raise ValueError('claim_outside_unit')
        event('reviewed', dict(rule_id=rule_id, version=version, estado=estado,
                              claim_ids=claim_ids, razao=razao, responsavel=responsavel))
        return {'registered': True, 'operator_approval': False}

    initial = offer([c for c in cards if c['nature'] != 'review_criterion'][:4])
    context = '\n\nTRAINING SUITE — somente metodologia, nunca prova da unit. '
    context += 'Consulte por assunto; declare uso e conflitos com aplicar_training. '
    context += 'Revise TODOS os criterios exigidos, inclusive insuficientes e nao aplicaveis. '
    context += 'Exemplos/quizzes nao integram este contexto. Condicoes exigem julgamento.\n'
    context += 'O status candidate nos bytes da ficha e historico; o aceite esta na publicacao fixada.\n'
    context += json.dumps({'status': manifest['status'], 'release_id': release,
                           'publication_approved': approval is not None,
                           'release_changed': manifest['release_changed'],
                           'scope': scope, 'criteria': criteria, 'offered': initial}, ensure_ascii=False)
    return context, TOOLS, {'consultar_training': consult, 'aplicar_training': apply,
                           'revisar_training': review}


def review_coverage(audit):
    """Coverage is records present, not correctness or acceptance of title."""
    out = []
    for ctx in audit['contexts']:
        expected = ctx['manifest'].get('expected_criteria', [])
        reviews = {e['detail']['rule_id']: e['detail'] for e in audit['events']
                   if e['session_id'] == ctx['session_id'] and e['kind'] == 'reviewed'}
        out.append({'session_id': ctx['session_id'], 'expected': expected,
                    'missing': [r for r in expected if r not in reviews],
                    'reviews': list(reviews.values())})
    return out
