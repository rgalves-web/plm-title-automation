"""Database dump and verified restore into an isolated, password-protected cluster."""
import json
import os
import secrets
import socket
import subprocess
from pathlib import Path
from datetime import datetime,timezone

from src.casefile.db import connect,dsn
from src.casefile.storage import operation_root,digest_file

TABLES=('units','claims','model_sessions','cost_entries','tasks','task_runs','operation_artifacts','operation_artifact_links','operation_lessons','operation_commands','operation_cases','operation_events','operation_source_jobs','operation_requirements','operation_requests','operation_spending_limits','knowledge_registry_versions')


def binaries():
    found=list(Path('C:/Program Files/PostgreSQL').glob('*/bin/pg_dump.exe'))
    if not found: raise ValueError('postgresql_recovery_tools_required')
    return found[-1].parent


def counts(conn):
    return {table:conn.execute('SELECT count(*) AS n FROM '+table).fetchone()['n'] for table in TABLES
            if conn.execute('SELECT to_regclass(%s) AS name',(table,)).fetchone()['name']}


def invoke(command,environment):
    result=subprocess.run([str(a) for a in command],env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=180)
    if result.returncode:
        raise RuntimeError('recovery_command_failed:'+Path(str(command[0])).name+':'+str(result.returncode))


def backup():
    from psycopg.conninfo import conninfo_to_dict
    with connect() as conn:
        if conn.execute("SELECT to_regclass('operation_cases') AS name").fetchone()['name'] and conn.execute("SELECT 1 FROM operation_cases WHERE execution_state='running' LIMIT 1").fetchone():
            raise ValueError('pause_cases_before_verified_recovery_snapshot')
        expected=counts(conn)
    params=conninfo_to_dict(dsn())
    environment=os.environ.copy()
    environment['PGPASSWORD']=params.get('password','')
    root=operation_root()/'recuperacao'/('snapshot_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'))
    root.mkdir(parents=True)
    target=root/'casefile.dump'
    invoke([binaries()/'pg_dump.exe','-h',params.get('host','localhost'),'-p',params.get('port','5432'),
            '-U',params['user'],'-d',params['dbname'],'-Fc','-f',target],environment)
    meta={'sha256':digest_file(target),'counts':expected,'created_at':datetime.now(timezone.utc).isoformat()}
    (root/'manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    return target


def verify(snapshot):
    import psycopg
    from psycopg.rows import dict_row
    snapshot=Path(snapshot).resolve()
    if not snapshot.is_relative_to((operation_root()/'recuperacao').resolve()):
        raise ValueError('declared_recovery_snapshot_required')
    meta=json.loads(snapshot.with_name('manifest.json').read_text('utf-8'))
    if digest_file(snapshot)!=meta['sha256']: raise ValueError('recovery_snapshot_changed')
    root=snapshot.parent/'verificacao_isolada'
    root.mkdir(exist_ok=False)
    pw=root/'senha_temporaria.txt';password=secrets.token_urlsafe(32);pw.write_text(password,encoding='utf-8')
    bin=binaries();data=root/'postgres'
    environment=os.environ.copy();environment['PGPASSWORD']=password
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    started=False
    try:
        invoke([bin/'initdb.exe','-D',data,'-U','plm_recovery','-A','scram-sha-256','--pwfile',pw,'--no-locale','-E','UTF8'],environment)
        pw.unlink()
        started=True
        invoke([bin/'pg_ctl.exe','-D',data,'-l',root/'postgres.log','-o',f'-h 127.0.0.1 -p {port}','-w','start'],environment)
        invoke([bin/'pg_restore.exe','-h','127.0.0.1','-p',port,'-U','plm_recovery','-d','postgres',
                '--no-owner','--no-privileges','--exit-on-error',snapshot],environment)
        with psycopg.connect(host='127.0.0.1',port=port,user='plm_recovery',password=password,dbname='postgres',row_factory=dict_row) as conn:
            actual=counts(conn)
        if actual!=meta['counts']:raise ValueError('recovered_counts_differ')
        proof={'ok':True,'snapshot_sha256':meta['sha256'],'counts':actual,'isolated_cluster':True,
               'verified_at':datetime.now(timezone.utc).isoformat(),'production_unchanged':True}
        (snapshot.parent/'RECUPERACAO_VERIFICADA.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
        return proof
    finally:
        if started:invoke([bin/'pg_ctl.exe','-D',data,'-m','fast','-w','stop'],environment)
        if pw.exists():pw.unlink()


if __name__=='__main__':
    snapshot=backup()
    print(json.dumps(verify(snapshot),ensure_ascii=False))
