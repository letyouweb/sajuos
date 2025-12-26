"""
Saju AI Service - FastAPI Main App v3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P0 요구사항:
- /health: 외부 의존성 0, 즉시 OK
- /ready: 준비상태 체크 (OpenAI/RuleCards/Supabase)
- 포트: PORT 환경변수, 기본 8080
- Supabase: Lazy-init (import 시점 초기화 금지)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import calculate, interpret, reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행"""
    logger.info("🚀 Saju AI Service starting...")
    settings = get_settings()
    
    # 1. OpenAI API Key 확인 (lazy하지 않음 - 필수)
    app.state.openai_ready = False
    try:
        from app.services.openai_key import get_openai_api_key, key_fingerprint, key_tail
        key = get_openai_api_key()
        logger.info(f"✅ OPENAI key fp={key_fingerprint(key)} tail={key_tail(key)}")
        logger.info(f"✅ Model: {settings.openai_model}")
        app.state.openai_ready = True
    except Exception as e:
        logger.error(f"❌ OPENAI_API_KEY error: {e}")
    
    # 2. RuleCards 로드 (시작 시 필수)
    app.state.rulestore = None
    try:
        from app.services.rulecards_store import RuleCardStore
        
        base_dir = os.path.dirname(os.path.dirname(__file__))
        possible_paths = [
            os.path.join(base_dir, "data", "sajuos_master_db.jsonl"),
            os.path.join(os.getcwd(), "data", "sajuos_master_db.jsonl"),
            "/app/data/sajuos_master_db.jsonl",
            "data/sajuos_master_db.jsonl",
        ]
        
        for p in possible_paths:
            if os.path.exists(p):
                rulestore = RuleCardStore(p)
                rulestore.load()
                app.state.rulestore = rulestore
                logger.info(f"✅ RuleCards 로드 완료: {len(rulestore.cards)}장")
                break
        
        if not app.state.rulestore:
            logger.error(f"❌ RuleCards 파일 없음")
    except Exception as e:
        logger.error(f"❌ RuleCards 로드 실패: {e}")
    
    # 3. Supabase 상태 체크 (Lazy-init - 실제 호출 시에만 연결)
    app.state.supabase_configured = bool(
        settings.supabase_url and settings.supabase_service_role_key
    )
    if app.state.supabase_configured:
        logger.info("✅ Supabase 환경변수 설정됨 (Lazy-init)")
    else:
        logger.warning("⚠️ Supabase 환경변수 없음")
    
    # 4. 서버 시작 시 미완료 Job 복구
    if app.state.supabase_configured:
        try:
            from app.services.job_recovery import recover_interrupted_jobs
            recovered = await recover_interrupted_jobs(app.state.rulestore)
            if recovered > 0:
                logger.info(f"🔄 미완료 Job {recovered}개 복구 시작")
        except Exception as e:
            logger.warning(f"Job 복구 스킵: {e}")
    
    logger.info(f"✅ CORS origins: {settings.allowed_origins_list}")
    
    yield
    
    logger.info("👋 Saju AI Service stopped")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI App 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app = FastAPI(
    title="Saju AI Service",
    description="99,000원 프리미엄 비즈니스 사주 컨설팅",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

settings = get_settings()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 라우터 등록 (P0: 라우트 통일 + alias)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 기본 라우터
app.include_router(calculate.router, prefix="/api/v1", tags=["Calculate"])
app.include_router(interpret.router, prefix="/api/v1", tags=["Interpret"])

# 🔥 프리미엄 리포트 라우터 (Primary + Aliases)
# Primary: /api/v1/reports/*
app.include_router(reports.router, prefix="/api/v1", tags=["Premium Reports"])

# Alias 1: /api/reports/* (프론트 호환)
app.include_router(reports.router, prefix="/api", tags=["Reports Alias"], include_in_schema=False)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시스템 엔드포인트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/", tags=["System"])
async def root():
    """서비스 정보"""
    return {
        "service": "Saju AI Service",
        "version": "3.0.0",
        "status": "running"
    }


@app.get("/health", tags=["System"])
async def health_check():
    """
    🏥 헬스체크 - 외부 의존성 0, 즉시 OK
    Railway/K8s 컨테이너 상태 확인용
    """
    return {"status": "ok"}


@app.get("/ready", tags=["System"])
async def readiness_check(request: Request):
    """
    🚀 준비상태 체크 - 실제 서비스 가능 여부
    """
    checks = {
        "openai": getattr(request.app.state, "openai_ready", False),
        "rulecards": request.app.state.rulestore is not None,
        "supabase": getattr(request.app.state, "supabase_configured", False),
    }
    
    all_ready = all(checks.values())
    rulecard_count = len(request.app.state.rulestore.cards) if request.app.state.rulestore else 0
    
    if all_ready:
        return {
            "status": "ready",
            "checks": checks,
            "rulecards_loaded": rulecard_count
        }
    else:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks}
        )


@app.get("/env-check", tags=["System"])
async def env_check():
    """환경변수 설정 상태"""
    return {
        "openai_api_key": "SET" if settings.openai_api_key else "NOT_SET",
        "supabase_url": "SET" if settings.supabase_url else "NOT_SET",
        "supabase_key": "SET" if settings.supabase_service_role_key else "NOT_SET",
        "resend_key": "SET" if settings.resend_api_key else "NOT_SET",
        "model": settings.openai_model,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Exception: {type(exc).__name__}: {str(exc)[:200]}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 직접 실행 (Railway/Docker)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
