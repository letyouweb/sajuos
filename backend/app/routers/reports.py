"""
Reports API Router v5 - Emergency Fix
"""
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Request/Response Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ReportStartRequest(BaseModel):
    email: EmailStr
    name: str = "고객"
    saju_result: Optional[Dict[str, Any]] = None
    year_pillar: Optional[str] = None
    month_pillar: Optional[str] = None
    day_pillar: Optional[str] = None
    hour_pillar: Optional[str] = None
    target_year: int = 2026
    question: str = ""
    concern_type: str = "career"
    survey_data: Optional[Dict[str, Any]] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Supabase Lazy Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_supabase():
    """Lazy import - 호출 시점에만 로드"""
    try:
        from app.services.supabase_service import supabase_service
        return supabase_service
    except Exception as e:
        logger.error(f"Supabase import 실패: {e}")
        return None


SECTION_SPECS = [
    {"id": "exec", "title": "Executive Summary", "order": 1},
    {"id": "money", "title": "Money & Cashflow", "order": 2},
    {"id": "business", "title": "Business Strategy", "order": 3},
    {"id": "team", "title": "Team & Partner", "order": 4},
    {"id": "health", "title": "Health & Performance", "order": 5},
    {"id": "calendar", "title": "12-Month Calendar", "order": 6},
    {"id": "sprint", "title": "90-Day Sprint", "order": 7},
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@router.post("/start")
async def start_report(
    payload: ReportStartRequest,
    background_tasks: BackgroundTasks,
    request: Request
):
    """리포트 생성 시작"""
    input_data = {
        "question": payload.question,
        "concern_type": payload.concern_type,
        "survey_data": payload.survey_data,
        "saju_result": payload.saju_result,
        "year_pillar": payload.year_pillar,
        "month_pillar": payload.month_pillar,
        "day_pillar": payload.day_pillar,
        "hour_pillar": payload.hour_pillar,
    }
    
    supabase = get_supabase()
    
    if supabase and supabase.is_available():
        try:
            job = await supabase.create_job(
                email=payload.email,
                name=payload.name,
                input_data=input_data,
                target_year=payload.target_year
            )
            job_id = job["id"]
            
            await supabase.init_sections(job_id, SECTION_SPECS)
            
            # 백그라운드 작업
            rulestore = getattr(request.app.state, "rulestore", None)
            background_tasks.add_task(run_report_job, job_id, rulestore)
            
            return {
                "success": True,
                "job_id": job_id,
                "status": "queued",
                "message": "리포트 생성이 시작되었습니다.",
                "poll_url": f"/api/reports/{job_id}"
            }
        except Exception as e:
            logger.error(f"Job 생성 실패: {e}")
            raise HTTPException(status_code=500, detail=str(e)[:200])
    else:
        # Supabase 없으면 임시 ID 반환
        import uuid
        temp_id = str(uuid.uuid4())
        return {
            "success": True,
            "job_id": temp_id,
            "status": "queued",
            "message": "리포트 생성 시작 (Supabase 미연결)",
            "poll_url": f"/api/reports/{temp_id}"
        }


@router.get("/{job_id}")
async def get_report_status(job_id: str):
    """폴링용 상태 조회"""
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        return {
            "job_id": job_id,
            "status": "unknown",
            "progress": 0,
            "message": "Supabase 미연결"
        }
    
    try:
        job = await supabase.get_job_with_sections(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return {
            "job_id": job_id,
            "status": job["status"],
            "progress": job["progress"],
            "current_step": job.get("current_step", ""),
            "sections": [
                {"id": s["section_id"], "status": s["status"]}
                for s in job.get("sections", [])
            ],
            "error": job.get("error"),
            "result": job.get("result_json") if job["status"] == "completed" else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:100])


@router.get("/{job_id}/result")
async def get_report_result(job_id: str):
    """완료된 리포트 결과"""
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        raise HTTPException(status_code=503, detail="Supabase 미연결")
    
    job = await supabase.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] != "completed":
        return {"completed": False, "status": job["status"], "progress": job["progress"]}
    
    return {"completed": True, "result": job["result_json"]}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 백그라운드 작업
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def run_report_job(job_id: str, rulestore):
    """백그라운드 리포트 생성"""
    try:
        from app.services.report_worker import report_worker
        await report_worker.run_job(job_id, rulestore)
    except Exception as e:
        logger.error(f"Report job 실패: {job_id} | {e}")
        supabase = get_supabase()
        if supabase:
            try:
                await supabase.fail_job(job_id, str(e))
            except:
                pass
