"""Display bounded test diagnostics with credentials redacted."""
import re
import sys
from pathlib import Path

text=Path(sys.argv[1]).read_text(encoding='utf-8',errors='replace')
text=re.sub(r'([a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@',r'\1[redacted]@',text)
text=re.sub(r'\bsk-[A-Za-z0-9_-]{8,}','[redacted-key]',text)
print('\n'.join(text.splitlines()[-int(sys.argv[2] if len(sys.argv)>2 else 45):]))
