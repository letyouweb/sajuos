"""
Reports API Router v3 - 프리미엄 리포트 API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P0/P1 요구사항:
- POST /reports/start → 즉시 job_id 반환
- GET /reports/{job_id} → 폴링용 상태 조회
- Supabase 영속화 (Lazy-init)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any, List
import logging

from app.services.supabase_service import supabase_service, SECTION_SPECS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Request/Response Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ReportStartRequest(BaseModel):
    """리포트 생성 요청"""
    email: EmailStr
    name: str = "고객"
    
    # 사주 데이터
    saju_result: Optional[Dict[str, Any]] = None
    year_pillar: Optional[str] = None
    month_pillar: Optional[str] = None
    day_pillar: Optional[str] = None
    hour_pillar: Optional[str] = None
    
    # 분석 옵션
    target_year: int = 2026
    question: str = ""
    concern_type: str = "career"
    
    # 7문항 설문
    survey_data: Optional[Dict[str, Any]] = None


class ReportStartResponse(BaseModel):
    """리포트 생성 시작 응답"""
    success: bool
    job_id: str
    status: str
    message: str
    poll_url: str


class ReportStatusResponse(BaseModel):
    """진행 상태 응답"""
    job_id: str
    status: str  # queued, generating, completed, failed
    progress: int  # 0-100
    current_step: str
    sections: List[Dict[str, Any]]
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/start", response_model=ReportStartResponse)
async def start_report_generation(
    payload: ReportStartRequest,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    🎯 프리미엄 리포트 생성 시작
    
    - 즉시 job_id 반환
    - 백그라운드에서 생성 진행
    - GET /reports/{job_id}로 폴링
    - 완료 시 이메일 발송
    """
    # 입력 데이터 구성
    input_data = {
        "question": payload.question,
        "concern_type": payload.concern_type,
    }
    
    if payload.survey_data:
        input_data["survey_data"] = payload.survey_data
    
    if payload.saju_result:
        input_data["saju_result"] = payload.saju_result
    else:
        input_data.update({
            "year_pillar": payload.year_pillar,
            "month_pillar": payload.month_pillar,
            "day_pillar": payload.day_pillar,
            "hour_pillar": payload.hour_pillar,
        })
    
    try:
        # Supabase에 Job 생성 (status='queued')
        job = await supabase_service.create_job(
            email=payload.email,
            name=payload.name,
            input_data=input_data,
            target_year=payload.target_year
        )
        
        job_id = job["id"]
        
        # 섹션 초기화
        await supabase_service.init_sections(job_id, SECTION_SPECS)
        
        logger.info(f"[Reports] Job 생성: {job_id} | Email: {payload.email}")
        
        # RuleStore 가져오기
        rulestore = getattr(request.app.state, "rulestore", None)
        
        # 백그라운드 작업 등록
        from app.services.report_worker import report_worker
        background_tasks.add_task(
            report_worker.run_job,
            job_id=job_id,
            rulestore=rulestore
        )
        
        return ReportStartResponse(
            success=True,
            job_id=job_id,
            status="queued",
            message="리포트 생성이 시작되었습니다.",
            poll_url=f"/api/reports/{job_id}"
        )
        
    except Exception as e:
        logger.error(f"[Reports] 생성 시작 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/{job_id}", response_model=ReportStatusResponse)
async def get_report_status(job_id: str):
    """
    📊 리포트 상태 조회 (폴링용)
    
    - 2~3초 간격으로 폴링 권장
    - completed 시 result 포함
    """
    job = await supabase_service.get_job_with_sections(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    
    # 섹션 정보 포맷팅
    sections = []
    for section in job.get("sections", []):
        sections.append({
            "id": section["section_id"],
            "title": section["section_title"],
            "status": section["status"],
            "order": section["section_order"],
        })
    
    response = ReportStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        current_step=job.get("current_step", ""),
        sections=sections,
        error=job.get("error"),
    )
    
    # 완료 시 결과 포함
    if job["status"] == "completed" and job.get("result_json"):
        response.result = job["result_json"]
    
    return response


@router.get("/{job_id}/result")
async def get_report_result(job_id: str):
    """
    📄 완료된 리포트 결과 조회
    """
    job = await supabase_service.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    
    if job["status"] != "completed":
        return JSONResponse(content={
            "completed": False,
            "status": job["status"],
            "progress": job["progress"],
            "message": "리포트가 아직 생성 중입니다."
        })
    
    return JSONResponse(content={
        "completed": True,
        "job_id": job_id,
        "result": job["result_json"],
        "pdf_url": job.get("pdf_url"),
        "generated_at": job.get("completed_at"),
    })


@router.get("/view/{access_token}")
async def view_report_by_token(access_token: str):
    """
    🔗 토큰 기반 리포트 조회 (이메일 링크용)
    """
    job = await supabase_service.get_job_by_token(access_token)
    
    if not job:
        raise HTTPException(status_code=404, detail="유효하지 않은 링크입니다.")
    
    if job["status"] != "completed":
        return JSONResponse(content={
            "completed": False,
            "status": job["status"],
            "progress": job["progress"],
            "message": "리포트가 아직 생성 중입니다."
        })
    
    return JSONResponse(content={
        "completed": True,
        "job_id": job["id"],
        "result": job["result_json"],
        "name": job.get("name"),
        "target_year": job.get("target_year"),
    })


@router.post("/{job_id}/retry")
async def retry_report_generation(
    job_id: str,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    🔄 실패한 리포트 재시도
    """
    job = await supabase_service.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    
    if job["status"] not in ["failed", "generating"]:
        raise HTTPException(
            status_code=400,
            detail=f"재시도 불가 상태: {job['status']}"
        )
    
    # 상태 리셋
    await supabase_service.update_progress(job_id, 0, "retry", "queued")
    
    # RuleStore 가져오기
    rulestore = getattr(request.app.state, "rulestore", None)
    
    # 재시도 시작
    from app.services.report_worker import report_worker
    background_tasks.add_task(
        report_worker.run_job,
        job_id=job_id,
        rulestore=rulestore
    )
    
    return JSONResponse(content={
        "success": True,
        "job_id": job_id,
        "message": "재시도가 시작되었습니다."
    })


@router.get("/{job_id}/sections")
async def get_report_sections(job_id: str):
    """
    📋 리포트 섹션 상세 조회
    """
    job = await supabase_service.get_job_with_sections(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    
    return JSONResponse(content={
        "job_id": job_id,
        "status": job["status"],
        "sections": job.get("sections", [])
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸리티
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/sections-info")
async def get_sections_info():
    """섹션 정보 조회"""
    return JSONResponse(content={
        "total_sections": len(SECTION_SPECS),
        "sections": SECTION_SPECS
    })
