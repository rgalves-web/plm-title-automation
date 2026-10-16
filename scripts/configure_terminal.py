"""Remove PLM model API keys and select official account-authenticated CLIs.

Never copies credentials into a backup, prints their values, revokes unrelated
account keys, or changes historical API charges. All cases remain paused.
"""
import json
import os
from pathlib import Path
import re

from src.infra.terminal import KEYS, auth_status


def remove_local_keys(root, *, clean_windows=True):
    from dotenv import dotenv_values
    removed = []
    values = set()
    for path in root.glob('.env*'):
        if not path.is_file():
            continue
        parsed = dotenv_values(path)
        names = [name for name in KEYS if parsed.get(name)]
        values.update(parsed[name] for name in names)
        original = path.read_text('utf-8-sig')
        clean = ''.join(line for line in original.splitlines(keepends=True)
            if not re.match(r'^\s*(?:export\s+)?(' + '|'.join(KEYS) + r')\s*=', line))
        if path.name == '.env':
            clean = re.sub(r'^\s*PLM_API_DISABLED\s*=.*$', '', clean, flags=re.M).rstrip() + '\nPLM_API_DISABLED=1\n'
        if clean != original:
            path.write_text(clean, encoding='utf-8')
        if any(dotenv_values(path).get(name) for name in KEYS):
            raise RuntimeError('credential_removal_not_verified')
        removed.append({'path': path.name, 'removed_variables': names})
    # Only remove a persisted Windows variable when it is the same PLM key.
    if os.name == 'nt' and clean_windows:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as env:
            for name in KEYS:
                try:
                    value, _ = winreg.QueryValueEx(env, name)
                    if value in values:
                        winreg.DeleteValue(env, name)
                except FileNotFoundError:
                    pass
    for name in KEYS:
        os.environ.pop(name, None)
    os.environ['PLM_API_DISABLED'] = '1'
    return removed


def main():
    from src.casefile.db import connect, migrar
    from src.casefile.repo import Repo
    root = Path(__file__).resolve().parents[1]
    with connect() as conn:
        if conn.execute('SELECT 1 FROM task_runs WHERE finished_at IS NULL LIMIT 1').fetchone():
            raise RuntimeError('wait_current_execution_before_backend_change')
        migrar(conn)
        repo = Repo(conn)
        cases = []
        with repo.transacao():
            for case in repo.operation_cases():
                uid = case['unit_id']
                repo.operation_update(uid, execution_state='paused', profile={**case['profile'],
                    'execution_backend': 'terminal', 'backend_changed_by': 'human:renato',
                    'backend_change_note': 'Renato solicitou excluir as chaves e usar Claude Code e Codex pelo terminal.'})
                repo.operation_event('execution.backend_changed', 'human:renato',
                    {'backend': 'terminal', 'api_fallback': False, 'historical_charges_preserved': True}, unit_id=uid)
                cases.append(uid)
        removed = remove_local_keys(root)
    print(json.dumps({'cases_paused': cases, 'key_removal': removed,
        'claude_code': auth_status('A'), 'codex': auth_status('B')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
