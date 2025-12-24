"""
사주 AI 서비스 설정
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List
import re


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    
    # KASI (한국천문연구원) API
    kasi_api_key: str = ""
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False  # 프로덕션에서는 False
    
    # Token Limits (비용 통제)
    max_output_tokens: int = 1200
    max_input_tokens: int = 2000
    
    # Cache
    cache_ttl_seconds: int = 86400  # 24시간
    cache_max_size: int = 10000
    
    # CORS - 프로덕션 도메인 포함
    # Vercel 프리뷰 URL도 허용하려면 환경변수에 추가
    allowed_origins: str = "http://localhost:3000,https://sajuos.com,https://www.sajuos.com"
    
    @property
    def allowed_origins_list(self) -> List[str]:
        origins = [origin.strip() for origin in self.allowed_origins.split(",")]
        return origins
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
