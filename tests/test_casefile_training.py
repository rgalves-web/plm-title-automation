"""Contracts of source identity, scope, review, blindness and accounting, not title."""
import json
from pathlib import Path

import pytest

from src.casefile import sessao, training, training_runtime, exame_vs3, vs3_entregaveis
from src.examinador.loop import TurnRecord
from tests.helpers_casefile import RepoFake, unit_de_teste, ClientRoteirizado, Msg, Texto


def card(tmp_path, rule_id='memo', project='Emirates', nature='methodology'):
    source = tmp_path / 'TRAINING SUITE.txt'
    source.write_text('royalty memorandum source text\n', encoding='utf-8')
    return dict(rule_id=rule_id, literal='royalty memorandum source text', interpretation='proposed method',
                nature=nature, scope=dict(project=[project], jurisdiction=['Texas'], substance=['oil and gas'],
                stage=['planning', 'examination'], work_type=['title']), conditions=['scope'], exceptions=['no default'],
                relations=[{'kind': 'conflicts', 'rule_id': 'other'}],
                sources=[dict(path=str(source), sha256=training.file_hash(source), locator='line:1',
                              quote='royalty memorandum source text')])


def setup(tmp_path, nature='methodology'):
    store = training.Store(tmp_path / 'store')
    c = store.put(card(tmp_path, nature=nature))
    release = store.publish([{'rule_id': c['rule_id'], 'version': c['version']}],
                            reviewer='synthetic reviewer', reason='fixture only', reviewed_at='2026-09-11')
    repo = RepoFake(); unit = unit_de_teste(repo, tmp_path / 'unit')
    scope = {k: v[0] for k, v in c['scope'].items()}
    repo.decisions.append(dict(id=1, unit_id=unit['id'], kind='training_scope', decided_at='2026-09-11',
                               answer=json.dumps({'release_id': release, 'scope': scope})))
    sid = repo.abrir_sessao(unit['id'], 'exame.vs3', 'fixture')
    return store, c, release, repo, unit, sid


def test_idempotent_versions_and_tampering(tmp_path):
    store = training.Store(tmp_path / 'store')
    payload = card(tmp_path); a = store.put(payload); b = store.put(payload)
    assert a['version'] == b['version']
    payload['interpretation'] = 'corrected proposal'
    new = store.put(payload)
    assert new['version'] != a['version']
    assert store.get(a['rule_id'], a['version']) == a
    (store.root / 'cards' / a['rule_id'] / f"{a['version']}.json").write_text('{}')
    with pytest.raises(ValueError, match='card_hash_mismatch'):
        store.get(a['rule_id'], a['version'])


@pytest.mark.parametrize('field,value,error', [('sha256', '0'*64, 'source_hash'),
                                               ('quote', 'fabricated quote', 'source_quote')])
def test_exact_source_required(tmp_path, field, value, error):
    payload = card(tmp_path); payload['sources'][0][field] = value
    with pytest.raises(ValueError, match=error):
        training.Store(tmp_path / 'store').put(payload)


@pytest.mark.parametrize('key,bad', [('project','Pearl'), ('jurisdiction','Arkansas'),
                                   ('substance','brine/lithium'), ('stage','administration'),
                                   ('work_type','payroll')])
def test_no_cross_scope_or_unknown_global(tmp_path, key, bad):
    c = card(tmp_path); context = {k:v[0] for k,v in c['scope'].items()}
    assert training.applicable(c, context)
    context[key] = bad
    assert not training.applicable(c, context)
    c['scope'][key] = []
    assert not training.applicable(c, context)


@pytest.mark.parametrize('nature', ['source_fragment', 'quiz', 'example', 'administrative'])
def test_non_operational_content_cannot_be_published(tmp_path, nature):
    store = training.Store(tmp_path/'store'); c = store.put(card(tmp_path, nature=nature))
    with pytest.raises(ValueError, match='non_operational'):
        store.publish([dict(rule_id=c['rule_id'], version=c['version'])],
                       reviewer='test', reason='test', reviewed_at='2026-09-11')


def test_inventory_idempotent_with_duplicates_media_and_snapshots(tmp_path):
    source = tmp_path/'source'; source.mkdir()
    (source/'TRAINING SUITE.txt').write_text('one fragment')
    (source/'TRAINING SUITE__copy.txt').write_text('one fragment')
    (source/'TRAINING SUITE__snapshot.txt').write_text('earlier version')
    (source/'TRAINING SUITE.png').write_bytes(b'image fixture')
    store = training.Store(tmp_path/'store')
    a, manifest = training.inventory(source, store)
    b, _ = training.inventory(source, store)
    assert a == b and len(list(store.cards())) == 1
    assert sum(bool(s['duplicate_of']) for s in manifest['sources']) == 1
    assert all(not s['coverage']['image_examined'] for s in manifest['sources'])
    assert all(not s['coverage']['knowledge_approved'] for s in manifest['sources'])


def test_offered_consulted_applied_and_version_pinning(tmp_path):
    store, c, release, repo, unit, sid = setup(tmp_path)
    text, tools, dispatch = training_runtime.prepare(repo, unit, sid, 'exame.vs3', store)
    assert release in text and len(tools) == 3
    result = dispatch['consultar_training']('royalty')
    assert result['cards'][0]['relations'] == c['relations']
    with pytest.raises(ValueError, match='version_not_offered'):
        dispatch['aplicar_training']('other', c['version'], 'reason', [], '', 'reviewer')
    with pytest.raises(ValueError, match='claim_outside_unit'):
        dispatch['aplicar_training'](c['rule_id'], c['version'], 'reason', [], '', 'reviewer', claim_id=999)
    dispatch['aplicar_training'](c['rule_id'], c['version'], 'reason', ['other'], 'missing OGL', 'reviewer')
    assert repo.knowledge_audit(unit['id'])['events'][-1]['detail']['lacuna'] == 'missing OGL'
    revised = card(tmp_path); revised['interpretation'] = 'changed'
    store.put(revised)
    sid2 = repo.abrir_sessao(unit['id'], 'exame.vs3', 'fixture')
    training_runtime.prepare(repo, unit, sid2, 'exame.vs3', store)
    current = repo.knowledge_audit(unit['id'])['contexts'][-1]['manifest']
    assert current['release_id'] == release and not current['release_changed']
    assert current['cards'][0]['version'] == c['version']


def test_criteria_population_never_disappears(tmp_path):
    store, c, _, repo, unit, sid = setup(tmp_path, 'review_criterion')
    _, _, dispatch = training_runtime.prepare(repo, unit, sid, 'exame.vs3', store)
    coverage = training_runtime.review_coverage(repo.knowledge_audit(unit['id']))[-1]
    assert coverage['missing'] == [c['rule_id']]
    dispatch['consultar_training']('memo')
    with pytest.raises(ValueError, match='review_evidence'):
        dispatch['revisar_training'](c['rule_id'], c['version'], 'atendido', [], 'reason', 'reviewer')
    dispatch['revisar_training'](c['rule_id'], c['version'], 'insuficiente', [], 'missing source', 'reviewer')
    coverage = training_runtime.review_coverage(repo.knowledge_audit(unit['id']))[-1]
    assert not coverage['missing'] and coverage['reviews'][0]['estado'] == 'insuficiente'


def test_unapproved_context_and_cross_unit_are_not_inherited(tmp_path):
    store, _, _, repo, unit, sid = setup(tmp_path)
    other = unit_de_teste(repo, tmp_path/'other', 'OTHER')
    sid2 = repo.abrir_sessao(other['id'], 'exame.vs3', 'fixture')
    text, _, dispatch = training_runtime.prepare(repo, other, sid2, 'exame.vs3', store)
    assert 'pending_operator' in text and dispatch['consultar_training']('royalty')['cards'] == []
    with pytest.raises(ValueError, match='session_outside_unit'):
        repo.knowledge_context(other['id'], sid, {})


@pytest.mark.parametrize('error', [RuntimeError, KeyboardInterrupt])
def test_interrupted_session_keeps_usage_and_closes(tmp_path, monkeypatch, error):
    repo = RepoFake(); unit = unit_de_teste(repo, tmp_path)
    def fail(**kwargs):
        kwargs['on_turn'](TurnRecord(1, '', [], {'entrada':1000, 'saida':100, 'custo_usd':.0075}))
        raise error('fixture interruption')
    monkeypatch.setattr(sessao, 'run_loop', fail)
    with pytest.raises(error):
        sessao.rodar(repo=repo, unit=unit, pasta=tmp_path, comando='exame.vs3', sistema='', task='',
                     ferramentas=[], dispatch={}, modelo_sessao='claude-opus-5', max_cost_usd=1)
    assert repo.sessions[-1]['ended_at'] and 'INTERROMPIDA' in repo.sessions[-1]['stop_reason']
    assert repo.custo_acumulado(unit['id']) == .0075
    assert repo.sessions[-1]['usage']['entrada'] == 1000


def test_real_loop_receives_context_only_on_examiner_paths(tmp_path, monkeypatch):
    repo = RepoFake(); unit = unit_de_teste(repo, tmp_path)
    client = ClientRoteirizado([[Texto('done')]])
    sessao.rodar(repo=repo, unit=unit, pasta=tmp_path, comando='planejar.examinador',
                sistema='', task='', ferramentas=[], dispatch={}, modelo_sessao='claude-opus-5',
                max_cost_usd=1, client=client)
    assert len(repo.knowledge_audit(unit['id'])['contexts']) == 1
    # A family-B-labelled session must not gain training tools or prior answers.
    def blind(**kwargs):
        assert 'TRAINING SUITE' not in kwargs['task']
        assert not kwargs['tools']
        raise RuntimeError('stop before model')
    monkeypatch.setattr(sessao, 'run_loop', blind)
    with pytest.raises(RuntimeError):
        sessao.rodar(repo=repo, unit=unit, pasta=tmp_path, comando='verificacao',
                    sistema='', task='blind evidence', ferramentas=[], dispatch={},
                    modelo_sessao='fixture', max_cost_usd=1)


def test_generic_task_has_no_josh_fixture(tmp_path):
    repo = RepoFake(); unit = unit_de_teste(repo, tmp_path)
    task = exame_vs3._task(repo, unit)
    for word in ('155', '80,02', 'BRA-DE', 'Stewart', '0220936', '67'):
        assert word not in task


def test_artifact_presence_does_not_certify_final(tmp_path):
    from tests.test_casefile_vs3 import _unit, _claim
    repo, unit, _ = _unit(tmp_path)
    cid = _claim(repo, unit, entidade='data de corte')
    repo.gravar_posicao(unit['id'], 'one', 'comprovada', [cid], '', 1)
    repo.registrar_deliverable(unit['id'], 'chain_graph_vs3', 1, 'graph', 'a'*64)
    assert vs3_entregaveis._lifecycle(repo, unit) == 'partial'


def test_legacy_search_reads_body_and_does_not_approve(tmp_path):
    (tmp_path/'arbitrary-slug.md').write_text('royalty memorandum', encoding='utf-8')
    result = training.legacy_candidates(tmp_path, 'royalty')
    assert result[0]['rule_id'] == 'arbitrary-slug'
    assert result[0]['status'] == 'legacy_unreviewed'


def test_path_traversal_rejected(tmp_path):
    with pytest.raises(ValueError, match='identifier'):
        training.Store(tmp_path).get('../escape', 'a'*64)


def test_received_response_accounted_before_tool_interrupt(tmp_path):
    from tests.helpers_casefile import Use
    repo = RepoFake(); unit = unit_de_teste(repo, tmp_path)
    def interrupt():
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        sessao.rodar(repo=repo, unit=unit, pasta=tmp_path, comando='fixture', sistema='', task='',
                    ferramentas=[], dispatch={'interrupt': interrupt}, modelo_sessao='claude-opus-5',
                    max_cost_usd=1, client=ClientRoteirizado([[Use('interrupt', {})]]))
    assert repo.sessions[-1]['usage']['entrada'] == 10
    assert repo.sessions[-1]['ended_at']
    assert repo.custo_acumulado(unit['id']) > 0


def test_release_change_and_withdrawal_are_visible(tmp_path):
    store, c, old, repo, unit, sid = setup(tmp_path)
    training_runtime.prepare(repo, unit, sid, 'exame.vs3', store)
    payload = card(tmp_path); payload['interpretation'] = 'revised'
    new = store.put(payload)
    rid = store.publish([dict(rule_id=new['rule_id'], version=new['version'])],
                        reviewer='test', reason='revision', reviewed_at='2026-09-12')
    config = json.loads(repo.decisions[0]['answer']); config['release_id'] = rid
    repo.decisions.append({**repo.decisions[0], 'id':2, 'answer': json.dumps(config)})
    sid2 = repo.abrir_sessao(unit['id'], 'exame.vs3', 'fixture')
    training_runtime.prepare(repo, unit, sid2, 'exame.vs3', store)
    contexts = repo.knowledge_audit(unit['id'])['contexts']
    assert contexts[-1]['manifest']['release_changed']
    assert contexts[0]['manifest']['cards'][0]['version'] == c['version']
    store.withdraw(rid, 'test', 'withdraw fixture', '2026-09-12')
    with pytest.raises(ValueError, match='withdrawn'):
        store.release(rid)
    assert repo.knowledge_audit(unit['id'])['contexts'][0] == contexts[0]


def test_legacy_same_slug_both_visible_and_write_is_candidate(tmp_path):
    from src.casefile.ferramentas import montar_dispatch
    from src.examinador.okf import KnowledgeBase
    repo = RepoFake(); unit = unit_de_teste(repo, tmp_path/'unit')
    local = KnowledgeBase(tmp_path/'local'); global_ = KnowledgeBase(tmp_path/'global')
    local.write('same', 'local rule'); global_.write('same', 'global rule')
    before = (local.root/'same.md').read_bytes()
    dispatch = montar_dispatch(acervo=None, repo=repo, unit=unit, pasta=tmp_path/'unit',
                                kb_unidade=local, kb_global=global_, ator='test', session_ref={'id':1})
    result = dispatch['read_knowledge']('same')
    assert len(result['versoes_relevantes']) == 2
    assert dispatch['write_knowledge']('same', 'changed', 'regra', 'unidade')['status'] == 'candidate'
    assert (local.root/'same.md').read_bytes() == before


def test_acceptance_is_bound_to_population_and_review_snapshot(tmp_path):
    from tests.test_casefile_vs3 import _claim
    store, c, _, repo, unit, sid = setup(tmp_path, 'review_criterion')
    _, _, dispatch = training_runtime.prepare(repo, unit, sid, 'exame.vs3', store)
    dispatch['consultar_training']('memo')
    dispatch['revisar_training'](c['rule_id'], c['version'], 'nao_aplicavel', [], 'fixture reason', 'reviewer')
    repo.registrar_source_file('a'*64, 1)
    cid = _claim(repo, unit, entidade='data de corte')
    repo.gravar_membro_populacao(unit['id'], 'leases', 'L1')
    repo.gravar_posicao(unit['id'], 'leases::L1', 'comprovada', [cid], '', sid)
    repo.registrar_deliverable(unit['id'], 'chain_graph_vs3', 1, 'graph', 'b'*64)
    status = vs3_entregaveis.completude(repo, unit)
    assert not status['missing']
    assert vs3_entregaveis._lifecycle(repo, unit) == 'partial'
    repo.decisions.append(dict(id=2, unit_id=unit['id'], kind='vs3_acceptance', decided_at='2026-09-11',
                               answer=json.dumps({'approved': True, 'snapshot': status['snapshot']})))
    assert vs3_entregaveis._lifecycle(repo, unit) == 'final'
    repo.gravar_membro_populacao(unit['id'], 'leases', 'L2')
    assert vs3_entregaveis._lifecycle(repo, unit) == 'partial'
    repo.gravar_membro_populacao(unit['id'], 'other_population', 'L1')
    assert 'population:other_population::L1' in vs3_entregaveis.completude(repo, unit)['missing']


def test_api_exposes_database_methodology(tmp_path):
    from src.casefile.api import unit_training
    store, c, _, repo, unit, sid = setup(tmp_path)
    _, _, dispatch = training_runtime.prepare(repo, unit, sid, 'exame.vs3', store)
    dispatch['aplicar_training'](c['rule_id'], c['version'], 'reason', [], 'gap', 'owner')
    got = unit_training(unit['id'], repo)
    assert got['contexts'][0]['manifest']['cards'][0]['sources']
    assert got['events'][-1]['detail']['responsavel'] == 'owner'


@pytest.mark.postgres
def test_postgres_context_and_event_roundtrip(tmp_path):
    from src.casefile.db import migrar
    from src.casefile.repo import Repo
    from tests.helpers_casefile import conectar_pg_ou_skip
    conn, schema = conectar_pg_ou_skip()
    try:
        migrar(conn); repo = Repo(conn); unit = unit_de_teste(repo, tmp_path)
        sid = repo.abrir_sessao(unit['id'], 'exame.vs3', 'fixture')
        repo.knowledge_context(unit['id'], sid, {'release_id': 'fixture'})
        repo.knowledge_context(unit['id'], sid, {'release_id': 'fixture'})
        with pytest.raises(ValueError, match='immutable'):
            repo.knowledge_context(unit['id'], sid, {'release_id': 'changed'})
        repo.knowledge_event(unit['id'], sid, 'queried', {'query': 'source'})
        assert len(repo.knowledge_audit(unit['id'])['contexts']) == 1
        assert repo.knowledge_audit(unit['id'])['events'][0]['detail']['query'] == 'source'
        with pytest.raises(ValueError, match='claim_outside'):
            repo.knowledge_event(unit['id'], sid, 'applied', {'claim_id':999})
        other = unit_de_teste(repo, tmp_path/'other', 'OTHER')
        with pytest.raises(Exception):
            repo.knowledge_event(other['id'], sid, 'queried', {})
        assert repo.knowledge_audit(other['id']) == {'contexts': [], 'events': []}
    finally:
        conn.execute(f'DROP SCHEMA "{schema}" CASCADE'); conn.close()
