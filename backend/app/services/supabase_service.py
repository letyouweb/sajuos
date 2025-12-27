"""
Supabase Service - Job 영속화 (Lazy-init)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Lazy-init: 첫 호출 시에만 연결
- save_section(): 섹션 결과 저장
- complete_job(): 전체 완료
- get_job(): 폴링용 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 스펙
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


class SupabaseService:
    """Supabase Job 저장 서비스 (Lazy-init)"""
    
    _client = None
    
    def _get_client(self):
        """Lazy 클라이언트 초기화 - 첫 호출 시에만 연결"""
        if self._client is None:
            from supabase import create_client
            
            url = os.getenv("SUPABASE_URL", "").strip()
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            
            if not url or not key:
                raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 없음")
            
            self._client = create_client(url, key)
            logger.info("✅ Supabase 연결 완료 (Lazy-init)")
        
        return self._client
    
    def is_available(self) -> bool:
        """환경변수만 체크 (연결 안함)"""
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        return bool(url and key)
    
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
        """Job 생성"""
        client = self._get_client()
        
        result = client.table("reports").insert({
            "email": email,
            "name": name or "고객",
            "input_data": input_data,
            "target_year": target_year,
            "status": "queued",
            "progress": 0,
            "current_step": "queued",
        }).execute()
        
        if not result.data:
            raise RuntimeError("Job 생성 실패")
        
        job = result.data[0]
        logger.info(f"[Supabase] Job 생성: {job['id']}")
        return job
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Job 조회 (폴링용)"""
        client = self._get_client()
        result = client.table("reports").select("*").eq("id", job_id).execute()
        return result.data[0] if result.data else None
    
    async def get_job_by_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """토큰으로 Job 조회"""
        client = self._get_client()
        result = client.table("reports").select("*").eq("access_token", access_token).execute()
        return result.data[0] if result.data else None
    
    async def update_progress(
        self,
        job_id: str,
        progress: int,
        step: str,
        status: str = "generating"
    ) -> None:
        """진행률 업데이트"""
        client = self._get_client()
        client.table("reports").update({
            "status": status,
            "progress": progress,
            "current_step": step,
        }).eq("id", job_id).execute()
    
    async def complete_job(
        self,
        job_id: str,
        result_json: Dict[str, Any],
        markdown: str = "",
        generation_time_ms: int = 0
    ) -> None:
        """Job 완료"""
        client = self._get_client()
        
        if markdown:
            result_json["markdown"] = markdown
        
        client.table("reports").update({
            "status": "completed",
            "progress": 100,
            "current_step": "completed",
            "result_json": result_json,
            "completed_at": datetime.utcnow().isoformat(),
            "generation_time_ms": generation_time_ms,
        }).eq("id", job_id).execute()
        
        logger.info(f"[Supabase] ✅ Job 완료: {job_id}")
    
    async def fail_job(self, job_id: str, error: str) -> None:
        """Job 실패"""
        client = self._get_client()
        client.table("reports").update({
            "status": "failed",
            "error": error[:500],
        }).eq("id", job_id).execute()
        logger.error(f"[Supabase] ❌ Job 실패: {job_id}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 섹션 저장
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
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
        """섹션 결과 저장 (upsert)"""
        client = self._get_client()
        
        data = {
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
        
        # 기존 확인
        existing = client.table("report_sections").select("id").eq(
            "report_id", job_id
        ).eq("section_id", section_id).execute()
        
        if existing.data:
            client.table("report_sections").update(data).eq(
                "report_id", job_id
            ).eq("section_id", section_id).execute()
        else:
            client.table("report_sections").insert(data).execute()
        
        logger.info(f"[Supabase] 섹션 저장: {section_id}")
    
    async def get_sections(self, job_id: str) -> List[Dict[str, Any]]:
        """Job의 모든 섹션"""
        client = self._get_client()
        result = client.table("report_sections").select("*").eq(
            "report_id", job_id
        ).order("section_order").execute()
        return result.data or []
    
    async def get_job_with_sections(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Job + 섹션"""
        job = await self.get_job(job_id)
        if not job:
            return None
        job["sections"] = await self.get_sections(job_id)
        return job
    
    async def init_sections(self, job_id: str, section_specs: List[Dict]) -> None:
        """섹션 초기화"""
        client = self._get_client()
        for spec in section_specs:
            existing = client.table("report_sections").select("id").eq(
                "report_id", job_id
            ).eq("section_id", spec["id"]).execute()
            
            if not existing.data:
                client.table("report_sections").insert({
                    "report_id": job_id,
                    "section_id": spec["id"],
                    "section_title": spec["title"],
                    "section_order": spec["order"],
                    "status": "pending",
                }).execute()
    
    async def update_section_status(
        self, job_id: str, section_id: str, status: str, error: str = None
    ) -> None:
        """섹션 상태 업데이트"""
        client = self._get_client()
        data = {"status": status}
        if error:
            data["error"] = error[:500]
        client.table("report_sections").update(data).eq(
            "report_id", job_id
        ).eq("section_id", section_id).execute()
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Recovery용
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def get_jobs_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        """특정 상태의 Job들"""
        try:
            client = self._get_client()
            result = client.table("reports").select(
                "id, email, status, created_at"
            ).eq("status", status).order("created_at", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"get_jobs_by_status 실패: {e}")
            return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 싱글톤 export (이 이름으로 import 해야 함)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
supabase_service = SupabaseService()
