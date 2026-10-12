"""Persist a pause; current responses are accounted before tools can continue."""
from uuid import uuid4
from src.casefile.db import connect
from src.casefile.repo import Repo
from src.casefile import operations
with connect() as conn:
    repo=Repo(conn)
    for case in repo.operation_cases():
        if case['execution_state']=='running':
            operations.command(repo,{'command_id':uuid4().hex,'unit_id':case['unit_id'],'expected_revision':case['revision'],
                'action':'pause','note':'Conservar o lote e suas respostas para conferir contratos finais e produzir recuperação verificável dentro do limite adicional já aprovado.'})
    print({'unfinished_runs':conn.execute('SELECT id,task_id FROM task_runs WHERE finished_at IS NULL').fetchall()})
