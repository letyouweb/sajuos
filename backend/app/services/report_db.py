"""
Report DB Service - Supabase 기반 리포트 영구 저장
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- reports 테이블: 메인 리포트 상태/결과
- report_sections 테이블: 섹션별 저장 (재시도 시 스킵용)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from app.services.supabase_client import get_supabase_client, is_supabase_available

logger = logging.getLogger(__name__)


class ReportStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class SectionStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# 섹션 정의 (순서 중요)
SECTION_SPECS = [
    ("exec", "Executive Summary", 1),
    ("money", "Money & Cashflow", 2),
    ("business", "Business Strategy", 3),
    ("team", "Team & Partnership", 4),
    ("health", "Health & Performance", 5),
    ("calendar", "12-Month Calendar", 6),
    ("sprint", "90-Day Sprint", 7),
]


@dataclass
class ReportRecord:
    id: str
    email: str
    name: str
    status: ReportStatus
    progress: int
    current_step: Optional[str]
    result_json: Optional[Dict]
    pdf_url: Optional[str]
    error: Optional[str]
    access_token: str
    target_year: int
    created_at: datetime
    updated_at: datetime


class ReportDBService:
    """Supabase 기반 리포트 DB 서비스"""
    
    def __init__(self):
        self._client = get_supabase_client()
    
    @property
    def available(self) -> bool:
        return self._client is not None
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Reports CRUD
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def create_report(
        self,
        email: str,
        name: str,
        input_data: Dict[str, Any],
        target_year: int = 2026
    ) -> Optional[Dict]:
        """새 리포트 생성 + 섹션 초기화"""
        if not self.available:
            logger.warning("[ReportDB] Supabase 미설정 - create 스킵")
            return None
        
        try:
            # 1. reports 테이블에 삽입
            result = self._client.table("reports").insert({
                "email": email,
                "name": name,
                "input_data": input_data,
                "target_year": target_year,
                "status": ReportStatus.PENDING.value,
                "progress": 0,
                "current_step": "초기화 중..."
            }).execute()
            
            if not result.data:
                raise Exception("Insert failed - no data returned")
            
            report = result.data[0]
            report_id = report["id"]
            
            # 2. report_sections 테이블에 7개 섹션 초기화
            sections_data = [
                {
                    "report_id": report_id,
                    "section_id": sid,
                    "section_title": title,
                    "section_order": order,
                    "status": SectionStatus.PENDING.value
                }
                for sid, title, order in SECTION_SPECS
            ]
            
            self._client.table("report_sections").insert(sections_data).execute()
            
            logger.info(f"[ReportDB] ✅ 리포트 생성: {report_id}")
            return report
            
        except Exception as e:
            logger.error(f"[ReportDB] ❌ create_report 실패: {e}")
            return None
    
    async def get_report(self, report_id: str) -> Optional[Dict]:
        """리포트 조회 (ID)"""
        if not self.available:
            return None
        
        try:
            result = self._client.table("reports")\
                .select("*")\
                .eq("id", report_id)\
                .single()\
                .execute()
            return result.data
        except Exception as e:
            logger.error(f"[ReportDB] get_report 실패: {e}")
            return None
    
    async def get_report_by_token(self, access_token: str) -> Optional[Dict]:
        """리포트 조회 (access_token - 이메일 링크용)"""
        if not self.available:
            return None
        
        try:
            result = self._client.table("reports")\
                .select("*")\
                .eq("access_token", access_token)\
                .single()\
                .execute()
            return result.data
        except Exception as e:
            logger.error(f"[ReportDB] get_report_by_token 실패: {e}")
            return None
    
    async def update_report_status(
        self,
        report_id: str,
        status: ReportStatus,
        progress: int = None,
        current_step: str = None,
        error: str = None
    ) -> bool:
        """리포트 상태 업데이트"""
        if not self.available:
            return False
        
        try:
            update_data = {"status": status.value}
            if progress is not None:
                update_data["progress"] = progress
            if current_step is not None:
                update_data["current_step"] = current_step
            if error is not None:
                update_data["error"] = error
            if status == ReportStatus.COMPLETED:
                update_data["completed_at"] = datetime.utcnow().isoformat()
            
            self._client.table("reports")\
                .update(update_data)\
                .eq("id", report_id)\
                .execute()
            
            return True
        except Exception as e:
            logger.error(f"[ReportDB] update_report_status 실패: {e}")
            return False
    
    async def complete_report(
        self,
        report_id: str,
        result_json: Dict,
        pdf_url: str = None,
        generation_time_ms: int = None,
        total_tokens: int = None
    ) -> bool:
        """리포트 완료 처리"""
        if not self.available:
            return False
        
        try:
            update_data = {
                "status": ReportStatus.COMPLETED.value,
                "progress": 100,
                "current_step": "완료",
                "result_json": result_json,
                "completed_at": datetime.utcnow().isoformat()
            }
            if pdf_url:
                update_data["pdf_url"] = pdf_url
            if generation_time_ms:
                update_data["generation_time_ms"] = generation_time_ms
            if total_tokens:
                update_data["total_tokens_used"] = total_tokens
            
            self._client.table("reports")\
                .update(update_data)\
                .eq("id", report_id)\
                .execute()
            
            logger.info(f"[ReportDB] ✅ 리포트 완료: {report_id}")
            return True
        except Exception as e:
            logger.error(f"[ReportDB] complete_report 실패: {e}")
            return False
    
    async def fail_report(self, report_id: str, error: str) -> bool:
        """리포트 실패 처리"""
        if not self.available:
            return False
        
        try:
            # retry_count 증가
            report = await self.get_report(report_id)
            retry_count = (report.get("retry_count", 0) if report else 0) + 1
            
            self._client.table("reports")\
                .update({
                    "status": ReportStatus.FAILED.value,
                    "error": error[:500],
                    "retry_count": retry_count
                })\
                .eq("id", report_id)\
                .execute()
            
            logger.error(f"[ReportDB] ❌ 리포트 실패: {report_id} | {error[:100]}")
            return True
        except Exception as e:
            logger.error(f"[ReportDB] fail_report 실패: {e}")
            return False
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sections CRUD
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def get_sections(self, report_id: str) -> List[Dict]:
        """리포트의 모든 섹션 조회"""
        if not self.available:
            return []
        
        try:
            result = self._client.table("report_sections")\
                .select("*")\
                .eq("report_id", report_id)\
                .order("section_order")\
                .execute()
            return result.data or []
        except Exception as e:
            logger.error(f"[ReportDB] get_sections 실패: {e}")
            return []
    
    async def update_section_status(
        self,
        report_id: str,
        section_id: str,
        status: SectionStatus,
        error: str = None
    ) -> bool:
        """섹션 상태 업데이트"""
        if not self.available:
            return False
        
        try:
            update_data = {"status": status.value}
            if status == SectionStatus.GENERATING:
                update_data["started_at"] = datetime.utcnow().isoformat()
                update_data["attempt_count"] = self._client.table("report_sections")\
                    .select("attempt_count")\
                    .eq("report_id", report_id)\
                    .eq("section_id", section_id)\
                    .single()\
                    .execute().data.get("attempt_count", 0) + 1
            if error:
                update_data["error"] = error[:500]
            
            self._client.table("report_sections")\
                .update(update_data)\
                .eq("report_id", report_id)\
                .eq("section_id", section_id)\
                .execute()
            
            return True
        except Exception as e:
            logger.error(f"[ReportDB] update_section_status 실패: {e}")
            return False
    
    async def complete_section(
        self,
        report_id: str,
        section_id: str,
        content_json: Dict,
        char_count: int = 0,
        rulecard_count: int = 0,
        elapsed_ms: int = 0
    ) -> bool:
        """섹션 완료 처리"""
        if not self.available:
            return False
        
        try:
            self._client.table("report_sections")\
                .update({
                    "status": SectionStatus.COMPLETED.value,
                    "content_json": content_json,
                    "char_count": char_count,
                    "rulecard_count": rulecard_count,
                    "elapsed_ms": elapsed_ms,
                    "completed_at": datetime.utcnow().isoformat()
                })\
                .eq("report_id", report_id)\
                .eq("section_id", section_id)\
                .execute()
            
            logger.info(f"[ReportDB] ✅ 섹션 완료: {report_id}/{section_id}")
            return True
        except Exception as e:
            logger.error(f"[ReportDB] complete_section 실패: {e}")
            return False
    
    async def get_completed_sections(self, report_id: str) -> List[str]:
        """완료된 섹션 ID 목록 (재시도 시 스킵용)"""
        if not self.available:
            return []
        
        try:
            result = self._client.table("report_sections")\
                .select("section_id")\
                .eq("report_id", report_id)\
                .eq("status", SectionStatus.COMPLETED.value)\
                .execute()
            return [r["section_id"] for r in (result.data or [])]
        except Exception as e:
            logger.error(f"[ReportDB] get_completed_sections 실패: {e}")
            return []
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Progress Calculation
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def calculate_progress(self, report_id: str) -> int:
        """진행률 계산 (완료 섹션 / 전체 섹션 * 100)"""
        sections = await self.get_sections(report_id)
        if not sections:
            return 0
        
        completed = sum(1 for s in sections if s["status"] == SectionStatus.COMPLETED.value)
        return int((completed / len(sections)) * 100)


# 싱글톤
report_db = ReportDBService()
