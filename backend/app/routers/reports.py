"""
Reports API Router - 프리미엄 리포트 API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST /api/reports/start - 리포트 생성 시작
GET /api/reports/{id}/status - 진행 상태 조회
GET /api/reports/{id}/result - 완료된 결과 조회
POST /api/reports/{id}/retry - 재시도
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
import logging

from app.services.supabase_store import supabase_store, SECTION_SPECS
from app.services.report_worker import report_worker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Request/Response Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ReportStartRequest(BaseModel):
    """리포트 생성 요청"""
    email: EmailStr
    name: str = "고객"
    
    # 사주 데이터 (calculate API 결과)
    saju_result: Optional[Dict[str, Any]] = None
    
    # 또는 직접 기둥 데이터
    year_pillar: Optional[str] = None
    month_pillar: Optional[str] = None
    day_pillar: Optional[str] = None
    hour_pillar: Optional[str] = None
    
    # 분석 옵션
    target_year: int = 2026
    question: str = ""
    concern_type: str = "career"


class ReportStartResponse(BaseModel):
    """리포트 생성 시작 응답"""
    success: bool
    report_id: str
    status: str
    message: str
    status_url: str
    result_url: str


class ReportStatusResponse(BaseModel):
    """진행 상태 응답"""
    report_id: str
    status: str  # pending, generating, completed, failed
    progress: int  # 0-100
    current_step: str
    sections: list
    error: Optional[str] = None
    created_at: str
    updated_at: str


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/start", response_model=ReportStartResponse)
async def start_report_generation(
    payload: ReportStartRequest,
    background_tasks: BackgroundTasks,
    raw: Request
):
    """
    🎯 프리미엄 리포트 생성 시작
    
    - 즉시 report_id 반환
    - 백그라운드에서 생성 진행 (탭 닫아도 계속)
    - 진행 상태는 /status 엔드포인트로 폴링
    - 완료 시 이메일 발송
    """
    # 입력 데이터 구성
    input_data = {
        "question": payload.question,
        "concern_type": payload.concern_type,
    }
    
    if payload.saju_result:
        input_data["saju_result"] = payload.saju_result
    else:
        # 직접 기둥 데이터
        input_data.update({
            "year_pillar": payload.year_pillar,
            "month_pillar": payload.month_pillar,
            "day_pillar": payload.day_pillar,
            "hour_pillar": payload.hour_pillar,
        })
    
    try:
        # Supabase에 리포트 생성
        report = await supabase_store.create_report(
            email=payload.email,
            name=payload.name,
            input_data=input_data,
            target_year=payload.target_year
        )
        
        report_id = report["id"]
        
        logger.info(f"[ReportsAPI] 리포트 생성: {report_id} | Email: {payload.email}")
        
        # RuleStore 가져오기
        rulestore = getattr(raw.app.state, "rulestore", None)
        
        # 백그라운드 작업 등록
        background_tasks.add_task(
            report_worker.start_report_generation,
            report_id=report_id,
            rulestore=rulestore
        )
        
        return ReportStartResponse(
            success=True,
            report_id=report_id,
            status="pending",
            message="리포트 생성이 시작되었습니다. 완료되면 이메일로 알려드립니다.",
            status_url=f"/api/reports/{report_id}/status",
            result_url=f"/api/reports/{report_id}/result"
        )
        
    except Exception as e:
        logger.error(f"[ReportsAPI] 생성 시작 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/{report_id}/status", response_model=ReportStatusResponse)
async def get_report_status(report_id: str):
    """
    📊 리포트 진행 상태 조회
    
    - 2~3초 간격으로 폴링 권장
    - sections 배열에 각 섹션별 상태 포함
    """
    report = await supabase_store.get_report_with_sections(report_id)
    
    if not report:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    
    # 섹션 정보 포맷팅
    sections = []
    for section in report.get("sections", []):
        sections.append({
            "id": section["section_id"],
            "title": section["section_title"],
            "status": section["status"],
            "order": section["section_order"],
            "char_count": section.get("char_count", 0),
            "elapsed_ms": section.get("elapsed_ms", 0),
            "error": section.get("error"),
        })
    
    return ReportStatusResponse(
        report_id=report_id,
        status=report["status"],
        progress=report["progress"],
        current_step=report.get("current_step", ""),
        sections=sections,
        error=report.get("error"),
        created_at=report["created_at"],
        updated_at=report["updated_at"]
    )


@router.get("/{report_id}/result")
async def get_report_result(
    report_id: str,
    token: Optional[str] = Query(None, description="접근 토큰 (이메일 링크용)")
):
    """
    📄 완료된 리포트 결과 조회
    
    - token 파라미터로 접근 제어
    - 완료되지 않은 경우 현재 상태 반환
    """
    report = await supabase_store.get_report(report_id)
    
    if not report:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    
    # 토큰 검증 (선택적)
    if token and report["access_token"] != token:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    
    if report["status"] != "completed":
        # 아직 완료되지 않음
        return JSONResponse(content={
            "completed": False,
            "status": report["status"],
            "progress": report["progress"],
            "current_step": report.get("current_step", ""),
            "message": "리포트가 아직 생성 중입니다."
        })
    
    # 완료된 결과 반환
    return JSONResponse(content={
        "completed": True,
        "report_id": report_id,
        "result": report["result_json"],
        "pdf_url": report.get("pdf_url"),
        "generated_at": report.get("completed_at"),
        "generation_time_ms": report.get("generation_time_ms"),
    })


@router.get("/view/{access_token}")
async def view_report_by_token(access_token: str):
    """
    🔗 토큰 기반 리포트 조회 (이메일 링크용)
    
    - 이메일에 포함된 고유 링크로 접근
    - 로그인 없이 본인만 조회 가능
    """
    report = await supabase_store.get_report_by_token(access_token)
    
    if not report:
        raise HTTPException(status_code=404, detail="유효하지 않은 링크입니다.")
    
    if report["status"] != "completed":
        return JSONResponse(content={
            "completed": False,
            "status": report["status"],
            "progress": report["progress"],
            "message": "리포트가 아직 생성 중입니다. 완료되면 이메일로 알려드립니다."
        })
    
    return JSONResponse(content={
        "completed": True,
        "report_id": report["id"],
        "result": report["result_json"],
        "pdf_url": report.get("pdf_url"),
        "name": report.get("name"),
        "target_year": report.get("target_year"),
    })


@router.post("/{report_id}/retry")
async def retry_report_generation(
    report_id: str,
    background_tasks: BackgroundTasks,
    raw: Request
):
    """
    🔄 실패한 리포트 재시도
    
    - 완료된 섹션은 스킵
    - 실패/대기 중인 섹션만 재생성
    """
    report = await supabase_store.get_report(report_id)
    
    if not report:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    
    if report["status"] not in ["failed", "generating"]:
        raise HTTPException(
            status_code=400,
            detail=f"재시도할 수 없는 상태입니다: {report['status']}"
        )
    
    # RuleStore 가져오기
    rulestore = getattr(raw.app.state, "rulestore", None)
    
    # 재시도 시작
    background_tasks.add_task(
        report_worker.retry_report,
        report_id=report_id,
        rulestore=rulestore
    )
    
    return JSONResponse(content={
        "success": True,
        "report_id": report_id,
        "message": "재시도가 시작되었습니다."
    })


@router.get("/{report_id}/sections")
async def get_report_sections(report_id: str):
    """
    📋 리포트 섹션 상세 조회
    
    - 각 섹션별 콘텐츠 포함
    - 디버깅/관리용
    """
    report = await supabase_store.get_report_with_sections(report_id)
    
    if not report:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    
    return JSONResponse(content={
        "report_id": report_id,
        "status": report["status"],
        "sections": report.get("sections", [])
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸리티 엔드포인트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/sections-info")
async def get_sections_info():
    """섹션 정보 조회"""
    return JSONResponse(content={
        "total_sections": len(SECTION_SPECS),
        "sections": SECTION_SPECS
    })
