"""Offline surface evidence intake. Stores analyst observations; never judges title.

This path accepts captured documents and research gaps without entering the
Emirates collectors, calling models, promoting files or changing case state.
Unallocated documents remain staged in each explicitly named case. They are
not global file sightings and cannot silently become evidence for other units.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.casefile import project_profile


def _required(row, fields):
    for field in fields:
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError('surface_field_required:' + field)


def _file(root, item):
    _required(item, ('path', 'sha256'))
    path = Path(item['path']).resolve()
    if not path.is_relative_to(root):
        raise ValueError('surface_source_outside_project')
    if '1. landman submitted' in [p.lower() for p in path.parts]:
        raise ValueError('surface_intake_requires_control_source')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != item['sha256']:
        raise ValueError('surface_source_changed:' + path.name)
    return len(data)


def validate_round(repo, payload):
    if payload.get('schema') != 1 or payload.get('status') != 'WORKING DRAFT':
        raise ValueError('surface_round_schema_or_status')
    _required(payload, ('round_id', 'analyst', 'observed_at', 'project_root'))
    if payload.get('cost_usd') != 0:
        raise ValueError('surface_offline_zero_cost_only')
    root = Path(payload['project_root']).resolve()
    requested = payload.get('units', [])
    if not requested or len({r['id'] for r in requested}) != len(requested):
        raise ValueError('surface_units_required_unique')
    units = {u['id']: u for u in repo.listar_units()}
    for requested_unit in requested:
        unit = units.get(requested_unit['id'])
        if not unit or unit['canonical_name'] != requested_unit['canonical_name']:
            raise ValueError('surface_unit_identity_mismatch')
        profile = project_profile.selected(repo, unit)
        if not profile or Path(profile['project_root']).resolve() != root:
            raise ValueError('surface_explicit_profile_required')
    documents = payload.get('documents', [])
    if not documents or len({d['instrument'] for d in documents}) != len(documents):
        raise ValueError('surface_documents_required_unique')
    sizes = {}
    for doc in documents:
        _required(doc, ('instrument', 'source_url', 'capture_status', 'completeness_note'))
        sizes[doc['instrument']] = _file(root, doc)
        pages = doc.get('captured_pages', [])
        count = doc.get('preview_page_count')
        if not isinstance(count, int) or count < 1 or pages != list(range(1, count + 1)):
            raise ValueError('surface_preview_page_manifest_incomplete')
        images = doc.get('images', [])
        if {im.get('source_page') for im in images} != set(pages):
            raise ValueError('surface_page_images_missing')
        for im in images:
            _file(root, im)
        allocations = doc.get('allocations', {})
        if set(allocations) != {str(u['id']) for u in requested}:
            raise ValueError('surface_allocation_required_per_unit')
        for allocation in allocations.values():
            _required(allocation, ('status', 'reason'))
            if allocation['status'] not in ('pending', 'applicable', 'not_applicable'):
                raise ValueError('surface_allocation_status')
            if allocation['status'] != 'pending':
                _required(allocation, ('legal_description_source', 'page', 'quote', 'reviewer'))
        for observation in doc.get('observations', []):
            _required(observation, ('page', 'quote', 'note'))
            if observation.get('source_page') not in pages:
                raise ValueError('surface_citation_page_outside_capture')
    for gap in payload.get('gaps', []):
        _required(gap, ('title', 'what', 'where', 'method', 'owner'))
    for search in payload.get('searches', []):
        _required(search, ('target', 'scope', 'source_url', 'observed_at'))
        if not isinstance(search.get('terms'), list) or not search['terms']:
            raise ValueError('surface_search_terms_required')
        if not isinstance(search.get('names_scanned'), int) or search['names_scanned'] < 0:
            raise ValueError('surface_search_count_required')
        if not isinstance(search.get('hits'), list):
            raise ValueError('surface_search_hits_required')
    return sizes


def import_round(repo, payload, *, dry_run=False):
    """Caller provides one DB transaction for the complete round."""
    sizes = validate_round(repo, payload)  # check every source before any write
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    key = 'surface_round:' + payload['round_id']
    previous = [repo.politica(u['id'], key) for u in payload['units']]
    if any(previous):
        if not all(p and json.loads(p)['sha256'] == digest for p in previous):
            raise ValueError('surface_round_conflict')
        return dict(status='already_imported', sha256=digest, units=len(previous))
    result = dict(status='validated' if dry_run else 'staged', sha256=digest,
                  units=len(payload['units']), documents=len(payload['documents']),
                  gaps_per_unit=len(payload.get('gaps', [])), cost_usd=0,
                  promoted=False, title_approved=False, case_state_changed=False)
    if dry_run:
        return result
    for unit in payload['units']:
        uid = unit['id']
        session = repo.abrir_sessao(uid, 'surface-evidence', payload['analyst'])
        for doc in payload['documents']:
            repo.registrar_source_file(doc['sha256'], sizes[doc['instrument']])
            item = repo.criar_collection_item(
                uid, 'surface:' + payload['round_id'] + ':' + doc['instrument'],
                'manual_preview', {'instrument': doc['instrument'], 'source_url': doc['source_url']})
            repo.atualizar_collection_item(
                item, status='staged', staged_path=doc['path'], sha256=doc['sha256'],
                provenance=dict(doc, allocation=doc['allocations'][str(uid)],
                                analyst=payload['analyst'], observed_at=payload['observed_at']),
                cost_usd=0, note='WORKING DRAFT; analyst observations; no promotion or title approval')
        for gap in payload.get('gaps', []):
            repo.inserir_pesquisa(uid, gap['title'], gap['what'], gap['where'],
                                  gap['method'] + '; owner=' + gap['owner'], session, [])
        for search in payload.get('searches', []):
            repo.registrar_busca(uid, search['target'], search['terms'],
                                  json.dumps(search, ensure_ascii=False),
                                  search['names_scanned'], search['hits'])
        repo.registrar_politica(uid, key, json.dumps(dict(result, round=payload), ensure_ascii=False))
        repo.fechar_sessao(session, 'offline_evidence_staged', 0, {}, 0, '')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    payload = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    from src.casefile.db import connect
    from src.casefile.repo import Repo
    with connect() as conn:
        with conn.transaction():
            result = import_round(Repo(conn), payload, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
