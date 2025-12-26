"""
/interpret endpoint - Premium Business Report Engine
- 99,000원 프리미엄 모드: 7섹션 순차 생성 + 용어 치환 + Retry
- 단독 섹션 재생성 엔드포인트
- RuleCards 8,500장 데이터 자동 활용
"""
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from typing import Optional
import logging

from app.models.schemas import (
    InterpretRequest,
    InterpretResponse,
    ErrorResponse,
    ConcernType
)
from app.services.gpt_interpreter import gpt_interpreter
from app.services.report_builder import premium_report_builder, PREMIUM_SECTIONS
from app.services.engine_v2 import SajuManager

# RuleCard pipeline
from app.services.feature_tags_no_time import build_feature_tags_no_time_from_pillars
from app.services.preset_type2 import BUSINESS_OWNER_PRESET_V2
from app.services.focus_boost import boost_preset_focus
from app.services.rulecard_selector import select_cards_for_preset

logger = logging.getLogger(__name__)
router = APIRouter()


# ============ Helper Functions ============

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


def _get_all_rulecards(saju_data: dict, store, target_year: int) -> list:
    """사주 데이터에 맞는 전체 RuleCards 반환"""
    year_p, month_p, day_p = _extract_pillars_from_saju_data(saju_data)
    
    logger.info(f"[RuleCards] 추출된 기둥: 년={year_p}, 월={month_p}, 일={day_p}")
    
    if not (year_p and month_p and day_p):
        logger.warning("[RuleCards] 사주 기둥 데이터 부족")
        return []
    
    ft = build_feature_tags_no_time_from_pillars(year_p, month_p, day_p, overlay_year=target_year)
    feature_tags = ft.get("tags", [])
    
    boosted = boost_preset_focus(BUSINESS_OWNER_PRESET_V2, feature_tags)
    selection = select_cards_for_preset(store, boosted, feature_tags)
    
    all_cards = []
    for sec in selection.get("sections", []):
        all_cards.extend(sec.get("cards", []))
    
    logger.info(f"[RuleCards] ✅ 총 {len(all_cards)}장 수집")
    return all_cards


def inject_year_context(question: str, target_year: int) -> str:
    """연도 강제 컨텍스트 주입"""
    return f"""[분석 기준 고정]
- 이 분석은 반드시 {target_year}년 1월~12월 기준으로만 작성합니다.
- 월별 운세/좋은 시기/조심할 시기는 {target_year}년 달력 흐름으로 제시합니다.

[사용자 질문]
{question}""".strip()


def _compress_rulecards_for_prompt(selection: dict, max_cards_per_section: int = 8) -> str:
    """RuleCards를 GPT 프롬프트용으로 압축"""
    lines = ["[사주OS RuleCard 컨텍스트]"]
    
    total_cards = 0
    for sec in selection.get("sections", []):
        title = sec.get("title", sec.get("key", ""))
        cards = sec.get("cards", [])[:max_cards_per_section]
        if not cards:
            continue
            
        lines.append(f"\n## {title}")
        for c in cards:
            total_cards += 1
            cid = c.get("id", "")
            topic = c.get("topic", "")
            mech = (c.get("mechanism") or "")[:100]
            act = (c.get("action") or "")[:100]
            
            lines.append(f"- [{cid}] {topic}")
            if mech: lines.append(f"  mechanism: {mech}")
            if act: lines.append(f"  action: {act}")

    lines.append(f"\n[총 {total_cards}개 RuleCard 참조]")
    return "\n".join(lines)


def build_rulecards_context(saju_data: dict, store, target_year: int = 2026) -> tuple:
    """사주 데이터에서 RuleCards 컨텍스트 생성"""
    year_p, month_p, day_p = _extract_pillars_from_saju_data(saju_data)
    
    if not (year_p and month_p and day_p):
        return "", [], 0
    
    ft = build_feature_tags_no_time_from_pillars(year_p, month_p, day_p, overlay_year=target_year)
    feature_tags = ft.get("tags", [])
    
    boosted = boost_preset_focus(BUSINESS_OWNER_PRESET_V2, feature_tags)
    selection = select_cards_for_preset(store, boosted, feature_tags)
    
    context = _compress_rulecards_for_prompt(selection)
    total_cards = sum(len(sec.get("cards", [])) for sec in selection.get("sections", []))
    
    return context, feature_tags, total_cards


# ============ API Endpoints ============

@router.post(
    "/interpret",
    response_model=InterpretResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Saju Interpretation (Legacy 단일 호출)"
)
async def interpret_saju(
    payload: InterpretRequest,
    raw: Request,
    mode: str = Query("auto", description="auto | direct | premium")
):
    """사주 해석 API (Legacy 단일 호출)"""
    if mode == "premium":
        return await generate_premium_report(payload, raw, mode)
    
    saju_data = {}
    if payload.saju_result:
        saju_data = payload.saju_result.model_dump()
    else:
        if not all([payload.year_pillar, payload.month_pillar, payload.day_pillar]):
            raise HTTPException(status_code=400, detail={"error_code": "MISSING_SAJU_DATA", "message": "Saju data required"})
        saju_data = {
            "year_pillar": payload.year_pillar,
            "month_pillar": payload.month_pillar,
            "day_pillar": payload.day_pillar,
            "hour_pillar": payload.hour_pillar,
            "day_master": payload.day_pillar[0] if payload.day_pillar else "",
            "day_master_element": ""
        }

    question = payload.question
    final_year = payload.target_year if payload.target_year else 2026
    
    store = getattr(raw.app.state, "rulestore", None)
    rulecards_context = ""
    cards_count = 0
    
    if store and mode != "direct":
        try:
            rulecards_context, feature_tags, cards_count = build_rulecards_context(saju_data, store, final_year)
            if rulecards_context:
                question = f"{question}\n\n{rulecards_context}"
        except Exception as e:
            logger.warning(f"[RuleCards] 컨텍스트 생성 실패: {e}")
    
    question_with_context = inject_year_context(question, final_year)
    logger.info(f"[INTERPRET] Year={final_year} | Mode={mode} | Cards={cards_count}")

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
    🎯 99,000원 프리미엄 비즈니스 컨설팅 보고서
    
    - 7개 섹션 순차 생성 (안정성 우선)
    - Retry + Exponential Backoff (429/5xx 대응)
    - Sprint/Calendar 전용 validation
    - 상세 에러 정보 포함
    """
    if mode == "legacy":
        return await interpret_saju(payload, raw, "auto")
    
    saju_data = {}
    if payload.saju_result:
        saju_data = payload.saju_result.model_dump()
    else:
        if not all([payload.year_pillar, payload.month_pillar, payload.day_pillar]):
            raise HTTPException(
                status_code=400,
                detail={"error_code": "MISSING_SAJU_DATA", "message": "Saju data required"}
            )
        saju_data = {
            "year_pillar": payload.year_pillar,
            "month_pillar": payload.month_pillar,
            "day_pillar": payload.day_pillar,
            "hour_pillar": payload.hour_pillar,
            "day_master": payload.day_pillar[0] if payload.day_pillar else "",
            "day_master_element": ""
        }
    
    final_year = payload.target_year if payload.target_year else 2026
    
    store = getattr(raw.app.state, "rulestore", None)
    rulecards = []
    
    if store:
        try:
            rulecards = _get_all_rulecards(saju_data, store, final_year)
        except Exception as e:
            logger.warning(f"[PremiumReport] RuleCards 로드 실패: {e}")
    else:
        logger.warning("[PremiumReport] ⚠️ RuleStore 미로드")
    
    logger.info(f"[PREMIUM-REPORT] Year={final_year} | RuleCards={len(rulecards)} | Mode={mode}")
    
    try:
        report = await premium_report_builder.build_premium_report(
            saju_data=saju_data,
            rulecards=rulecards,
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
                "meta": {"mode": "premium_business_30p", "error": True}
            }
        )


@router.post(
    "/regenerate-section",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="단일 섹션 재생성 (Sprint 복구용)"
)
async def regenerate_single_section(
    payload: InterpretRequest,
    raw: Request,
    section_id: str = Query(..., description="재생성할 섹션 ID (exec, money, business, team, health, calendar, sprint)")
):
    """
    🔄 단일 섹션 재생성 엔드포인트
    
    전체 리포트 재생성 없이 특정 섹션만 재생성합니다.
    Sprint 섹션 실패 시 복구용으로 사용합니다.
    
    **사용 예시:**
    ```
    POST /api/v1/regenerate-section?section_id=sprint
    ```
    """
    # section_id 검증
    valid_sections = list(PREMIUM_SECTIONS.keys())
    if section_id not in valid_sections:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_SECTION_ID",
                "message": f"Invalid section_id: {section_id}. Valid options: {valid_sections}"
            }
        )
    
    # 사주 데이터 추출
    saju_data = {}
    if payload.saju_result:
        saju_data = payload.saju_result.model_dump()
    else:
        if not all([payload.year_pillar, payload.month_pillar, payload.day_pillar]):
            raise HTTPException(
                status_code=400,
                detail={"error_code": "MISSING_SAJU_DATA", "message": "Saju data required"}
            )
        saju_data = {
            "year_pillar": payload.year_pillar,
            "month_pillar": payload.month_pillar,
            "day_pillar": payload.day_pillar,
            "hour_pillar": payload.hour_pillar,
            "day_master": payload.day_pillar[0] if payload.day_pillar else "",
            "day_master_element": ""
        }
    
    final_year = payload.target_year if payload.target_year else 2026
    
    # RuleCards 로드
    store = getattr(raw.app.state, "rulestore", None)
    rulecards = []
    
    if store:
        try:
            rulecards = _get_all_rulecards(saju_data, store, final_year)
        except Exception as e:
            logger.warning(f"[RegenerateSection] RuleCards 로드 실패: {e}")
    
    logger.info(f"[REGENERATE-SECTION] Section={section_id} | Year={final_year} | RuleCards={len(rulecards)}")
    
    try:
        result = await premium_report_builder.regenerate_single_section(
            section_id=section_id,
            saju_data=saju_data,
            rulecards=rulecards,
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


# ============ Utility Endpoints ============

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
                "min_chars": spec.min_chars,
                "rulecard_quota": spec.rulecard_quota,
                "validation_type": spec.validation_type,
                "required_elements": spec.required_elements
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
