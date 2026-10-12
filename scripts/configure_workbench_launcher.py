"""Record the installed interpreter, never credentials, for Windows login."""
import json
import sys
from src.casefile.storage import operation_root

target=operation_root()/'servico'/'launcher.json'
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps({'python':sys.executable,'port':8788},indent=2),encoding='utf-8')
print('Local launcher configured.')
