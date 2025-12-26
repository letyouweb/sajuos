"""
Supabase Service - Job 영속화 서비스 (Lazy-init)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P1 요구사항:
- Lazy-init: import 시점에 연결하지 않음, 실제 호출 시 연결
- service_role_key 사용 (프론트 노출 금지)
- Job 상태: queued → generating → completed/failed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class SupabaseService:
    """
    Supabase Job 영속화 서비스
    - Lazy-init: 첫 호출 시에만 클라이언트 생성
    - 싱글톤 패턴
    """
    
    _instance: Optional["SupabaseService"] = None
    _client = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _get_client(self):
        """Lazy 클라이언트 초기화"""
        if self._client is None:
            from supabase import create_client
            from app.config import get_settings
            
            settings = get_settings()
            
            if not settings.supabase_url or not settings.supabase_service_role_key:
                raise RuntimeError(
                    "Supabase 환경변수 없음: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY"
                )
            
            self._client = create_client(
                settings.supabase_url,
                settings.supabase_service_role_key
            )
            self._initialized = True
            logger.info("✅ Supabase 클라이언트 초기화 완료 (Lazy)")
        
        return self._client
    
    def is_available(self) -> bool:
        """Supabase 사용 가능 여부 (환경변수 체크만)"""
        try:
            from app.config import get_settings
            settings = get_settings()
            return bool(settings.supabase_url and settings.supabase_service_role_key)
        except:
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Job CRUD
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def create_job(
        self,
        email: str,
        name: str,
        input_data: Dict[str, Any],
        target_year: int = 2026
    ) -> Dict[str, Any]:
        """
        Job 생성 (status='queued')
        
        Returns:
            {"id": "uuid", "access_token": "...", ...}
        """
        client = self._get_client()
        
        job_data = {
            "email": email,
            "name": name or "고객",
            "input_data": input_data,
            "target_year": target_year,
            "status": "queued",
            "progress": 0,
            "current_step": "queued",
        }
        
        result = client.table("reports").insert(job_data).execute()
        
        if not result.data:
            raise RuntimeError("Job 생성 실패")
        
        job = result.data[0]
        logger.info(f"[Supabase] Job 생성: {job['id']} | Email: {email}")
        
        return job
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Job 조회"""
        client = self._get_client()
        
        result = (
            client.table("reports")
            .select("*")
            .eq("id", job_id)
            .execute()
        )
        
        return result.data[0] if result.data else None
    
    async def get_job_by_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """토큰으로 Job 조회 (이메일 링크용)"""
        client = self._get_client()
        
        result = (
            client.table("reports")
            .select("*")
            .eq("access_token", access_token)
            .execute()
        )
        
        return result.data[0] if result.data else None
    
    async def update_progress(
        self,
        job_id: str,
        progress: int,
        step: str,
        status: str = "generating"
    ) -> None:
        """진행 상태 업데이트"""
        client = self._get_client()
        
        client.table("reports").update({
            "status": status,
            "progress": progress,
            "current_step": step,
        }).eq("id", job_id).execute()
        
        logger.debug(f"[Supabase] Progress: {job_id} → {progress}% ({step})")
    
    async def save_section(
        self,
        job_id: str,
        section_id: str,
        section_title: str,
        section_order: int,
        content_json: Dict[str, Any],
        char_count: int = 0,
        elapsed_ms: int = 0
    ) -> None:
        """섹션 결과 저장"""
        client = self._get_client()
        
        # Upsert (이미 있으면 업데이트)
        section_data = {
            "report_id": job_id,
            "section_id": section_id,
            "section_title": section_title,
            "section_order": section_order,
            "status": "completed",
            "content_json": content_json,
            "char_count": char_count,
            "elapsed_ms": elapsed_ms,
            "completed_at": datetime.utcnow().isoformat(),
        }
        
        # 먼저 존재 여부 확인
        existing = (
            client.table("report_sections")
            .select("id")
            .eq("report_id", job_id)
            .eq("section_id", section_id)
            .execute()
        )
        
        if existing.data:
            # 업데이트
            client.table("report_sections").update(section_data).eq(
                "report_id", job_id
            ).eq("section_id", section_id).execute()
        else:
            # 삽입
            client.table("report_sections").insert(section_data).execute()
        
        logger.info(f"[Supabase] 섹션 저장: {section_id} ({char_count}자)")
    
    async def complete_job(
        self,
        job_id: str,
        result_json: Dict[str, Any],
        markdown: str = "",
        generation_time_ms: int = 0,
        total_tokens: int = 0
    ) -> None:
        """Job 완료 처리"""
        client = self._get_client()
        
        # result_json에 markdown 추가
        if markdown:
            result_json["markdown"] = markdown
        
        client.table("reports").update({
            "status": "completed",
            "progress": 100,
            "current_step": "completed",
            "result_json": result_json,
            "completed_at": datetime.utcnow().isoformat(),
            "generation_time_ms": generation_time_ms,
            "total_tokens_used": total_tokens,
        }).eq("id", job_id).execute()
        
        logger.info(f"[Supabase] ✅ Job 완료: {job_id} ({generation_time_ms}ms)")
    
    async def fail_job(self, job_id: str, error: str) -> None:
        """Job 실패 처리"""
        client = self._get_client()
        
        # retry_count 증가
        job = await self.get_job(job_id)
        retry_count = (job.get("retry_count", 0) or 0) + 1 if job else 1
        
        client.table("reports").update({
            "status": "failed",
            "error": error[:500],
            "retry_count": retry_count,
        }).eq("id", job_id).execute()
        
        logger.error(f"[Supabase] ❌ Job 실패: {job_id} | {error[:100]}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 섹션 관리
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def get_sections(self, job_id: str) -> List[Dict[str, Any]]:
        """Job의 모든 섹션 조회"""
        client = self._get_client()
        
        result = (
            client.table("report_sections")
            .select("*")
            .eq("report_id", job_id)
            .order("section_order")
            .execute()
        )
        
        return result.data or []
    
    async def get_job_with_sections(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Job + 섹션 함께 조회"""
        job = await self.get_job(job_id)
        if not job:
            return None
        
        sections = await self.get_sections(job_id)
        job["sections"] = sections
        
        return job
    
    async def init_sections(self, job_id: str, section_specs: List[Dict]) -> None:
        """섹션 초기화 (pending 상태로)"""
        client = self._get_client()
        
        for spec in section_specs:
            section_data = {
                "report_id": job_id,
                "section_id": spec["id"],
                "section_title": spec["title"],
                "section_order": spec["order"],
                "status": "pending",
            }
            
            # 중복 방지
            existing = (
                client.table("report_sections")
                .select("id")
                .eq("report_id", job_id)
                .eq("section_id", spec["id"])
                .execute()
            )
            
            if not existing.data:
                client.table("report_sections").insert(section_data).execute()
    
    async def update_section_status(
        self,
        job_id: str,
        section_id: str,
        status: str,
        error: Optional[str] = None
    ) -> None:
        """섹션 상태 업데이트"""
        client = self._get_client()
        
        update_data = {"status": status}
        if status == "generating":
            update_data["started_at"] = datetime.utcnow().isoformat()
        if error:
            update_data["error"] = error[:500]
        
        client.table("report_sections").update(update_data).eq(
            "report_id", job_id
        ).eq("section_id", section_id).execute()
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Recovery용
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def get_jobs_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        """특정 상태의 Job 목록 (복구용)"""
        try:
            client = self._get_client()
            
            result = (
                client.table("reports")
                .select("id, email, status, created_at, updated_at")
                .eq("status", status)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            return result.data or []
        except Exception as e:
            logger.error(f"[Supabase] get_jobs_by_status 실패: {e}")
            return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 스펙 (7개 섹션)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION_SPECS = [
    {"id": "exec", "title": "Executive Summary", "order": 1},
    {"id": "money", "title": "Money & Cashflow", "order": 2},
    {"id": "business", "title": "Business Strategy", "order": 3},
    {"id": "team", "title": "Team & Partner", "order": 4},
    {"id": "health", "title": "Health & Performance", "order": 5},
    {"id": "calendar", "title": "12-Month Calendar", "order": 6},
    {"id": "sprint", "title": "90-Day Sprint", "order": 7},
]


# 싱글톤 인스턴스
supabase_service = SupabaseService()
