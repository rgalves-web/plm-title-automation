"""A shared cap is serialized across four real PostgreSQL connections."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

from src.casefile import operations,orquestracao,spending
from src.casefile.db import connect
from src.casefile.repo import Repo
from src.casefile.accounting import RunAccounting
from tests.test_casefile_operations import operation_case,approve,task,request
from tests.helpers_casefile import unit_de_teste


def test_four_workers_cannot_overreserve_the_shared_cap(operation_case,tmp_path):
    repo,first,scope=operation_case
    units=[first]+[unit_de_teste(repo,Path(first['folder_path']).parent/f'CAP-{i}',f'CAP-{i}') for i in range(3)]
    for unit in units:
        if unit['id']!=first['id']:repo.operation_register(unit['id'],scope)
        approve(repo,unit,scope)
        task(repo,unit)
        operations.command(repo,request(repo,unit,'pause'))
    with repo.transacao():
        spending.approve(repo,[u['id'] for u in units],.6,'human:test','Shared synthetic request reservation.')
    for unit in units:operations.command(repo,request(repo,unit,'resume'))
    schema=repo.conn.execute('SELECT current_schema() AS name').fetchone()['name']
    barrier=Barrier(4)
    def reserve_one(unit):
        with connect(os.environ['CASEFILE_TEST_DSN']) as connection:
            connection.execute(f'SET search_path TO "{schema}",public')
            other=Repo(connection)
            current,run=orquestracao.pegar(other,unit['id'],'process:worker-cap-test',teto=50)
            barrier.wait(timeout=30)
            try:
                RunAccounting(other,current,run).before(.2)
                return 'reserved'
            except spending.SharedSpendingCap:
                return 'blocked'
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(reserve_one,units))
    assert sorted(results)==['blocked','reserved','reserved','reserved']
    state=spending.state(repo)
    assert float(state['reserved_usd'])==.6 and float(state['available_usd'])==0
