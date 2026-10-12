import hashlib
from pathlib import Path

import pytest

from src.casefile import project_profile, surface_evidence
from tests.test_casefile_project_profile import setup


def fixture_round(tmp_path):
    repo, unit, profile = setup(tmp_path)
    project_profile.configure(repo, unit, profile, 'fixture', 'test')
    root = Path(profile['project_root'])
    doc = root / 'capture.pdf'
    doc.write_bytes(b'synthetic capture bytes')
    image = root / 'page.png'
    image.write_bytes(b'synthetic image bytes')
    payload = dict(schema=1, status='WORKING DRAFT', round_id='synthetic-1',
                   analyst='test-analyst', observed_at='2026-01-01', cost_usd=0,
                   project_root=str(root), units=[dict(id=unit['id'], canonical_name=unit['canonical_name'])],
                   documents=[dict(instrument='synthetic-document', path=str(doc),
                       sha256=hashlib.sha256(doc.read_bytes()).hexdigest(),
                       source_url='https://example.invalid/synthetic',
                       preview_page_count=1, captured_pages=[1],
                       capture_status='preview_captured', completeness_note='synthetic only',
                       images=[dict(path=str(image), source_page=1,
                                    sha256=hashlib.sha256(image.read_bytes()).hexdigest())],
                       allocations={str(unit['id']):dict(status='pending', reason='synthetic gap')},
                       observations=[dict(source_page=1, page='1', quote='synthetic quote', note='test')])],
                   gaps=[dict(title='synthetic gap', what='synthetic', where='fixture',
                              method='manual', owner='analyst')], searches=[])
    return repo, unit, payload


def test_surface_round_stages_once_without_promotion_or_state_change(tmp_path):
    repo, unit, payload = fixture_round(tmp_path)
    result = surface_evidence.import_round(repo, payload)
    assert result['status'] == 'staged'
    assert repo.estado_da_unit(unit['id']) == 'INDICADA'
    assert len(repo.collection_items(unit['id'])) == 1
    assert repo.collection_items(unit['id'])[0]['status'] == 'staged'
    assert repo.contagem_pesquisas(unit['id']) == 1
    assert repo.sha_por_nome(unit['id']) == {}
    assert surface_evidence.import_round(repo, payload)['status'] == 'already_imported'
    assert repo.contagem_pesquisas(unit['id']) == 1


def test_surface_dry_run_has_no_writes(tmp_path):
    repo, unit, payload = fixture_round(tmp_path)
    assert surface_evidence.import_round(repo, payload, dry_run=True)['status'] == 'validated'
    assert repo.collection_items(unit['id']) == []
    assert repo.contagem_pesquisas(unit['id']) == 0


@pytest.mark.parametrize('mutation,error', [
    (lambda p: p.update(cost_usd=1), 'zero_cost'),
    (lambda p: p.update(status='FINAL'), 'schema_or_status'),
    (lambda p: p['units'][0].update(canonical_name='other'), 'identity_mismatch'),
    (lambda p: p['documents'][0].update(captured_pages=[]), 'manifest_incomplete'),
    (lambda p: p['documents'][0].update(images=[]), 'images_missing'),
    (lambda p: p['documents'][0].update(sha256='0'*64), 'source_changed'),
    (lambda p: p['documents'][0].update(allocations={}), 'allocation_required'),
    (lambda p: p['documents'][0]['observations'][0].update(source_page=2), 'outside_capture'),
])
def test_surface_invalid_round_writes_nothing(tmp_path, mutation, error):
    repo, unit, payload = fixture_round(tmp_path)
    mutation(payload)
    with pytest.raises(ValueError, match=error):
        surface_evidence.import_round(repo, payload)
    assert repo.collection_items(unit['id']) == []


def test_surface_changed_image_and_outside_path_rejected(tmp_path):
    repo, unit, payload = fixture_round(tmp_path)
    im = payload['documents'][0]['images'][0]
    Path(im['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='source_changed'):
        surface_evidence.import_round(repo, payload)
    im['path'] = str(tmp_path / 'outside.png')
    with pytest.raises(ValueError, match='outside_project'):
        surface_evidence.import_round(repo, payload)


def test_surface_allocation_needs_citation_and_round_conflict_is_explicit(tmp_path):
    repo, unit, payload = fixture_round(tmp_path)
    allocation = payload['documents'][0]['allocations'][str(unit['id'])]
    allocation['status'] = 'applicable'
    with pytest.raises(ValueError, match='legal_description_source'):
        surface_evidence.import_round(repo, payload)
    allocation['status'] = 'pending'
    surface_evidence.import_round(repo, payload)
    payload['analyst'] = 'different'
    with pytest.raises(ValueError, match='round_conflict'):
        surface_evidence.import_round(repo, payload)


def test_surface_explicit_profile_required(tmp_path):
    repo, unit, payload = fixture_round(tmp_path)
    repo.registrar_politica(unit['id'], 'project_profile', '')
    with pytest.raises(ValueError, match='explicit_profile_required'):
        surface_evidence.import_round(repo, payload)
