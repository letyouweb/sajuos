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
from app.routers import calculate, interpret

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
    
    if settings.openai_api_key:
        logger.info(f"OPENAI_API_KEY loaded: {settings.openai_api_key[:10]}...")
        logger.info(f"Model: {settings.openai_model}")
    else:
        logger.error("OPENAI_API_KEY not set!")
    
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


@app.get("/", tags=["System"])
async def root():
    return {
        "service": "Saju AI Service",
        "status": "running",
        "version": "1.0.1",
        "model": settings.openai_model
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
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
