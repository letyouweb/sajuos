"""
Supabase Service v9 - DB 스키마 완전 일치
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
report_jobs: id, user_email, input_json, status, progress, current_step, result_json, markdown, error, public_token
report_sections: id, job_id, section_id, status, progress, raw_json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


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
    _client = None
    
    def _get_client(self):
        if self._client is None:
            from supabase import create_client
            url = os.getenv("SUPABASE_URL", "")
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            if not url or not key:
                raise RuntimeError("SUPABASE_URL/KEY 없음")
            self._client = create_client(url, key)
            logger.info("✅ Supabase 연결")
        return self._client
    
    def is_available(self) -> bool:
        return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    
    async def create_job(self, email: str, name: str = "", input_data: Dict = None, target_year: int = 2026) -> Dict:
        """Job 생성"""
        client = self._get_client()
        
        # 🔥 input_data를 input_json 컬럼에 저장
        data = {
            "user_email": email,
            "input_json": input_data or {},  # 여기에 name, target_year 등 포함
            "status": "queued",
            "progress": 0,
            "current_step": "queued"
        }
        
        result = client.table("report_jobs").insert(data).execute()
        
        if not result.data:
            raise RuntimeError("Job 생성 실패")
        
        job = result.data[0]
        logger.info(f"[Supabase] Job 생성: {job['id']}")
        return job
    
    async def get_job(self, job_id: str) -> Optional[Dict]:
        """Job 조회"""
        client = self._get_client()
        result = client.table("report_jobs").select("*").eq("id", job_id).execute()
        return result.data[0] if result.data else None
    
    async def get_job_by_token(self, token: str) -> Optional[Dict]:
        """토큰으로 Job 조회"""
        client = self._get_client()
        result = client.table("report_jobs").select("*").eq("public_token", token).execute()
        return result.data[0] if result.data else None
    
    async def update_progress(self, job_id: str, progress: int, status: str = "running"):
        """진행률 업데이트"""
        client = self._get_client()
        client.table("report_jobs").update({
            "status": status,
            "progress": progress,
            "current_step": status
        }).eq("id", job_id).execute()
    
    async def complete_job(self, job_id: str, result_json: Dict = None, markdown: str = ""):
        """Job 완료"""
        client = self._get_client()
        data = {
            "status": "completed",
            "progress": 100,
            "current_step": "completed"
        }
        if result_json:
            data["result_json"] = result_json
        if markdown:
            data["markdown"] = markdown
        
        client.table("report_jobs").update(data).eq("id", job_id).execute()
        logger.info(f"[Supabase] ✅ Job 완료: {job_id}")
    
    async def fail_job(self, job_id: str, error: str):
        """Job 실패"""
        client = self._get_client()
        client.table("report_jobs").update({
            "status": "failed",
            "current_step": "failed",
            "error": error[:500]
        }).eq("id", job_id).execute()
        logger.error(f"[Supabase] ❌ Job 실패: {job_id}")
    
    async def save_section(self, job_id: str, section_id: str, content_json: Dict = None):
        """섹션 저장"""
        client = self._get_client()
        
        existing = client.table("report_sections").select("id").eq(
            "job_id", job_id).eq("section_id", section_id).execute()
        
        data = {
            "job_id": job_id,
            "section_id": section_id,
            "status": "completed",
            "progress": 100
        }
        if content_json:
            data["raw_json"] = content_json
        
        if existing.data:
            client.table("report_sections").update(data).eq(
                "job_id", job_id).eq("section_id", section_id).execute()
        else:
            client.table("report_sections").insert(data).execute()
        
        logger.info(f"[Supabase] 섹션 저장: {section_id}")
    
    async def get_sections(self, job_id: str) -> List[Dict]:
        """섹션 조회"""
        client = self._get_client()
        result = client.table("report_sections").select("*").eq("job_id", job_id).execute()
        return result.data or []
    
    async def get_job_with_sections(self, job_id: str) -> Optional[Dict]:
        """Job + 섹션"""
        job = await self.get_job(job_id)
        if job:
            job["sections"] = await self.get_sections(job_id)
        return job
    
    async def init_sections(self, job_id: str, specs: List[Dict]):
        """섹션 초기화"""
        client = self._get_client()
        for spec in specs:
            try:
                existing = client.table("report_sections").select("id").eq(
                    "job_id", job_id).eq("section_id", spec["id"]).execute()
                if not existing.data:
                    client.table("report_sections").insert({
                        "job_id": job_id,
                        "section_id": spec["id"],
                        "status": "pending",
                        "progress": 0
                    }).execute()
            except Exception as e:
                logger.warning(f"섹션 초기화 스킵: {spec['id']} | {e}")
    
    async def update_section_status(self, job_id: str, section_id: str, status: str, error: str = None):
        """섹션 상태 업데이트"""
        client = self._get_client()
        data = {"status": status}
        client.table("report_sections").update(data).eq(
            "job_id", job_id).eq("section_id", section_id).execute()
    
    async def get_jobs_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        """상태별 Job 조회"""
        try:
            client = self._get_client()
            result = client.table("report_jobs").select("*").eq(
                "status", status).order("created_at", desc=True).limit(limit).execute()
            return result.data or []
        except:
            return []


supabase_service = SupabaseService()
