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
    
    # ============ 30페이지 프리미엄 리포트 설정 ============
    
    # 섹션별 토큰 제한
    report_section_max_output_tokens: int = 4000  # 섹션당 최대 출력 토큰
    report_section_max_rulecards: int = 60  # 섹션당 최대 룰카드 수
    
    # 병렬 처리 설정
    report_max_concurrency: int = 3  # 동시 GPT 호출 수 (레이트리밋 방지)
    report_section_timeout: int = 60  # 섹션당 타임아웃 (초)
    report_total_timeout: int = 300  # 전체 리포트 타임아웃 (5분)
    
    # 폴백 설정
    report_enable_fallback: bool = True  # 실패 시 폴백 활성화
    report_fallback_short_mode: bool = True  # 짧은 모드 재시도
    
    # 레거시 호환 (단일 호출 모드)
    max_output_tokens: int = 12000
    max_input_tokens: int = 8000
    
    # Retry Settings
    sajuos_max_retries: int = 3
    sajuos_timeout: int = 180
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
