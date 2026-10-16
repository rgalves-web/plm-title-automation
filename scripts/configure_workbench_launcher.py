"""Record the installed interpreter, never credentials, for Windows login."""
import json
import sys
from pathlib import Path
from src.casefile.storage import operation_root

target=operation_root()/'servico'/'launcher.json'
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps({'python':sys.executable,'port':8788},indent=2),encoding='utf-8')
print('Local launcher configured.')

if '--install-startup' in sys.argv:
    import winreg
    python = Path(sys.executable)
    candidates = [python.with_name('pythonw.exe'), python.with_name('pythonw3.12.exe')]
    pythonw = next((path for path in candidates if path.is_file()), None)
    if pythonw is None:
        raise RuntimeError('pythonw_not_found_for_hidden_startup')
    entry = '"' + str(pythonw) + '" "' + str(Path(__file__).with_name('run_workbench.py').resolve()) + '"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, 'PLMTitleWorkbench', 0, winreg.REG_SZ, entry)
    print('Inicialização direta pelo Python configurada; política PowerShell preservada.')
