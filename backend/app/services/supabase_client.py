"""
Supabase Client - 연결 상태 확인용
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
main.py에서 Supabase 연결 상태 확인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)


def is_supabase_available() -> bool:
    """Supabase 설정이 있는지 확인"""
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def get_supabase_status() -> dict:
    """Supabase 상태 정보 반환"""
    settings = get_settings()
    
    has_url = bool(settings.supabase_url)
    has_key = bool(settings.supabase_service_role_key)
    
    return {
        "configured": has_url and has_key,
        "url_set": has_url,
        "key_set": has_key,
        "url_preview": settings.supabase_url[:30] + "..." if has_url else None
    }
