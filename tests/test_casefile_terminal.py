import json
from types import SimpleNamespace

import pytest

from src.infra import terminal, providers
from src.casefile import worker
from tests.test_casefile_operations import operation_case, approve, task, request, RESEARCH
from tests.helpers_casefile import ClientRoteirizado, Use


def events(text='', calls=None):
    return [{'type':'item.completed','item':{'type':'agent_message','text':json.dumps({'text':text,'calls':calls or []})}},
            {'type':'turn.completed','usage':{'input_tokens':30,'cached_input_tokens':10,'output_tokens':4}}]


def test_terminal_environment_removes_keys(monkeypatch):
    for key in terminal.KEYS:
        monkeypatch.setenv(key, 'synthetic-credential')
    assert not terminal.KEYS.intersection(terminal.child_environment())


def test_api_disabled_has_no_sdk_fallback(monkeypatch):
    monkeypatch.setenv('PLM_API_DISABLED','1')
    with pytest.raises(RuntimeError,match='direct_api_disabled'):
        providers.client('A')
    assert isinstance(providers.client('B',transport='terminal'),terminal.TerminalAdapter)


def test_cli_parser_preserves_calls_usage_and_subscription_receipt():
    tool={'name':'read','input_schema':{'type':'object','properties':{'page':{'type':'integer'}},'required':['page']}}
    reply=terminal.TerminalAdapter('B').parse(events(calls=[{'name':'read','arguments':'{"page":2}'}]),[tool])
    assert reply.content[0].input=={'page':2}
    assert reply.usage.input_tokens==20 and reply.usage.cache_read_input_tokens==10
    assert reply.terminal_receipt['subscription_charge_usd'] is None


@pytest.mark.parametrize('bad',[
    [{'type':'turn.failed'}],
    [{'type':'item.completed','item':{'type':'file_change'}}],
    events(calls=[{'name':'shell','arguments':'{}'}]),
    events()[:-1],
])
def test_cli_invalid_or_unreceipted_result_never_dispatches(bad):
    with pytest.raises(terminal.TerminalError):
        terminal.TerminalAdapter('B').parse(bad,[])


def test_claude_api_login_is_refused(monkeypatch):
    monkeypatch.setattr(terminal,'executable',lambda _: 'claude')
    monkeypatch.setattr(terminal,'run_process',lambda *a,**k:(0,json.dumps({'loggedIn':True,'authMethod':'api_key'}),''))
    assert not terminal.auth_status('A')['ok']


def test_delete_keys_preserves_database_settings_without_copy(tmp_path,monkeypatch):
    monkeypatch.setenv('PLM_API_DISABLED','0')
    from scripts.configure_terminal import remove_local_keys
    path=tmp_path/'.env'
    path.write_text('ANTHROPIC_API_KEY=synthetic-one\nOPENAI_API_KEY=synthetic-two\nCASEFILE_DSN=synthetic-db\n')
    remove_local_keys(tmp_path,clean_windows=False)
    value=path.read_text()
    assert 'synthetic-one' not in value and 'synthetic-two' not in value
    assert 'CASEFILE_DSN=synthetic-db' in value and 'PLM_API_DISABLED=1' in value
    assert len(list(tmp_path.iterdir()))==1


class ScriptedTerminal(ClientRoteirizado):
    def create(self,**kwargs):
        result=super().create(**kwargs)
        result.terminal_receipt={'billing_mode':'subscription','api_charge_usd':0,'subscription_charge_usd':None}
        return result


@pytest.mark.parametrize('independent',[False,True])
def test_real_worker_uses_terminal_without_api_reservation(operation_case,monkeypatch,independent):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    case=repo.operation_case(unit['id'])
    repo.operation_update(unit['id'],profile={**case['profile'],'execution_backend':'terminal'})
    item=task(repo,unit)
    if independent:
        repo.conn.execute('UPDATE tasks SET input_json=\'{"independent_comparison":true}\' WHERE id=%s',(item['id'],))
    monkeypatch.setattr(repo,'reservar_orcamento',lambda *a:pytest.fail('terminal must not reserve API money'))
    result=worker.executar_uma(repo,unit['id'],'terminal-fixture',teto=50,operation=True,
        client=ScriptedTerminal([[Use('entregar_saida',{'saida':RESEARCH})]]))
    assert result['erros']==[]
    run=repo.run(result['run_id'])
    assert run['execution_backend']=='terminal' and run['usage_state']=='subscription'
    assert ('/codex/' in run['model']) is independent
    assert not repo.conn.execute('SELECT 1 FROM operation_requests').fetchone()
    saved=repo.conn.execute('SELECT * FROM operation_terminal_calls').fetchone()
    assert saved['status']=='completed' and saved['receipt']['subscription_charge_usd'] is None


def test_terminal_failure_blocks_without_automatic_retry(operation_case):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    repo.operation_update(unit['id'],profile={**repo.operation_case(unit['id'])['profile'],'execution_backend':'terminal'})
    task(repo,unit)
    class Failing:
        messages=None
        def __init__(self):self.messages=self
        def create(self,**kwargs):raise terminal.TerminalError('terminal_timeout_requires_review')
    result=worker.executar_uma(repo,unit['id'],'terminal-fixture',teto=50,operation=True,client=Failing())
    assert result['tarefa']['status']=='bloqueada'
    assert repo.operation_case(unit['id'])['execution_state']=='waiting'
    assert not repo.conn.execute('SELECT 1 FROM operation_requests').fetchone()
    assert repo.conn.execute('SELECT status FROM operation_terminal_calls').fetchone()['status']=='interrupted'


@pytest.mark.parametrize('family',['A','B'])
def test_launch_contract_retains_subscription_login_and_no_native_tools(monkeypatch,tmp_path,family):
    monkeypatch.setenv('PLM_OPERATION_ROOT',str(tmp_path))
    monkeypatch.setattr(terminal,'auth_status',lambda _: {'ok':True})
    monkeypatch.setattr(terminal,'executable',lambda _: 'official-cli')
    observed={}
    def process(args,**kwargs):
        observed['args']=args
        if family=='A':
            assert '--safe-mode' in args and '--bare' not in args
            assert args[args.index('--tools')+1]==''
            from pathlib import Path
            trusted=Path(args[args.index('--system-prompt-file')+1]).read_text('utf-8')
            assert 'trusted-contract-marker' in trusted
            data={'type':'result','subtype':'success','is_error':False,
                'structured_output':{'text':'ok','calls':[]},'usage':{'input_tokens':3,'output_tokens':2}}
            return 0,json.dumps(data),''
        assert 'mcp_servers={}' in args and 'plugins={}' in args
        assert args[args.index('--sandbox')+1]=='read-only'
        assert '--dangerously-bypass-approvals-and-sandbox' not in args
        return 0,'\n'.join(map(json.dumps,events('ok'))),''
    monkeypatch.setattr(terminal,'run_process',process)
    message=terminal.TerminalAdapter(family).create(model='terminal/claude/sonnet' if family=='A' else 'terminal/codex/default',
        system='trusted-contract-marker',messages=[{'role':'user','content':'synthetic data'}],tools=[],max_tokens=500)
    assert message.content[0].text=='ok'
    assert message.terminal_receipt['protocol_sha256']
    assert not list((tmp_path/'terminal_tmp').iterdir())


def test_sleep_does_not_repeat_terminal_without_explicit_operator_review(operation_case):
    from src.casefile import orquestracao,operations
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    first=task(repo,unit); second=task(repo,unit)
    _,run=orquestracao.pegar(repo,unit['id'],'sleep-fixture',teto=50,max_active_per_unit=1)
    repo.conn.execute("UPDATE task_runs SET execution_backend='terminal',usage_state='subscription_running',lease_until=now()-interval '1 second' WHERE id=%s",(run['id'],))
    repo.conn.execute("INSERT INTO operation_terminal_calls(run_id,ordinal,family) VALUES (%s,1,'A')",(run['id'],))
    picked=orquestracao.pegar(repo,unit['id'],'other-fixture',teto=50,max_active_per_unit=1)
    assert picked[0]['id']==second['id']
    assert repo.tarefa(first['id'])['status']=='bloqueada'
    operations.command(repo,request(repo,unit,'retry_task',task_id=first['id']))
    assert repo.conn.execute('SELECT receipt FROM operation_terminal_calls').fetchone()['receipt']['reviewed_by'].startswith('human:')
    assert repo.tarefa(first['id'])['status']=='pronta'


def test_terminal_reply_after_expired_lease_is_not_dispatched(operation_case):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    repo.operation_update(unit['id'],profile={**repo.operation_case(unit['id'])['profile'],'execution_backend':'terminal'})
    task(repo,unit)
    class Late(ScriptedTerminal):
        def create(self,**kwargs):
            response=super().create(**kwargs)
            repo.conn.execute("UPDATE task_runs SET lease_until=now()-interval '1 second' WHERE finished_at IS NULL")
            return response
    result=worker.executar_uma(repo,unit['id'],'late-fixture',teto=50,operation=True,
        client=Late([[Use('entregar_saida',{'saida':RESEARCH})]]))
    assert result['tarefa']['status']=='bloqueada' and not result['gravados']
    assert repo.conn.execute('SELECT receipt FROM operation_terminal_calls').fetchone()['receipt']['billing_mode']=='subscription'
