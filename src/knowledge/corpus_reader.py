"""Historical import alias; implementation lives in src.infra."""
import sys
from src.infra import corpus_index as _implementation
sys.modules[__name__] = _implementation
