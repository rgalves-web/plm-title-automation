"""Free provider model catalog read. Sends no case data or inference requests."""
import json
from datetime import datetime,timezone
from src.casefile.db import _carregar_dotenv
from src.casefile.worker import MODELO_POR_NIVEL
from src.casefile.verificador import modelo_b
from src.casefile.storage import operation_root
from src.infra.providers import client
from src.infra.loop import RATES

_carregar_dotenv()
claude={m.id for m in client('A').models.list()}
openai={m.id for m in client('B').client.models.list()}
models={**MODELO_POR_NIVEL,'independente':modelo_b()}
result={'verified_at':datetime.now(timezone.utc).isoformat(),'paid_requests':0,
        'available':{name:model in (openai if name=='independente' else claude) for name,model in models.items()},
        'models':models,'rates':{m:RATES[m] for m in models.values()},
        'price_sources':['https://platform.claude.com/docs/en/about-claude/pricing','https://developers.openai.com/api/docs/models/gpt-5.6-terra']}
target=operation_root()/'servico'/'provedores.json'
target.write_text(json.dumps(result,indent=2),encoding='utf-8')
print({'available':result['available'],'paid_requests':0})
