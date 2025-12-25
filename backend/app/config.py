"""
Saju AI Service Settings
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    
    @property
    def clean_openai_api_key(self) -> str:
        """Clean API key"""
        return self.openai_api_key.strip().replace('\n', '').replace('\r', '')
    
    # KASI API
    kasi_api_key: str = ""
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # Token Limits (30페이지 보고서용)
    max_output_tokens: int = 12000  # ~6000자 = 15페이지+
    max_input_tokens: int = 8000
    
    # Retry Settings (30페이지 보고서용 타임아웃 증가)
    sajuos_max_retries: int = 3
    sajuos_timeout: int = 180  # 3분 (긴 보고서 생성 대응)
    sajuos_retry_base_delay: float = 1.0
    sajuos_retry_max_delay: float = 30.0
    
    # Cache
    cache_ttl_seconds: int = 86400
    cache_max_size: int = 10000
    
    # CORS
    allowed_origins: str = "http://localhost:3000,https://sajuos.com,https://www.sajuos.com"
    
    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]
    
    # Debug Mode
    debug_show_refs: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# No cache - fresh settings each time
def get_settings() -> Settings:
    return Settings()
