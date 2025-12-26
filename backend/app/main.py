"""
Saju AI Service - FastAPI Main App
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import re

from app.config import get_settings
from app.routers import calculate, interpret, reports
from app.services.openai_key import get_openai_api_key, key_fingerprint, key_tail
from app.services.rulecards_store import RuleCardStore
from app.services.supabase_client import is_supabase_available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def is_allowed_origin(origin: str, allowed_origins: list) -> bool:
    if not origin:
        return False
    if origin in allowed_origins:
        return True
    if origin.endswith('.vercel.app') and origin.startswith('https://'):
        return True
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Saju AI Service starting...")
    settings = get_settings()
    
    # OpenAI API Key 확인
    try:
        key = get_openai_api_key()
        logger.info("OPENAI key fp=%s tail=%s", key_fingerprint(key), key_tail(key))
        logger.info(f"Model: {settings.openai_model}")
    except RuntimeError as e:
        logger.error(f"OPENAI_API_KEY error: {e}")
    
    # RuleCards 로드 (8,500장 사주 데이터)
    try:
        import os
        
        # 여러 경로 시도 (Railway/로컬 호환)
        base_dir = os.path.dirname(os.path.dirname(__file__))  # backend/
        possible_paths = [
            os.path.join(base_dir, "data", "sajuos_master_db.jsonl"),
            os.path.join(os.getcwd(), "data", "sajuos_master_db.jsonl"),
            "/app/data/sajuos_master_db.jsonl",  # Docker/Railway
            "data/sajuos_master_db.jsonl",  # 상대 경로
        ]
        
        rulecards_path = None
        for p in possible_paths:
            if os.path.exists(p):
                rulecards_path = p
                break
        
        if not rulecards_path:
            logger.error(f"❌ RuleCards 파일 없음. 시도한 경로: {possible_paths}")
            app.state.rulestore = None
        else:
            rulestore = RuleCardStore(rulecards_path)
            rulestore.load()
            app.state.rulestore = rulestore
            logger.info(f"✅ RuleCards 로드 완료: {len(rulestore.cards)}장, topics={len(rulestore.by_topic)}, path={rulecards_path}")
    except Exception as e:
        logger.error(f"❌ RuleCards 로드 실패: {e}")
        app.state.rulestore = None
    
    logger.info(f"CORS origins: {settings.allowed_origins_list}")
    
    yield
    
    logger.info("Saju AI Service stopped")


app = FastAPI(
    title="Saju AI Service",
    description="AI-based Saju interpretation",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calculate.router, prefix="/api/v1", tags=["Calculate"])
app.include_router(interpret.router, prefix="/api/v1", tags=["Interpret"])
app.include_router(reports.router, prefix="/api", tags=["Premium Reports"])
app.include_router(reports.router, prefix="/api/v1", tags=["Premium Reports V1"])  # 🔥 Alias for consistency


@app.get("/", tags=["System"])
async def root():
    return {
        "service": "Saju AI Service",
        "status": "running",
        "version": "2.0.0",
        "model": settings.openai_model,
        "supabase": "connected" if is_supabase_available() else "not_configured"
    }


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy"}


@app.get("/env-check", tags=["System"])
async def env_check():
    return {
        "openai_api_key": "SET" if settings.openai_api_key else "NOT_SET",
        "model": settings.openai_model,
        "allowed_origins": settings.allowed_origins_list
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Exception: {type(exc).__name__}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    import os
    # Railway가 주입해주는 PORT 변수를 읽어옵니다. 없으면 기본값 8080 사용.
    port = int(os.environ.get("PORT", 8080))
    # host는 반드시 "0.0.0.0"이어야 외부(Railway)에서 접근 가능합니다.
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
