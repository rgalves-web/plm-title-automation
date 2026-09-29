import hashlib
import json
import pytest
from src.casefile import cli, project_profile
from tests.helpers_casefile import RepoFake, unit_de_teste


def setup(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    source = root / 'source.txt'
    source.write_text('synthetic methodology', encoding='utf-8')
    profile = dict(schema=1, name='synthetic surface', work_type='surface_title',
                   project_root=str(root), planning_system='Synthetic planning system',
                   planning_task='Synthetic parcel planning task',
                   sources=[dict(path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest())])
    repo = RepoFake()
    unit = unit_de_teste(repo, root / 'TRACT-1')
    return repo, unit, profile


def test_profile_explicit_and_planner_routing(tmp_path):
    repo, unit, profile = setup(tmp_path)
    assert project_profile.selected(repo, unit) is None
    project_profile.configure(repo, unit, profile, 'fixture', 'synthetic test')
    task = cli._task_planejar(repo, unit, {}, {'conteudos':0})
    assert 'Synthetic parcel planning task' in task
    assert 'Lease-to-Well' not in task
    assert project_profile.selected(repo, unit)['planning_system'] == 'Synthetic planning system'


def test_profile_rejects_wrong_project_and_changed_sources(tmp_path):
    repo, unit, profile = setup(tmp_path)
    outside = dict(unit, folder_path=str(tmp_path / 'different' / 'TRACT-1'))
    with pytest.raises(ValueError, match='outside_project'):
        project_profile.configure(repo, outside, profile, 'fixture', 'test')
    project_profile.configure(repo, unit, profile, 'fixture', 'test')
    from pathlib import Path
    Path(profile['sources'][0]['path']).write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='source_changed'):
        project_profile.selected(repo, unit)


@pytest.mark.parametrize('command', ['cmd_coletar','cmd_reconciliar','cmd_examinar','cmd_avancar'])
def test_surface_does_not_enter_emirates_pipeline(tmp_path, command):
    repo, unit, profile = setup(tmp_path)
    project_profile.configure(repo, unit, profile, 'fixture', 'test')
    before = repo.estado_da_unit(unit['id'])
    with pytest.raises(ValueError, match='surface_title_stage_not_ready'):
        getattr(cli, command)(unit['canonical_name'], repo=repo)
    assert repo.estado_da_unit(unit['id']) == before


def test_invalid_profile_fails_before_planning_transition(tmp_path):
    repo, unit, profile = setup(tmp_path)
    from pathlib import Path
    Path(unit['folder_path']).mkdir()
    profile['project_root'] = str(tmp_path / 'wrong')
    repo.registrar_politica(unit['id'], 'project_profile', json.dumps(profile))
    with pytest.raises(ValueError, match='outside_project'):
        cli.cmd_planejar(unit['canonical_name'], repo=repo)
    assert repo.estado_da_unit(unit['id']) == 'INDICADA'
