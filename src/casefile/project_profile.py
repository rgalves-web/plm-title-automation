"""Explicit, source-checked planning profiles. No title judgments or model calls."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def validate(profile, unit=None):
    if profile.get('schema') != 1 or profile.get('work_type') != 'surface_title':
        raise ValueError('unsupported_project_profile')
    for key in ('name', 'project_root', 'planning_system', 'planning_task'):
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            raise ValueError('profile_field_required:' + key)
    root = Path(profile['project_root']).resolve()
    if unit:
        folder = Path(unit['folder_path']).resolve()
        if folder == root or not folder.is_relative_to(root):
            raise ValueError('profile_outside_project')
    if not profile.get('sources'):
        raise ValueError('profile_sources_required')
    for source in profile['sources']:
        path = Path(source['path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('profile_source_outside_project')
        if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('profile_source_changed')
    return profile


def selected(repo, unit):
    raw = repo.politica(unit['id'], 'project_profile')
    return validate(json.loads(raw), unit) if raw else None


def configure(repo, unit, profile, reviewer, reason):
    if not reviewer.strip() or not reason.strip():
        raise ValueError('profile_decision_required')
    validate(profile, unit)
    snapshot = dict(profile, configured_by=reviewer, configuration_reason=reason)
    repo.registrar_politica(unit['id'], 'project_profile', json.dumps(snapshot, ensure_ascii=False))


def planning_task(repo, unit, summary, profile):
    return '\n\n'.join([
        'CASE FILE: ' + unit['canonical_name'],
        'CENSO: ' + json.dumps(summary, ensure_ascii=False, default=str),
        'DOCUMENTOS: ' + json.dumps(repo.sha_por_nome(unit['id']), ensure_ascii=False),
        'DECISOES: ' + json.dumps(repo.decisoes_da_unit(unit['id']), ensure_ascii=False, default=str),
        profile['planning_task'],
        'FONTES METODOLOGICAS (nao sao prova de propriedade): ' + json.dumps(profile['sources'], ensure_ascii=False)])


def require_supported(repo, unit, command):
    if selected(repo, unit) and command != 'planning':
        raise ValueError('surface_title_stage_not_ready:' + command +
                         ': use o plano e pedidos; adaptar coleta/exame/entrega ao template autorizado')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('profile', type=Path)
    p.add_argument('--unit-id', type=int)
    p.add_argument('--reviewer')
    p.add_argument('--reason')
    args = p.parse_args()
    profile = validate(json.loads(args.profile.read_text('utf-8')))
    if args.unit_id is None:
        print(json.dumps({'valid': True, 'name': profile['name'], 'activated': False}))
        return
    from src.casefile.db import connect
    from src.casefile.repo import Repo
    with connect() as conn:
        repo = Repo(conn)
        unit = next((u for u in repo.listar_units() if u['id'] == args.unit_id), None)
        if unit is None:
            raise ValueError('unit_not_found')
        configure(repo, unit, profile, args.reviewer or '', args.reason or '')
    print(json.dumps({'configured_unit': args.unit_id, 'model_called': False}))


if __name__ == '__main__':
    main()
