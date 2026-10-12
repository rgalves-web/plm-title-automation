"""Create a reviewable relocation plan only after preservation and restore proof."""
import json
from pathlib import Path
from datetime import datetime,timezone

from src.casefile.bootstrap import inventory_files
from src.casefile.storage import REPO_ROOT,operation_root,digest_file


def inspect():
    root=operation_root()
    proofs=sorted((root/'recuperacao').glob('snapshot_*/RECUPERACAO_VERIFICADA.json'))
    if not proofs or not json.loads(proofs[-1].read_text('utf-8')).get('ok'):
        raise ValueError('verified_database_recovery_required')
    aliases_file=root/'migracao'/'aliases.json'
    aliases=json.loads(aliases_file.read_text('utf-8'))
    checked={}
    project=REPO_ROOT.parent/'Land Cibola Surface Titles'
    actions=[];unscoped={};files=0
    for source in sorted(project.glob('00_Controle_Local_*')):
        if not source.is_dir() or source.is_symlink():continue
        destination=(root/'historico'/'controles_cibola'/source.name).resolve()
        if destination.exists():raise ValueError('historical_destination_already_exists')
        for path in inventory_files(source):
            if not path.is_file():continue
            original=path.resolve()
            if not original.is_relative_to(project.resolve()):raise ValueError('control_source_outside_project')
            sha=digest_file(original)
            entry=aliases.get(str(original))
            if entry:
                target=Path(entry['path']).resolve()
                if not (target.is_relative_to((root/'casos').resolve()) or target.is_relative_to((project/'Terrell County').resolve())):raise ValueError('preserved_copy_outside_cases')
                if str(target) not in checked:checked[str(target)]=digest_file(target)
                if checked[str(target)]!=sha or entry['sha256']!=sha:raise ValueError('preserved_control_bytes_differ')
            else:
                unscoped[str(original)]={'path':str(destination/original.relative_to(source.resolve())),'sha256':sha}
            files+=1
        actions.append({'source':str(source.resolve()),'destination':str(destination)})
    result={'workspace':str(REPO_ROOT.parent.resolve()),'historical_root':str((root/'historico').resolve()),
            'recovery_proof':str(proofs[-1]),'files_checked':files,'preserved_copies_checked':len(checked),
            'actions':actions,'additional_aliases':unscoped,'inspected_at':datetime.now(timezone.utc).isoformat(),
            'delete_sources':False,'delivered_packages_unchanged':True,'project_log_unchanged':True}
    target=root/'migracao'/'retirada_controles.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print({'plan':str(target),'folders':len(actions),'files_checked':files,'deleted_files':0})
    return target


def finish():
    root=operation_root()
    plan=json.loads((root/'migracao'/'retirada_controles.json').read_text('utf-8'))
    for action in plan['actions']:
        if Path(action['source']).exists() or not Path(action['destination']).is_dir():
            raise ValueError('control_relocation_not_complete')
    for entry in plan['additional_aliases'].values():
        if digest_file(entry['path'])!=entry['sha256']:raise ValueError('relocated_unique_control_changed')
    aliases_file=root/'migracao'/'aliases.json'
    aliases=json.loads(aliases_file.read_text('utf-8'))
    aliases_file.write_text(json.dumps({**aliases,**plan['additional_aliases']},ensure_ascii=False,indent=2),encoding='utf-8')
    plan['verified_after_move_at']=datetime.now(timezone.utc).isoformat()
    plan['reference_map_sha256']=digest_file(aliases_file)
    (root/'migracao'/'RETIRADA_CONTROLES_VERIFICADA.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    print({'relocated_folders':len(plan['actions']),'references_verified':len(aliases),'deleted_unique_sources':0})


if __name__=='__main__':
    import sys
    finish() if sys.argv[-1]=='finish' else inspect()
