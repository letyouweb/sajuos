"""
/interpret endpoint - Premium Business Report Engine v4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1) 룰카드 선택 엔진: featureTags + Top-100 RuleCards
2) JSON Schema 강제: Responses API + json_schema(strict)
3) 안정성: Semaphore(2), exponential backoff, regenerate-section
4) 🔥 SSE 스트리밍: 실시간 진행 상태 + 재시도 표시
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from fastapi import APIRouter, HTTPException, Request, Query, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional, List
import logging
import asyncio
import json

from app.models.schemas import (
    InterpretRequest,
    InterpretResponse,
    ErrorResponse,
    ConcernType
)
from app.services.gpt_interpreter import gpt_interpreter
from app.services.report_builder import premium_report_builder, PREMIUM_SECTIONS
from app.services.engine_v2 import SajuManager
from app.services.job_store import job_store, JobStatus

# RuleCard pipeline
from app.services.feature_tags_no_time import build_feature_tags_no_time_from_pillars
from app.services.preset_type2 import BUSINESS_OWNER_PRESET_V2
from app.services.focus_boost import boost_preset_focus
from app.services.rulecard_selector import select_cards_for_preset

logger = logging.getLogger(__name__)
router = APIRouter()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helper Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_pillar_ganji(pillar_data) -> str:
    """사주 기둥에서 간지 문자열 추출"""
    if isinstance(pillar_data, dict):
        if pillar_data.get("ganji"):
            return pillar_data["ganji"]
        gan = pillar_data.get("gan", "")
        ji = pillar_data.get("ji", "")
        if gan and ji:
            return gan + ji
        return ""
    elif isinstance(pillar_data, str):
        return pillar_data
    return ""


def _extract_pillars_from_saju_data(saju_data: dict) -> tuple:
    """사주 데이터에서 연/월/일 간지 추출"""
    if "saju" in saju_data and isinstance(saju_data["saju"], dict):
        saju = saju_data["saju"]
        year_p = _get_pillar_ganji(saju.get("year_pillar", {}))
        month_p = _get_pillar_ganji(saju.get("month_pillar", {}))
        day_p = _get_pillar_ganji(saju.get("day_pillar", {}))
        return year_p, month_p, day_p
    
    year_p = _get_pillar_ganji(saju_data.get("year_pillar", saju_data.get("year", "")))
    month_p = _get_pillar_ganji(saju_data.get("month_pillar", saju_data.get("month", "")))
    day_p = _get_pillar_ganji(saju_data.get("day_pillar", saju_data.get("day", "")))
    
    return year_p, month_p, day_p


def _get_rulecards_and_feature_tags(
    saju_data: dict, 
    store, 
    target_year: int
) -> tuple:
    """
    사주 데이터에서 RuleCards + FeatureTags 반환
    Returns: (rulecards: List, feature_tags: List, pool_count: int)
    """
    year_p, month_p, day_p = _extract_pillars_from_saju_data(saju_data)
    
    logger.info(f"[RuleCards] 기둥 추출: 년={year_p}, 월={month_p}, 일={day_p}")
    
    if not (year_p and month_p and day_p):
        logger.warning("[RuleCards] 사주 기둥 데이터 부족")
        return [], [], 0
    
    # FeatureTags 생성
    ft = build_feature_tags_no_time_from_pillars(year_p, month_p, day_p, overlay_year=target_year)
    feature_tags = ft.get("tags", [])
    
    logger.info(f"[RuleCards] FeatureTags 생성: {len(feature_tags)}개")
    
    # Preset 부스트 및 카드 선택
    boosted = boost_preset_focus(BUSINESS_OWNER_PRESET_V2, feature_tags)
    selection = select_cards_for_preset(store, boosted, feature_tags)
    
    # 모든 카드 수집
    all_cards = []
    for sec in selection.get("sections", []):
        all_cards.extend(sec.get("cards", []))
    
    pool_count = len(all_cards)
    logger.info(f"[RuleCards] ✅ Pool={pool_count}장, FeatureTags={len(feature_tags)}개")
    
    return all_cards, feature_tags, pool_count


def inject_year_context(question: str, target_year: int) -> str:
    """연도 강제 컨텍스트 주입"""
    return f"""[분석 기준 고정]
- 이 분석은 반드시 {target_year}년 1월~12월 기준으로만 작성합니다.

[사용자 질문]
{question}""".strip()


def _extract_saju_data_from_payload(payload: InterpretRequest) -> dict:
    """payload에서 사주 데이터 추출"""
    if payload.saju_result:
        return payload.saju_result.model_dump()
    
    if not all([payload.year_pillar, payload.month_pillar, payload.day_pillar]):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "MISSING_SAJU_DATA", "message": "Saju data required"}
        )
    
    return {
        "year_pillar": payload.year_pillar,
        "month_pillar": payload.month_pillar,
        "day_pillar": payload.day_pillar,
        "hour_pillar": payload.hour_pillar,
        "day_master": payload.day_pillar[0] if payload.day_pillar else "",
        "day_master_element": ""
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post(
    "/interpret",
    response_model=InterpretResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Saju Interpretation (Legacy)"
)
async def interpret_saju(
    payload: InterpretRequest,
    raw: Request,
    mode: str = Query("auto", description="auto | direct | premium")
):
    """사주 해석 API (Legacy 단일 호출)"""
    if mode == "premium":
        return await generate_premium_report(payload, raw, mode)
    
    saju_data = _extract_saju_data_from_payload(payload)
    question = payload.question
    final_year = payload.target_year if payload.target_year else 2026
    
    store = getattr(raw.app.state, "rulestore", None)
    
    if store and mode != "direct":
        try:
            rulecards, feature_tags, pool_count = _get_rulecards_and_feature_tags(
                saju_data, store, final_year
            )
            # 레거시 모드는 컨텍스트만 추가
        except Exception as e:
            logger.warning(f"[RuleCards] 컨텍스트 생성 실패: {e}")
    
    question_with_context = inject_year_context(question, final_year)
    logger.info(f"[INTERPRET] Year={final_year} | Mode={mode}")

    try:
        result = await gpt_interpreter.interpret(
            saju_data=saju_data,
            name=payload.name,
            gender=payload.gender.value if payload.gender else None,
            concern_type=payload.concern_type,
            question=question_with_context
        )
        return result
    except Exception as e:
        logger.error(f"[INTERPRET] Error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail={"error_code": "INTERPRETATION_ERROR", "message": str(e)[:200]})


@router.post(
    "/generate-report",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="99,000원 프리미엄 30페이지 비즈니스 컨설팅 보고서"
)
async def generate_premium_report(
    payload: InterpretRequest,
    raw: Request,
    mode: str = Query("premium", description="premium | legacy")
):
    """
    🎯 99,000원 프리미엄 비즈니스 컨설팅 보고서 v4
    
    **핵심 개선사항:**
    1. 룰카드 선택 엔진: featureTags + 사업가형 태그 50개 → Top-100 RuleCards
    2. JSON Schema 강제: Responses API + json_schema(strict)
    3. 안정성: Semaphore(2), exponential backoff + jitter, 3회 재시도
    
    **응답 meta에 포함:**
    - rulecards_pool_total: 전체 룰카드 수
    - rulecards_selected_total: 선택된 룰카드 수
    - rulecards_by_section: 섹션별 selected_count, pool_count, selected_card_ids
    - feature_tags_count: 사용된 featureTags 수
    """
    if mode == "legacy":
        return await interpret_saju(payload, raw, "auto")
    
    saju_data = _extract_saju_data_from_payload(payload)
    final_year = payload.target_year if payload.target_year else 2026
    
    # RuleStore에서 RuleCards + FeatureTags 가져오기
    store = getattr(raw.app.state, "rulestore", None)
    rulecards = []
    feature_tags = []
    pool_count = 0
    
    if store:
        try:
            rulecards, feature_tags, pool_count = _get_rulecards_and_feature_tags(
                saju_data, store, final_year
            )
        except Exception as e:
            logger.warning(f"[PremiumReport] RuleCards 로드 실패: {e}")
    else:
        logger.warning("[PremiumReport] ⚠️ RuleStore 미로드")
    
    logger.info(
        f"[PREMIUM-REPORT] Year={final_year} | "
        f"RuleCards Pool={pool_count} | FeatureTags={len(feature_tags)}"
    )
    
    try:
        report = await premium_report_builder.build_premium_report(
            saju_data=saju_data,
            rulecards=rulecards,
            feature_tags=feature_tags,  # ← featureTags 전달
            target_year=final_year,
            user_question=payload.question,
            name=payload.name,
            mode="premium_business_30p"
        )
        
        return JSONResponse(content=report)
        
    except Exception as e:
        logger.error(f"[PREMIUM-REPORT] Error: {type(e).__name__}: {str(e)[:200]}")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "error_code": "REPORT_GENERATION_ERROR",
                "message": str(e)[:200],
                "target_year": final_year,
                "sections": [],
                "meta": {
                    "mode": "premium_business_30p", 
                    "error": True,
                    "rulecards_pool_total": pool_count,
                    "feature_tags_count": len(feature_tags)
                }
            }
        )


@router.post(
    "/regenerate-section",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="단일 섹션 재생성 (오류 복구용)"
)
async def regenerate_single_section(
    payload: InterpretRequest,
    raw: Request,
    section_id: str = Query(..., description="재생성할 섹션 ID (exec, money, business, team, health, calendar, sprint)")
):
    """
    🔄 단일 섹션 재생성 엔드포인트
    
    전체 리포트 재생성 없이 특정 섹션만 재생성합니다.
    "이 섹션 생성 중 오류" 발생 시 복구용으로 사용합니다.
    
    **사용 예시:**
    ```
    POST /api/v1/regenerate-section?section_id=sprint
    ```
    
    **응답 형식:**
    ```json
    {
      "success": true,
      "section": {
        "id": "sprint",
        "title": "90-Day Sprint Plan",
        "rulecard_selected": 10,
        "rulecard_pool": 480,
        "char_count": 2500,
        ...
      }
    }
    ```
    """
    # section_id 검증
    valid_sections = list(PREMIUM_SECTIONS.keys())
    if section_id not in valid_sections:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_SECTION_ID",
                "message": f"Invalid section_id: {section_id}. Valid: {valid_sections}"
            }
        )
    
    saju_data = _extract_saju_data_from_payload(payload)
    final_year = payload.target_year if payload.target_year else 2026
    
    # RuleCards + FeatureTags
    store = getattr(raw.app.state, "rulestore", None)
    rulecards = []
    feature_tags = []
    
    if store:
        try:
            rulecards, feature_tags, pool_count = _get_rulecards_and_feature_tags(
                saju_data, store, final_year
            )
        except Exception as e:
            logger.warning(f"[RegenerateSection] RuleCards 로드 실패: {e}")
    
    logger.info(
        f"[REGENERATE-SECTION] Section={section_id} | Year={final_year} | "
        f"RuleCards={len(rulecards)} | FeatureTags={len(feature_tags)}"
    )
    
    try:
        result = await premium_report_builder.regenerate_single_section(
            section_id=section_id,
            saju_data=saju_data,
            rulecards=rulecards,
            feature_tags=feature_tags,
            target_year=final_year,
            user_question=payload.question
        )
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"[REGENERATE-SECTION] Error: {type(e).__name__}: {str(e)[:200]}")
        
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "section_id": section_id,
                "error": str(e)[:500],
                "error_type": type(e).__name__
            }
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Utility Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/interpret/today", summary="Today Date (KST)")
async def get_today_context():
    today = SajuManager.get_today_kst()
    return {
        "today_kst": SajuManager.get_today_string(),
        "year": today.year,
        "month": today.month,
        "day": today.day
    }


@router.get("/interpret/cost-estimate", summary="Cost Estimate")
async def get_cost_estimate(input_tokens: int = 1500, output_tokens: int = 1000):
    return gpt_interpreter.estimate_cost(input_tokens, output_tokens)


@router.get("/interpret/concern-types", summary="Concern Types")
async def get_concern_types():
    return {
        "concern_types": [
            {"value": "love", "label": "Love/Marriage", "emoji": "💕"},
            {"value": "wealth", "label": "Wealth/Finance", "emoji": "💰"},
            {"value": "career", "label": "Career/Business", "emoji": "💼"},
            {"value": "health", "label": "Health", "emoji": "🏥"},
            {"value": "study", "label": "Study/Exam", "emoji": "📚"},
            {"value": "general", "label": "General Fortune", "emoji": "🔮"}
        ]
    }


@router.get("/interpret/rulecards-status", summary="RuleCards Status")
async def get_rulecards_status(raw: Request):
    """RuleCards 로드 상태 확인"""
    store = getattr(raw.app.state, "rulestore", None)
    if store:
        return {
            "loaded": True,
            "total_cards": len(store.cards),
            "topics": list(store.by_topic.keys())[:20],
            "topics_count": len(store.by_topic)
        }
    return {"loaded": False, "total_cards": 0, "topics": [], "topics_count": 0}


@router.get("/interpret/premium-sections", summary="Premium Report Sections Info")
async def get_premium_sections():
    """프리미엄 리포트 섹션 정보"""
    return {
        "mode": "premium_business_30p",
        "price": "99,000원",
        "total_pages": sum(s.pages for s in PREMIUM_SECTIONS.values()),
        "sections": [
            {
                "id": spec.id,
                "title": spec.title,
                "pages": spec.pages,
                "max_cards": spec.max_cards,
                "min_chars": spec.min_chars,
                "validation_type": spec.validation_type
            }
            for spec in PREMIUM_SECTIONS.values()
        ]
    }


@router.get("/interpret/gpt-test", summary="GPT API Connection Test")
async def test_gpt_connection():
    """GPT API 연결 테스트"""
    from app.config import get_settings
    from app.services.openai_key import get_openai_api_key, key_fingerprint, key_tail
    from openai import AsyncOpenAI
    import httpx
    
    settings = get_settings()
    
    try:
        api_key = get_openai_api_key()
        key_preview = f"fp={key_fingerprint(api_key)} tail={key_tail(api_key)}"
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    
    try:
        client = AsyncOpenAI(api_key=api_key, timeout=httpx.Timeout(30.0, connect=10.0))
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=20
        )
        return {
            "success": True,
            "api_key_preview": key_preview,
            "model": settings.openai_model,
            "response": resp.choices[0].message.content,
            "concurrency": settings.report_max_concurrency,
            "status": "READY_FOR_PRODUCTION"
        }
    except Exception as e:
        return {"success": False, "error_type": type(e).__name__, "error": str(e)[:200]}



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 SSE 스트리밍 API (실시간 진행 상태)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _run_report_generation(
    job_id: str,
    saju_data: dict,
    rulecards: list,
    feature_tags: list,
    target_year: int,
    user_question: str,
    name: str
):
    """백그라운드 리포트 생성 태스크"""
    try:
        await premium_report_builder.build_premium_report(
            saju_data=saju_data,
            rulecards=rulecards,
            feature_tags=feature_tags,
            target_year=target_year,
            user_question=user_question,
            name=name,
            mode="premium_business_30p",
            job_id=job_id
        )
    except Exception as e:
        logger.error(f"[AsyncReport] Job {job_id} 실패: {e}")
        await job_store.fail_job(job_id, str(e)[:500])


@router.post(
    "/generate-report-async",
    responses={400: {"model": ErrorResponse}},
    summary="🔥 비동기 프리미엄 보고서 생성 (SSE용)"
)
async def generate_report_async(
    payload: InterpretRequest,
    raw: Request,
    background_tasks: BackgroundTasks
):
    """
    🎯 비동기 프리미엄 리포트 생성 시작
    
    즉시 job_id 반환 → SSE로 진행 상태 스트리밍
    
    **응답:**
    ```json
    {
      "job_id": "abc12345",
      "status": "queued",
      "stream_url": "/api/v1/report-progress/stream?job_id=abc12345",
      "result_url": "/api/v1/report-result?job_id=abc12345"
    }
    ```
    """
    saju_data = _extract_saju_data_from_payload(payload)
    final_year = payload.target_year if payload.target_year else 2026
    
    # RuleCards + FeatureTags 준비
    store = getattr(raw.app.state, "rulestore", None)
    rulecards = []
    feature_tags = []
    
    if store:
        try:
            rulecards, feature_tags, _ = _get_rulecards_and_feature_tags(
                saju_data, store, final_year
            )
        except Exception as e:
            logger.warning(f"[AsyncReport] RuleCards 로드 실패: {e}")
    
    # Job 생성 (섹션 정보 포함)
    section_specs = [(spec.id, spec.title) for spec in PREMIUM_SECTIONS.values()]
    job_id = await job_store.create_job(section_specs)
    
    logger.info(f"[AsyncReport] Job 생성: {job_id} | Year={final_year}")
    
    # 백그라운드 태스크 등록
    background_tasks.add_task(
        _run_report_generation,
        job_id=job_id,
        saju_data=saju_data,
        rulecards=rulecards,
        feature_tags=feature_tags,
        target_year=final_year,
        user_question=payload.question,
        name=payload.name
    )
    
    return JSONResponse(content={
        "job_id": job_id,
        "status": "queued",
        "stream_url": f"/api/v1/report-progress/stream?job_id={job_id}",
        "result_url": f"/api/v1/report-result?job_id={job_id}",
        "sections": [{"id": s.id, "title": s.title} for s in PREMIUM_SECTIONS.values()]
    })


@router.get(
    "/report-progress/stream",
    summary="🔥 SSE 진행 상태 스트리밍"
)
async def stream_report_progress(
    job_id: str = Query(..., description="Job ID")
):
    """
    🎯 SSE(Server-Sent Events) 실시간 진행 상태 스트리밍
    
    **이벤트 형식:**
    ```
    event: progress
    data: {"job_id":"abc","overall":{"total":7,"done":3,"percent":42},...}
    
    event: complete
    data: {"job_id":"abc"}
    ```
    
    **프론트엔드 사용 예:**
    ```javascript
    const evtSource = new EventSource('/api/v1/report-progress/stream?job_id=abc');
    evtSource.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data);
      console.log('진행률:', data.overall.percent);
    });
    evtSource.addEventListener('complete', () => {
      evtSource.close();
      // 결과 fetch
    });
    ```
    """
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    async def event_generator():
        queue = await job_store.subscribe(job_id)
        
        try:
            # 초기 상태 전송
            initial = (await job_store.get_job(job_id))
            if initial:
                yield f"event: progress\ndata: {json.dumps(initial.to_dict())}\n\n"
            
            while True:
                try:
                    # 5초 타임아웃으로 이벤트 대기
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    
                    # 완료 신호 확인
                    if isinstance(data, dict) and data.get("type") == "complete":
                        yield f"event: complete\ndata: {json.dumps({'job_id': job_id})}\n\n"
                        break
                    
                    yield f"event: progress\ndata: {json.dumps(data)}\n\n"
                    
                except asyncio.TimeoutError:
                    # keepalive
                    yield f": keepalive\n\n"
                    
                    # Job 상태 확인
                    current_job = await job_store.get_job(job_id)
                    if not current_job:
                        break
                    if current_job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                        yield f"event: complete\ndata: {json.dumps({'job_id': job_id, 'status': current_job.status.value})}\n\n"
                        break
                        
        except Exception as e:
            logger.error(f"[SSE] 스트리밍 오류: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)[:200]})}\n\n"
        finally:
            await job_store.unsubscribe(job_id, queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Nginx 버퍼링 비활성화
        }
    )


@router.get(
    "/report-result",
    summary="완료된 리포트 결과 조회"
)
async def get_report_result(
    job_id: str = Query(..., description="Job ID")
):
    """
    🎯 완료된 리포트 결과 조회
    
    Job이 완료되면 최종 결과를 반환합니다.
    진행 중이면 현재 상태를 반환합니다.
    """
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    if job.status == JobStatus.COMPLETED and job.final_result:
        return JSONResponse(content={
            "status": "completed",
            "job_id": job_id,
            "result": job.final_result
        })
    
    if job.status == JobStatus.FAILED:
        return JSONResponse(
            status_code=500,
            content={
                "status": "failed",
                "job_id": job_id,
                "error": job.error_message
            }
        )
    
    # 아직 진행 중
    return JSONResponse(content={
        "status": job.status.value,
        "job_id": job_id,
        "progress": job.to_dict()
    })


@router.get(
    "/report-progress",
    summary="진행 상태 폴링 조회 (SSE 대안)"
)
async def get_report_progress(
    job_id: str = Query(..., description="Job ID")
):
    """
    🎯 폴링 방식 진행 상태 조회
    
    SSE가 불안정한 환경에서 1~2초마다 호출하여 진행 상태를 확인합니다.
    """
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    return JSONResponse(content=job.to_dict())
