"""
Reports API Router v8 - 토큰 검증 API 추가
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P0 수정:
1) /verify/{job_id}?token=xxx 엔드포인트 추가
2) /{job_id}/access?token=xxx 토큰 검증 포함 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any, List
import logging
import uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


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


def get_supabase():
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
# 🔥 고정 경로 먼저 (/{job_id} 보다 위에!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/start")
async def start_report(
    payload: ReportStartRequest,
    background_tasks: BackgroundTasks,
    request: Request
):
    """리포트 생성 시작"""
    input_data = {
        "name": payload.name,
        "question": payload.question,
        "concern_type": payload.concern_type,
        "target_year": payload.target_year,
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
            public_token = job.get("public_token")  # 🔥 토큰 확인
            
            logger.info(f"[Reports] Job 생성 완료: {job_id}, token={public_token[:8] if public_token else 'NULL'}...")
            
            # 섹션 초기화 (실패해도 계속)
            try:
                await supabase.init_sections(job_id, SECTION_SPECS)
            except Exception as e:
                logger.warning(f"섹션 초기화 스킵: {e}")
            
            # 백그라운드 작업
            rulestore = getattr(request.app.state, "rulestore", None)
            
            # 🔥 RuleCards 진단 로그
            if rulestore:
                card_count = len(getattr(rulestore, 'cards', [])) if hasattr(rulestore, 'cards') else 0
                logger.info(f"[Reports] RuleStore 전달: {card_count}장, id={id(rulestore)}")
            else:
                logger.warning(f"[Reports] ⚠️ RuleStore가 None! app.state.rulestore 확인 필요")
            
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
            raise HTTPException(status_code=500, detail=str(e)[:300])
    else:
        # Supabase 없으면 임시 ID 반환
        temp_id = str(uuid.uuid4())
        return {
            "success": True,
            "job_id": temp_id,
            "status": "queued",
            "message": "리포트 생성 시작 (Supabase 미연결)",
            "poll_url": f"/api/reports/{temp_id}"
        }


@router.get("/start")
async def start_report_get():
    """GET /start는 지원하지 않음"""
    return {"error": "Use POST method", "method": "POST /api/reports/start"}


@router.get("/sections-info")
async def get_sections_info():
    """섹션 정보"""
    return {"sections": SECTION_SPECS}


@router.get("/view/{job_id}")
async def view_by_job_id(job_id: str, token: str = Query(..., description="Access token")):
    """
    🔥 P0 수정: job_id + token으로 결과 조회
    프론트엔드: /report/{job_id}?token=xxx → 백엔드: /view/{job_id}?token=xxx
    """
    # UUID 형식 체크
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job_id format: {job_id}")
    
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        raise HTTPException(status_code=503, detail="Supabase 미연결")
    
    # 🔥 핵심: id = job_id AND public_token = token
    is_valid, job = await supabase.verify_job_token(job_id, token)
    
    if not is_valid or not job:
        raise HTTPException(status_code=404, detail="Invalid token")
    
    return {
        "job_id": job["id"],
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "result": job.get("result_json") if job.get("status") == "completed" else None,
        "markdown": job.get("markdown") if job.get("status") == "completed" else None,
        "error": job.get("error") if job.get("status") == "failed" else None
    }


@router.get("/verify/{job_id}")
async def verify_token(job_id: str, token: str = Query(..., description="Access token")):
    """
    🔥 P0-1: job_id + token 검증 API
    프론트엔드에서 /report/{job_id}?token=xxx 로 호출
    """
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job_id format: {job_id}")
    
    if not token:
        raise HTTPException(status_code=400, detail="Token required")
    
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        raise HTTPException(status_code=503, detail="Supabase 미연결")
    
    is_valid, job = await supabase.verify_job_token(job_id, token)
    
    if not is_valid:
        raise HTTPException(status_code=403, detail="Invalid token")
    
    return {
        "valid": True,
        "job_id": job["id"],
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "result": job.get("result_json") if job.get("status") == "completed" else None,
        "markdown": job.get("markdown") if job.get("status") == "completed" else None,
        "error": job.get("error") if job.get("status") == "failed" else None
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 동적 경로는 마지막에!
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{job_id}/status")
async def get_job_status(job_id: str):
    """
    🔥 P0 추가: 폴링용 상태 조회 /{job_id}/status
    프론트엔드에서 호출: GET /api/v1/reports/{job_id}/status
    """
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job_id format: {job_id}")
    
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        return {"job_id": job_id, "status": "unknown", "progress": 0, "message": "Supabase 미연결"}
    
    try:
        job = await supabase.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # 섹션 정보 조회
        sections_data = await supabase.get_sections(job_id)
        
        # 진행률 계산 (섹션 기반)
        total_sections = len(SECTION_SPECS)
        completed_sections = len([s for s in sections_data if s.get("status") in ("completed", "done", "success")])
        calculated_progress = int((completed_sections / total_sections) * 100) if total_sections > 0 else 0
        
        # DB progress와 계산된 progress 중 큰 값 사용
        progress = max(job.get("progress", 0), calculated_progress)
        
        return {
            "job_id": job_id,
            "status": job.get("status", "unknown"),
            "progress": progress,
            "current_step": job.get("current_step", ""),
            "sections": [
                {
                    "id": s.get("section_id"),
                    "status": s.get("status"),
                    "error": s.get("error")
                }
                for s in sections_data
            ],
            "error": job.get("error"),
            "updated_at": job.get("updated_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/{job_id}")
async def get_report_status(job_id: str, token: Optional[str] = Query(None)):
    """
    폴링용 상태 조회
    🔥 token 파라미터가 있으면 검증 후 결과 반환
    """
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job_id format: {job_id}")
    
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        return {"job_id": job_id, "status": "unknown", "progress": 0, "message": "Supabase 미연결"}
    
    try:
        # 🔥 토큰이 있으면 검증
        if token:
            is_valid, job = await supabase.verify_job_token(job_id, token)
            if not is_valid:
                raise HTTPException(status_code=403, detail="Invalid token")
        else:
            job = await supabase.get_job_with_sections(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # 섹션 정보 (토큰 없는 경우에만 조회 - 이미 job에 없으면)
        if "sections" not in job:
            sections_data = await supabase.get_sections(job_id)
            job["sections"] = sections_data
        
        return {
            "job_id": job_id,
            "status": job.get("status", "unknown"),
            "progress": job.get("progress", 0),
            "sections": [
                {"id": s.get("section_id"), "status": s.get("status")}
                for s in job.get("sections", [])
            ],
            "error": job.get("error"),
            "result": job.get("result_json") if job.get("status") == "completed" else None,
            "markdown": job.get("markdown") if job.get("status") == "completed" else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/{job_id}/result")
async def get_report_result(job_id: str, token: Optional[str] = Query(None)):
    """완료된 리포트 결과"""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job_id: {job_id}")
    
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        raise HTTPException(status_code=503, detail="Supabase 미연결")
    
    # 🔥 토큰 검증
    if token:
        is_valid, job = await supabase.verify_job_token(job_id, token)
        if not is_valid:
            raise HTTPException(status_code=403, detail="Invalid token")
    else:
        job = await supabase.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.get("status") != "completed":
        return {"completed": False, "status": job.get("status"), "progress": job.get("progress", 0)}
    
    return {
        "completed": True, 
        "result": job.get("result_json"),
        "markdown": job.get("markdown")
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 백그라운드 작업
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_report_job(job_id: str, rulestore):
    """백그라운드 리포트 생성"""
    try:
        from app.services.report_worker import report_worker
        
        # 🔥 RuleCards 진단 로그
        if rulestore:
            card_count = len(getattr(rulestore, 'cards', [])) if hasattr(rulestore, 'cards') else 0
            logger.info(f"[RunJob] RuleStore 수신: {card_count}장, id={id(rulestore)}")
        else:
            logger.warning(f"[RunJob] ⚠️ RuleStore가 None!")
        
        await report_worker.run_job(job_id, rulestore)
    except Exception as e:
        logger.error(f"Report job 실패: {job_id} | {e}")
        supabase = get_supabase()
        if supabase:
            try:
                await supabase.fail_job(job_id, str(e))
            except:
                pass
