"""
Saju AI Service Settings v5
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
99,000원 프리미엄 리포트 설정:
- Supabase 영구 저장
- 이메일 알림 (Resend)
- 백그라운드 Job 처리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    
    @property
    def clean_openai_api_key(self) -> str:
        return self.openai_api_key.strip().replace('\n', '').replace('\r', '')
    
    # KASI API
    kasi_api_key: str = ""
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Supabase (DB 영구 저장)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    supabase_url: str = ""
    supabase_service_role_key: str = ""  # Service Role (백엔드용)
    supabase_anon_key: str = ""  # Anon Key (프론트용, 선택)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Email (Resend)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    resend_api_key: str = ""
    email_from: str = "SajuOS <noreply@sajuos.com>"
    email_reply_to: str = "support@sajuos.com"
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Frontend URL (이메일 링크용)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    frontend_url: str = "https://sajuos.com"
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Redis (백그라운드 Job 큐) - 선택적
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    redis_url: str = "redis://localhost:6379/0"
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 99,000원 프리미엄 리포트 설정
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    # 섹션별 설정
    report_section_max_output_tokens: int = 4000
    report_section_timeout: int = 90
    
    # 동시성
    report_max_concurrency: int = 2
    
    # Retry 설정
    report_max_retries: int = 3
    report_retry_base_delay: float = 2.0
    
    # RuleCard 설정
    report_rulecard_top_limit: int = 100
    
    # 전체 타임아웃
    report_total_timeout: int = 600
    
    # 레거시 호환
    max_output_tokens: int = 12000
    max_input_tokens: int = 8000
    
    # Retry Settings (레거시)
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
    
    # Debug
    debug_show_refs: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


_settings: Optional[Settings] = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
