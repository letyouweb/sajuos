"""
Reports API Router v9 - 집계(Aggregation) 응답 + full_markdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P0 핵심 수정:
1) /view/{job_id} → job + sections + full_markdown 집계 반환
2) sections 순서 강제: exec/money/business/team/health/calendar/sprint
3) 각 section에 markdown 필드 포함
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


# 🔥 섹션 순서 강제
SECTION_ORDER = ["exec", "money", "business", "team", "health", "calendar", "sprint"]

SECTION_SPECS = [
    {"id": "exec", "title": "Executive Summary", "order": 1},
    {"id": "money", "title": "Money & Cashflow", "order": 2},
    {"id": "business", "title": "Business Strategy", "order": 3},
    {"id": "team", "title": "Team & Partner", "order": 4},
    {"id": "health", "title": "Health & Performance", "order": 5},
    {"id": "calendar", "title": "12-Month Calendar", "order": 6},
    {"id": "sprint", "title": "90-Day Sprint", "order": 7},
]


def get_section_title(section_id: str) -> str:
    """section_id로 title 조회"""
    for spec in SECTION_SPECS:
        if spec["id"] == section_id:
            return spec["title"]
    return section_id or "Unknown"


def extract_markdown_from_section(section: Dict) -> str:
    """섹션에서 markdown 추출 (여러 소스에서 시도)"""
    # 1) 직접 markdown 필드
    if section.get("markdown"):
        return section["markdown"]
    
    # 2) content 필드
    if section.get("content"):
        return section["content"]
    
    # 3) raw_json에서 추출
    raw_json = section.get("raw_json") or {}
    
    # 3-1) body_markdown
    if raw_json.get("body_markdown"):
        return raw_json["body_markdown"]
    
    # 3-2) content
    if raw_json.get("content"):
        return raw_json["content"]
    
    # 3-3) JSON 전체를 마크다운으로 변환
    if raw_json:
        return build_markdown_from_raw_json(section.get("section_id", ""), raw_json)
    
    return ""


def build_markdown_from_raw_json(section_id: str, raw_json: Dict) -> str:
    """raw_json을 마크다운으로 변환"""
    lines = []
    title = raw_json.get("title") or get_section_title(section_id)
    lines.append(f"## {title}\n")
    
    # body_markdown이 있으면 우선 사용
    if raw_json.get("body_markdown"):
        lines.append(raw_json["body_markdown"])
        return "\n".join(lines)
    
    # diagnosis
    diagnosis = raw_json.get("diagnosis")
    if diagnosis:
        lines.append("### 진단")
        if diagnosis.get("current_state"):
            lines.append(f"**현재 상태**: {diagnosis['current_state']}")
        if diagnosis.get("key_issues"):
            lines.append("**핵심 이슈**:")
            for issue in diagnosis["key_issues"]:
                lines.append(f"- {issue}")
        lines.append("")
    
    # hypotheses
    hypotheses = raw_json.get("hypotheses") or []
    if hypotheses:
        lines.append("### 가설")
        for h in hypotheses:
            lines.append(f"- **{h.get('id', '')}**: {h.get('statement', '')} (신뢰도: {h.get('confidence', '')})")
        lines.append("")
    
    # strategy_options
    options = raw_json.get("strategy_options") or []
    if options:
        lines.append("### 전략 옵션")
        for opt in options:
            lines.append(f"#### {opt.get('name', '')}")
            lines.append(opt.get('description', ''))
            if opt.get('pros'):
                lines.append("**장점**: " + ", ".join(opt['pros']))
            if opt.get('cons'):
                lines.append("**단점**: " + ", ".join(opt['cons']))
        lines.append("")
    
    # recommended_strategy
    rec = raw_json.get("recommended_strategy")
    if rec:
        lines.append("### 추천 전략")
        lines.append(f"**선택**: {rec.get('selected_option', '')}")
        lines.append(f"**근거**: {rec.get('rationale', '')}")
        if rec.get("execution_plan"):
            lines.append("**실행 계획**:")
            for plan in rec["execution_plan"]:
                lines.append(f"- Week {plan.get('week', '')}: {plan.get('focus', '')} - {', '.join(plan.get('actions', []))}")
        lines.append("")
    
    # kpis
    kpis = raw_json.get("kpis") or []
    if kpis:
        lines.append("### KPI")
        for kpi in kpis:
            lines.append(f"- **{kpi.get('metric', '')}**: 목표 {kpi.get('target', '')} (현재: {kpi.get('current', '')})")
        lines.append("")
    
    # risks
    risks = raw_json.get("risks") or []
    if risks:
        lines.append("### 리스크")
        for risk in risks:
            lines.append(f"- **{risk.get('risk', '')}**: 확률 {risk.get('probability', '')}, 영향 {risk.get('impact', '')}")
            lines.append(f"  대응: {risk.get('mitigation', '')}")
        lines.append("")
    
    # Calendar 전용
    if section_id == "calendar":
        if raw_json.get("annual_theme"):
            lines.append(f"### 연간 테마\n{raw_json['annual_theme']}\n")
        monthly = raw_json.get("monthly_plans") or []
        if monthly:
            lines.append("### 월별 계획")
            for m in monthly:
                lines.append(f"#### {m.get('month_name', m.get('month', ''))}월")
                lines.append(f"- 테마: {m.get('theme', '')}")
                lines.append(f"- 에너지: {m.get('energy_level', '')}")
                lines.append(f"- 핵심: {m.get('key_focus', '')}")
                if m.get('recommended_actions'):
                    lines.append(f"- 액션: {', '.join(m['recommended_actions'])}")
            lines.append("")
    
    # Sprint 전용
    if section_id == "sprint":
        if raw_json.get("mission_statement"):
            lines.append(f"### 미션\n{raw_json['mission_statement']}\n")
        
        for phase_key in ["phase_1_offer", "phase_2_funnel", "phase_3_content", "phase_4_automation"]:
            phase = raw_json.get(phase_key)
            if phase:
                lines.append(f"### {phase.get('theme', phase_key)}")
                lines.append(f"- 기간: {phase.get('weeks', '')}")
                if phase.get('goals'):
                    lines.append(f"- 목표: {', '.join(phase['goals'])}")
                if phase.get('deliverables'):
                    lines.append(f"- 산출물: {', '.join(phase['deliverables'])}")
                if phase.get('kpis'):
                    lines.append(f"- KPI: {', '.join(phase['kpis'])}")
                lines.append("")
        
        milestones = raw_json.get("milestones")
        if milestones:
            lines.append("### 마일스톤")
            for day_key in ["day_30", "day_60", "day_90"]:
                m = milestones.get(day_key)
                if m:
                    lines.append(f"- **{day_key.replace('_', ' ').title()}**: {m.get('goal', '')} (목표 매출: {m.get('revenue_target', '')})")
            lines.append("")
    
    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 디버그 엔드포인트 (DB 직접 확인용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/debug/{job_id}")
async def debug_job(job_id: str):
    """
    🔥 디버그용: DB에서 직접 job + sections 조회
    브라우저에서 확인: https://api.sajuos.com/api/v1/reports/debug/{job_id}
    """
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        return {"error": "Supabase 미연결"}
    
    # 1) Job 조회
    job = await supabase.get_job(job_id)
    if not job:
        return {"error": f"Job not found: {job_id}"}
    
    # 2) Sections 조회 (raw)
    sections_raw = await supabase.get_sections(job_id)
    
    # 3) 각 섹션의 raw_json 구조 확인
    sections_debug = []
    for s in sections_raw:
        raw_json = s.get("raw_json") or {}
        sections_debug.append({
            "section_id": s.get("section_id"),
            "status": s.get("status"),
            "has_raw_json": bool(raw_json),
            "raw_json_keys": list(raw_json.keys()) if raw_json else [],
            "has_body_markdown": bool(raw_json.get("body_markdown")),
            "body_markdown_length": len(raw_json.get("body_markdown", "")),
            "body_markdown_preview": (raw_json.get("body_markdown", ""))[:200] + "..." if raw_json.get("body_markdown") else None,
        })
    
    return {
        "job_id": job_id,
        "job_status": job.get("status"),
        "job_progress": job.get("progress"),
        "sections_count": len(sections_raw),
        "sections_debug": sections_debug,
        "has_result_json": bool(job.get("result_json")),
        "has_markdown": bool(job.get("markdown")),
    }


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
    # 🔥 P0: input_json에 saju_result 포함 (이메일 링크에서도 birth/time 표시 가능)
    input_data = {
        "name": payload.name,
        "question": payload.question,
        "concern_type": payload.concern_type,
        "target_year": payload.target_year,
        "survey_data": payload.survey_data,
        "saju_result": payload.saju_result,  # 🔥 핵심: 사주 계산 결과 저장
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
            public_token = job.get("public_token")
            
            logger.info(f"[Reports] Job 생성 완료: {job_id}, token={public_token[:8] if public_token else 'NULL'}...")
            
            # 섹션 초기화
            try:
                await supabase.init_sections(job_id, SECTION_SPECS)
            except Exception as e:
                logger.warning(f"섹션 초기화 스킵: {e}")
            
            # 백그라운드 작업
            rulestore = getattr(request.app.state, "rulestore", None)
            background_tasks.add_task(run_report_job, job_id, rulestore)
            
            # 🔥 P0: 표준화된 응답 (job_id, token, view_url)
            return {
                "success": True,
                "job_id": job_id,
                "token": public_token,
                "status": "queued",
                "message": "리포트 생성이 시작되었습니다.",
                "view_url": f"https://sajuos.com/report/{job_id}?token={public_token}",
                "status_url": f"https://api.sajuos.com/api/v1/reports/{job_id}/status",
                "result_url": f"https://api.sajuos.com/api/v1/reports/{job_id}/result",
            }
        except Exception as e:
            logger.error(f"Job 생성 실패: {e}")
            raise HTTPException(status_code=500, detail=str(e)[:300])
    else:
        temp_id = str(uuid.uuid4())
        return {
            "success": True,
            "job_id": temp_id,
            "status": "queued",
            "message": "리포트 생성 시작 (Supabase 미연결)",
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
async def view_report(job_id: str, token: str = Query(..., description="Access token")):
    """
    🔥🔥🔥 P0 핵심: job + sections + full_markdown 집계 반환
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
    
    # 1) token 검증 (report_jobs.id + public_token)
    is_valid, job = await supabase.verify_job_token(job_id, token)
    
    if not is_valid or not job:
        raise HTTPException(status_code=404, detail="Invalid token or job not found")
    
    # 2) sections 전부 조회
    sections_raw = await supabase.get_sections(job_id)
    
    # 3) 섹션 순서 정렬: exec/money/business/team/health/calendar/sprint
    sections_sorted = sorted(
        sections_raw or [],
        key=lambda x: SECTION_ORDER.index(x.get("section_id", "")) if x.get("section_id") in SECTION_ORDER else 999
    )
    
    # 4) 각 섹션에 markdown 추가 + 정규화
    sections_normalized = []
    for s in sections_sorted:
        section_id = s.get("section_id", "")
        raw_json = s.get("raw_json") or {}
        markdown = extract_markdown_from_section(s)
        
        sections_normalized.append({
            "section_id": section_id,
            "id": section_id,  # 호환성
            "title": get_section_title(section_id),
            "status": s.get("status", "pending"),
            "order": SECTION_ORDER.index(section_id) + 1 if section_id in SECTION_ORDER else 99,
            # 🔥 핵심: markdown 필드!
            "markdown": markdown,
            "content": markdown,  # 호환성
            "body_markdown": markdown,  # 호환성
            # raw_json 전체 (프론트에서 상세 데이터 필요시)
            "raw_json": raw_json,
            # 주요 필드 직접 노출 (프론트 편의)
            "confidence": raw_json.get("confidence", "MEDIUM"),
            "diagnosis": raw_json.get("diagnosis"),
            "hypotheses": raw_json.get("hypotheses"),
            "strategy_options": raw_json.get("strategy_options"),
            "recommended_strategy": raw_json.get("recommended_strategy"),
            "kpis": raw_json.get("kpis"),
            "risks": raw_json.get("risks"),
            # Calendar
            "annual_theme": raw_json.get("annual_theme"),
            "monthly_plans": raw_json.get("monthly_plans"),
            "quarterly_milestones": raw_json.get("quarterly_milestones"),
            "peak_months": raw_json.get("peak_months"),
            "risk_months": raw_json.get("risk_months"),
            # Sprint
            "mission_statement": raw_json.get("mission_statement"),
            "phase_1_offer": raw_json.get("phase_1_offer"),
            "phase_2_funnel": raw_json.get("phase_2_funnel"),
            "phase_3_content": raw_json.get("phase_3_content"),
            "phase_4_automation": raw_json.get("phase_4_automation"),
            "milestones": raw_json.get("milestones"),
            "risk_scenarios": raw_json.get("risk_scenarios"),
            # 메타
            "char_count": len(markdown),
            "error": s.get("error"),
            "updated_at": s.get("updated_at"),
        })
    
    # 5) full_markdown 생성 (프론트 단순 렌더용)
    full_markdown_parts = []
    for s in sections_normalized:
        if s.get("markdown"):
            full_markdown_parts.append(f"# {s['title']}\n\n{s['markdown']}")
    full_markdown = "\n\n---\n\n".join(full_markdown_parts)
    
    # 6) input_json (사주 데이터 - 이메일 링크에서도 birth/time 표시)
    input_json = job.get("input_json") or {}
    
    # 7) 🔥 집계 응답 반환
    return {
        "job": {
            "id": job["id"],
            "status": job.get("status"),
            "progress": job.get("progress", 0),
            "result_json": job.get("result_json"),
            "markdown": job.get("markdown"),
            "error": job.get("error"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        },
        # 🔥 P0: input_json (사주 원국 데이터 - localStorage 의존 제거)
        "input": input_json,
        # 🔥 P0 핵심: sections 배열 (7개, 정렬됨, markdown 포함)
        "sections": sections_normalized,
        # 🔥 P0: full_markdown (한 번에 렌더 가능)
        "full_markdown": full_markdown,
        # 메타
        "section_count": len(sections_normalized),
    }


@router.get("/verify/{job_id}")
async def verify_token(job_id: str, token: str = Query(..., description="Access token")):
    """job_id + token 검증 API"""
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
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 동적 경로는 마지막에!
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{job_id}/status")
async def get_job_status(job_id: str):
    """폴링용 상태 조회"""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job_id format: {job_id}")
    
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        return {"job_id": job_id, "status": "unknown", "progress": 0}
    
    try:
        job = await supabase.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        sections_data = await supabase.get_sections(job_id)
        completed = len([s for s in sections_data if s.get("status") in ("completed", "done", "success")])
        progress = max(job.get("progress", 0), int((completed / 7) * 100))
        
        return {
            "job_id": job_id,
            "status": job.get("status", "unknown"),
            "progress": progress,
            "sections": [{"id": s.get("section_id"), "status": s.get("status")} for s in sections_data],
            "error": job.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/{job_id}")
async def get_report_status(job_id: str, token: Optional[str] = Query(None)):
    """폴링용 상태 조회 (토큰 옵션)"""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job_id format: {job_id}")
    
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        return {"job_id": job_id, "status": "unknown", "progress": 0}
    
    try:
        if token:
            is_valid, job = await supabase.verify_job_token(job_id, token)
            if not is_valid:
                raise HTTPException(status_code=403, detail="Invalid token")
        else:
            job = await supabase.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        sections_data = await supabase.get_sections(job_id)
        
        return {
            "job_id": job_id,
            "status": job.get("status", "unknown"),
            "progress": job.get("progress", 0),
            "sections": [{"id": s.get("section_id"), "status": s.get("status")} for s in sections_data],
            "error": job.get("error"),
            "result": job.get("result_json") if job.get("status") == "completed" else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/{job_id}/result")
async def get_report_result(job_id: str, token: Optional[str] = Query(None)):
    """
    🔥 P0: /result도 job + sections 집계 반환 (view와 동일 구조)
    """
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job_id: {job_id}")
    
    supabase = get_supabase()
    
    if not supabase or not supabase.is_available():
        raise HTTPException(status_code=503, detail="Supabase 미연결")
    
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
    
    # 🔥 sections 조회 및 정규화 (view와 동일)
    sections_raw = await supabase.get_sections(job_id)
    sections_sorted = sorted(
        sections_raw or [],
        key=lambda x: SECTION_ORDER.index(x.get("section_id", "")) if x.get("section_id") in SECTION_ORDER else 999
    )
    
    sections_normalized = []
    for s in sections_sorted:
        section_id = s.get("section_id", "")
        raw_json = s.get("raw_json") or {}
        markdown = extract_markdown_from_section(s)
        
        sections_normalized.append({
            "section_id": section_id,
            "id": section_id,
            "title": get_section_title(section_id),
            "markdown": markdown,
            "raw_json": raw_json,
            "status": s.get("status"),
        })
    
    full_markdown = "\n\n---\n\n".join([
        f"# {s['title']}\n\n{s['markdown']}" for s in sections_normalized if s.get("markdown")
    ])
    
    input_json = job.get("input_json") or {}
    
    return {
        "completed": True,
        "job": {
            "id": job["id"],
            "status": job.get("status"),
            "result_json": job.get("result_json"),
        },
        "input": input_json,
        "sections": sections_normalized,
        "full_markdown": full_markdown,
        "result": job.get("result_json"),
        "markdown": job.get("markdown") or full_markdown,
    }


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
