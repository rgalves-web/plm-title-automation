"""Windows login entry without a PowerShell script or execution-policy change."""
from pathlib import Path
import json
import os
import sys
import urllib.request


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    try:
        with urllib.request.urlopen('http://127.0.0.1:8788/api/operations', timeout=5) as response:
            state = json.load(response)
            if state.get('installed') and 'cases' in state:
                return
    except (OSError, ValueError):
        pass
    from src.casefile.storage import operation_root
    folder = operation_root() / 'servico'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'inicio_python.log').open('a', encoding='utf-8', buffering=1) as log:
        sys.stdout = sys.stderr = log
        sys.argv = [sys.argv[0], 'serve']
        from src.casefile.workbench import main as serve
        try:
            serve()
        except Exception:
            import traceback
            traceback.print_exc()
            raise


if __name__ == '__main__':
    main()
