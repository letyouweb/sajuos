"""
사주 AI 서비스 - FastAPI 메인 앱
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import get_settings
from app.routers import calculate, interpret

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    # 시작 시
    logger.info("🚀 사주 AI 서비스 시작")
    settings = get_settings()
    
    # API 키 확인
    if not settings.openai_api_key:
        logger.warning("⚠️ OPENAI_API_KEY가 설정되지 않았습니다!")
    if not settings.kasi_api_key:
        logger.warning("⚠️ KASI_API_KEY가 설정되지 않았습니다. Fallback 모드로 동작합니다.")
    
    # CORS 설정 로깅
    logger.info(f"✅ CORS 허용 도메인: {settings.allowed_origins_list}")
    
    yield
    
    # 종료 시
    logger.info("👋 사주 AI 서비스 종료")


# FastAPI 앱 생성
app = FastAPI(
    title="사주 AI 서비스",
    description="""
## 🔮 AI 기반 사주 해석 서비스

### 주요 기능
- `/calculate`: 생년월일 → 사주 원국 계산
- `/interpret`: 사주 원국 → AI 해석

### ⚠️ 면책 조항
본 서비스는 오락/참고 목적으로 제공되며, 의학/법률/투자 등 전문적 조언을 대체하지 않습니다.
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정 - sajuqueen.com에서 직접 호출 허용
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(calculate.router, prefix="/api/v1", tags=["사주 계산"])
app.include_router(interpret.router, prefix="/api/v1", tags=["사주 해석"])


# 헬스체크
@app.get("/", tags=["시스템"])
async def root():
    """서비스 상태 확인"""
    return {
        "service": "사주 AI 서비스",
        "status": "running",
        "version": "1.0.0",
        "cors_origins": settings.allowed_origins_list,
        "endpoints": {
            "calculate": "/api/v1/calculate",
            "interpret": "/api/v1/interpret",
            "docs": "/docs"
        }
    }


@app.get("/health", tags=["시스템"])
async def health_check():
    """헬스체크"""
    return {"status": "healthy"}


# 에러 핸들러
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_code": "INTERNAL_ERROR",
            "message": "서버 내부 오류가 발생했습니다.",
            "detail": str(exc) if settings.debug else None
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
