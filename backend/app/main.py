"""
Saju AI Service - Main App (v5 Emergency Fix)
"""
import os
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 App 선언 (최상단)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = FastAPI(title="Saju AI", version="5.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 /health - 무조건 즉시 OK (최우선)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"service": "Saju AI", "status": "running"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 라우터 등록 (try-except로 보호)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    from app.routers import calculate, interpret
    app.include_router(calculate.router, prefix="/api/v1", tags=["Calculate"])
    app.include_router(interpret.router, prefix="/api/v1", tags=["Interpret"])
    logger.info("✅ calculate, interpret 라우터 등록")
except Exception as e:
    logger.error(f"❌ 기본 라우터 등록 실패: {e}")

try:
    from app.routers import reports
    app.include_router(reports.router, prefix="/api/v1", tags=["Reports"])
    app.include_router(reports.router, prefix="/api", include_in_schema=False)
    logger.info("✅ reports 라우터 등록 (/api/v1/reports + /api/reports)")
except Exception as e:
    logger.error(f"❌ reports 라우터 등록 실패: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Startup (실패해도 서버는 살아있음)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_event("startup")
async def startup():
    logger.info(f"🚀 Server starting on PORT={os.getenv('PORT', 'unknown')}")
    
    # RuleCards (실패해도 OK)
    app.state.rulestore = None
    try:
        from app.services.rulecards_store import RuleCardStore
        for p in ["/app/data/sajuos_master_db.jsonl", "data/sajuos_master_db.jsonl"]:
            if os.path.exists(p):
                store = RuleCardStore(p)
                store.load()
                app.state.rulestore = store
                logger.info(f"✅ RuleCards: {len(store.cards)}장")
                break
    except Exception as e:
        logger.warning(f"⚠️ RuleCards 로드 실패 (계속 진행): {e}")
    
    logger.info("✅ Startup 완료")


@app.get("/ready")
async def ready():
    checks = {
        "rulecards": app.state.rulestore is not None,
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "supabase": bool(os.getenv("SUPABASE_URL")),
    }
    return {"status": "ready" if all(checks.values()) else "partial", "checks": checks}


@app.exception_handler(Exception)
async def error_handler(request: Request, exc: Exception):
    logger.error(f"Error: {exc}")
    return JSONResponse(status_code=500, content={"error": str(exc)[:100]})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
