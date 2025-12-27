"""
Supabase Service - Lazy Init (v5)
"""
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

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
    
    async def create_job(self, email: str, name: str, input_data: Dict, target_year: int = 2026) -> Dict:
        client = self._get_client()
        result = client.table("reports").insert({
            "email": email, "name": name or "고객",
            "input_data": input_data, "target_year": target_year,
            "status": "queued", "progress": 0, "current_step": "queued"
        }).execute()
        if not result.data:
            raise RuntimeError("Job 생성 실패")
        return result.data[0]
    
    async def get_job(self, job_id: str) -> Optional[Dict]:
        client = self._get_client()
        result = client.table("reports").select("*").eq("id", job_id).execute()
        return result.data[0] if result.data else None
    
    async def get_job_by_token(self, token: str) -> Optional[Dict]:
        client = self._get_client()
        result = client.table("reports").select("*").eq("access_token", token).execute()
        return result.data[0] if result.data else None
    
    async def update_progress(self, job_id: str, progress: int, step: str, status: str = "generating"):
        client = self._get_client()
        client.table("reports").update({
            "status": status, "progress": progress, "current_step": step
        }).eq("id", job_id).execute()
    
    async def complete_job(self, job_id: str, result_json: Dict, markdown: str = "", gen_ms: int = 0):
        client = self._get_client()
        if markdown:
            result_json["markdown"] = markdown
        client.table("reports").update({
            "status": "completed", "progress": 100, "current_step": "completed",
            "result_json": result_json, "completed_at": datetime.utcnow().isoformat(),
            "generation_time_ms": gen_ms
        }).eq("id", job_id).execute()
    
    async def fail_job(self, job_id: str, error: str):
        client = self._get_client()
        client.table("reports").update({
            "status": "failed", "error": error[:500]
        }).eq("id", job_id).execute()
    
    async def save_section(self, job_id: str, section_id: str, section_title: str,
                          section_order: int, content_json: Dict, char_count: int = 0, elapsed_ms: int = 0):
        client = self._get_client()
        data = {
            "report_id": job_id, "section_id": section_id, "section_title": section_title,
            "section_order": section_order, "status": "completed", "content_json": content_json,
            "char_count": char_count, "elapsed_ms": elapsed_ms,
            "completed_at": datetime.utcnow().isoformat()
        }
        existing = client.table("report_sections").select("id").eq(
            "report_id", job_id).eq("section_id", section_id).execute()
        if existing.data:
            client.table("report_sections").update(data).eq(
                "report_id", job_id).eq("section_id", section_id).execute()
        else:
            client.table("report_sections").insert(data).execute()
    
    async def get_sections(self, job_id: str) -> List[Dict]:
        client = self._get_client()
        result = client.table("report_sections").select("*").eq(
            "report_id", job_id).order("section_order").execute()
        return result.data or []
    
    async def get_job_with_sections(self, job_id: str) -> Optional[Dict]:
        job = await self.get_job(job_id)
        if job:
            job["sections"] = await self.get_sections(job_id)
        return job
    
    async def init_sections(self, job_id: str, specs: List[Dict]):
        client = self._get_client()
        for spec in specs:
            existing = client.table("report_sections").select("id").eq(
                "report_id", job_id).eq("section_id", spec["id"]).execute()
            if not existing.data:
                client.table("report_sections").insert({
                    "report_id": job_id, "section_id": spec["id"],
                    "section_title": spec["title"], "section_order": spec["order"],
                    "status": "pending"
                }).execute()
    
    async def update_section_status(self, job_id: str, section_id: str, status: str, error: str = None):
        client = self._get_client()
        data = {"status": status}
        if error:
            data["error"] = error[:500]
        client.table("report_sections").update(data).eq(
            "report_id", job_id).eq("section_id", section_id).execute()
    
    async def get_jobs_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        try:
            client = self._get_client()
            result = client.table("reports").select("id,email,status,created_at").eq(
                "status", status).order("created_at", desc=True).limit(limit).execute()
            return result.data or []
        except:
            return []


# 싱글톤
supabase_service = SupabaseService()
