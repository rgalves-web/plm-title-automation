"""Snapshot each paused pilot case with verified file references; no API calls."""
import json
from uuid import uuid4
from src.casefile.db import connect
from src.casefile.repo import Repo
from src.casefile import operations
from src.casefile.knowledge_registry import import_sources
with connect() as conn:
    repo=Repo(conn)
    if conn.execute('SELECT 1 FROM task_runs WHERE finished_at IS NULL LIMIT 1').fetchone():raise ValueError('wait_current_execution_before_snapshot')
    print(import_sources(repo))
    for uid in (2,3,4,5):
        operations.command(repo,{'command_id':uuid4().hex,'unit_id':uid,'expected_revision':repo.operation_case(uid)['revision'],
            'action':'build_packet','note':'Pacote local de decisão WORKING DRAFT: conferir todas as referências, preservar resultados, aprendizado aprovado, custos conhecidos e reservas incertas. Sem aprovação de title ou submissão externa.'})
        packet=repo.operation_artifacts(uid,'operation_packet')[-1]
        print(json.dumps({'unit_id':uid,'artifact_id':packet['id'],'path':packet['path'],'sha256':packet['sha256'],'files_verified':packet['metadata']['reference_files_verified']},ensure_ascii=False))
