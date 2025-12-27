"""
Saju AI Service - FastAPI Main App v4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P0 핵심:
1. PORT = os.getenv("PORT") (하드코딩 금지)
2. /health = 외부 의존성 0, 즉시 OK
3. /api/reports/* + /api/v1/reports/* 둘 다 지원
4. Supabase = Lazy-init
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 로깅
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 FastAPI App 선언 (최상단, lifespan 없이 먼저 선언)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = FastAPI(
    title="Saju AI Service",
    description="99,000원 프리미엄 비즈니스 사주 컨설팅",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 /health - 외부 의존성 0, 즉시 OK (최우선)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.get("/health", tags=["System"])
async def health_check():
    """헬스체크 - DB/Supabase/AI 없이 즉시 OK"""
    return {"status": "ok"}


@app.get("/", tags=["System"])
async def root():
    """서비스 정보"""
    return {"service": "Saju AI Service", "version": "4.0.0", "status": "running"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 라우터 등록 - /api/reports/* + /api/v1/reports/* 둘 다
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from app.routers import calculate, interpret, reports

# Primary routes
app.include_router(calculate.router, prefix="/api/v1", tags=["Calculate"])
app.include_router(interpret.router, prefix="/api/v1", tags=["Interpret"])

# 🔥 Reports - 두 경로 모두 지원 (404 방지)
app.include_router(reports.router, prefix="/api/v1", tags=["Premium Reports"])  # /api/v1/reports/*
app.include_router(reports.router, prefix="/api", tags=["Reports Alias"], include_in_schema=False)  # /api/reports/*


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 준비상태 체크 (/ready)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.get("/ready", tags=["System"])
async def readiness_check():
    """준비상태 - OpenAI/RuleCards/Supabase 체크"""
    checks = {
        "openai": False,
        "rulecards": False,
        "supabase": False,
    }
    
    # OpenAI
    try:
        from app.config import get_settings
        settings = get_settings()
        checks["openai"] = bool(settings.openai_api_key)
    except:
        pass
    
    # RuleCards
    try:
        rulestore = getattr(app.state, "rulestore", None)
        checks["rulecards"] = rulestore is not None and len(rulestore.cards) > 0
    except:
        pass
    
    # Supabase (환경변수만 체크, 연결 안함)
    try:
        from app.config import get_settings
        settings = get_settings()
        checks["supabase"] = bool(settings.supabase_url and settings.supabase_service_role_key)
    except:
        pass
    
    all_ready = all(checks.values())
    
    if all_ready:
        return {"status": "ready", "checks": checks}
    else:
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": checks})


@app.get("/env-check", tags=["System"])
async def env_check():
    """환경변수 상태"""
    try:
        from app.config import get_settings
        settings = get_settings()
        return {
            "openai": "SET" if settings.openai_api_key else "NOT_SET",
            "supabase_url": "SET" if settings.supabase_url else "NOT_SET",
            "supabase_key": "SET" if settings.supabase_service_role_key else "NOT_SET",
            "port": os.getenv("PORT", "NOT_SET"),
        }
    except Exception as e:
        return {"error": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Startup Event (lifespan 대신 on_event 사용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화 (health 체크와 무관)"""
    logger.info(f"🚀 Saju AI Service starting on port {os.getenv('PORT', 'unknown')}...")
    
    # 1. RuleCards 로드 (실패해도 서버는 살아있음)
    app.state.rulestore = None
    try:
        from app.services.rulecards_store import RuleCardStore
        
        possible_paths = [
            "/app/data/sajuos_master_db.jsonl",
            "data/sajuos_master_db.jsonl",
            os.path.join(os.getcwd(), "data", "sajuos_master_db.jsonl"),
        ]
        
        for p in possible_paths:
            if os.path.exists(p):
                rulestore = RuleCardStore(p)
                rulestore.load()
                app.state.rulestore = rulestore
                logger.info(f"✅ RuleCards 로드: {len(rulestore.cards)}장")
                break
        
        if not app.state.rulestore:
            logger.warning("⚠️ RuleCards 파일 없음 (서버는 계속 실행)")
    except Exception as e:
        logger.error(f"❌ RuleCards 로드 실패: {e}")
    
    # 2. OpenAI 키 확인
    try:
        from app.config import get_settings
        settings = get_settings()
        if settings.openai_api_key:
            logger.info("✅ OpenAI API Key 설정됨")
        else:
            logger.warning("⚠️ OpenAI API Key 없음")
    except Exception as e:
        logger.error(f"❌ Config 로드 실패: {e}")
    
    # 3. Supabase는 Lazy-init (여기서 연결 안함)
    logger.info("✅ Supabase: Lazy-init 모드 (첫 저장 시 연결)")
    
    logger.info("✅ 서버 시작 완료")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("👋 Saju AI Service stopped")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 글로벌 예외 핸들러
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Exception: {type(exc).__name__}: {str(exc)[:200]}")
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 직접 실행 (로컬 개발용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
