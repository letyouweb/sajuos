# services package - lazy imports to prevent startup errors
from app.services.engine_v2 import EPHEM_AVAILABLE, CalculationError

# Lazy import: 실제 사용할 때 import
scientific_engine = None
saju_engine = None
gpt_interpreter = None
cache_service = None

def get_scientific_engine():
    global scientific_engine
    if scientific_engine is None:
        from app.services.engine_v2 import scientific_engine as _engine
        scientific_engine = _engine
    return scientific_engine

def get_saju_engine():
    global saju_engine
    if saju_engine is None:
        from app.services.saju_engine import saju_engine as _engine
        saju_engine = _engine
    return saju_engine

def get_gpt_interpreter():
    global gpt_interpreter
    if gpt_interpreter is None:
        from app.services.gpt_interpreter import gpt_interpreter as _interpreter
        gpt_interpreter = _interpreter
    return gpt_interpreter

def get_cache_service():
    global cache_service
    if cache_service is None:
        from app.services.cache import cache_service as _cache
        cache_service = _cache
    return cache_service
