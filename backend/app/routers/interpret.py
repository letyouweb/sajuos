"""
/interpret endpoint - Production Ready
- 2026 신년운세: target_year 강제 컨텍스트
"""
from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional
import logging

from app.models.schemas import (
    InterpretRequest,
    InterpretResponse,
    ErrorResponse,
    ConcernType
)
from app.services.gpt_interpreter import gpt_interpreter
from app.services.engine_v2 import SajuManager

# RuleCard pipeline (Type2)
from app.services.feature_tags_no_time import build_feature_tags_no_time_from_pillars
from app.services.preset_type2 import BUSINESS_OWNER_PRESET_V2
from app.services.focus_boost import boost_preset_focus
from app.services.rulecard_selector import select_cards_for_preset

logger = logging.getLogger(__name__)
router = APIRouter()


# ============ 2026 컨텍스트 강제 ============

def inject_year_context(question: str, target_year: int) -> str:
    """
    2026 신년운세용: 연도 강제 컨텍스트 주입
    - '오늘 날짜'를 넣지 않음 (2025/2026 혼동 방지)
    - 모든 해석을 target_year 기준으로 고정
    """
    return f"""[분석 기준 고정]
- 이 분석은 반드시 {target_year}년 1월~12월 기준으로만 작성합니다.
- 월별 운세/좋은 시기/조심할 시기는 {target_year}년 달력 흐름으로 제시합니다.
- 다른 연도(예: 올해/작년/오늘 날짜)를 근거로 섹어 말하지 않습니다.

[사용자 질문]
{question}""".strip()


def _compress_rulecards_for_prompt(selection: dict, max_cards_per_section: int = 6) -> str:
    """Compress rulecards for GPT prompt"""
    lines = ["[RuleCard Context: Business Owner Type2 Premium Mode]"]
    for sec in selection.get("sections", []):
        title = sec.get("title", sec.get("key", ""))
        meta = sec.get("meta", {})
        avg_overlap = meta.get("avgOverlap", 0)
        by_stage = meta.get("byStage", {})
        lines.append(f"\n## {title} (avgOverlap={avg_overlap}, stage={by_stage})")

        cards = sec.get("cards", [])[:max_cards_per_section]
        for c in cards:
            cid = c.get("id", "")
            topic = c.get("topic", "")
            tags = ", ".join((c.get("tags") or [])[:8])
            trig = (c.get("trigger") or "")[:120]
            mech = (c.get("mechanism") or "")[:160]
            act = (c.get("action") or "")[:160]
            lines.append(f"- [ID:{cid}][{topic}] tags={tags}")
            if trig: lines.append(f"  - Trigger: {trig}")
            if mech: lines.append(f"  - Mechanism: {mech}")
            if act:  lines.append(f"  - Action: {act}")

    lines.append("\n[Request] Cite RuleCards, provide actionable strategies.")
    return "\n".join(lines)


@router.post(
    "/interpret",
    response_model=InterpretResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Saju Interpretation"
)
async def interpret_saju(
    payload: InterpretRequest,
    raw: Request,
    mode: str = Query("direct", description="direct | type2_rulecards")
):
    """Saju interpretation API"""
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

    # Premium mode (Type2 RuleCards)
    if mode == "type2_rulecards":
        store = getattr(raw.app.state, "rulestore", None)
        if store is None:
            raise HTTPException(status_code=500, detail={"error_code": "RULESTORE_NOT_LOADED", "message": "RuleCard store not loaded"})

        year_p = saju_data.get("year_pillar")
        month_p = saju_data.get("month_pillar")
        day_p = saju_data.get("day_pillar")
        if not (year_p and month_p and day_p):
            raise HTTPException(status_code=400, detail={"error_code": "MISSING_PILLARS", "message": "Pillars required for RuleCard mode"})

        ft = build_feature_tags_no_time_from_pillars(year_p, month_p, day_p, overlay_year=2026)
        boosted = boost_preset_focus(BUSINESS_OWNER_PRESET_V2, ft["tags"])
        selection = select_cards_for_preset(store, boosted, ft["tags"])
        rule_context = _compress_rulecards_for_prompt(selection)
        
        question = f"{question}\n\n[featureTags] {', '.join(ft['tags'][:24])}\n\n{rule_context}"
        logger.info(f"[PremiumMode] Type2 | featureTags={len(ft['tags'])} sections={len(selection.get('sections', []))}")

    # 2026 신년운세: target_year 항상 우선 (기본 2026)
    # - payload.target_year가 명시되면 그걸 사용
    # - 없으면 2026 고정 (신년운세 상품)
    final_year = payload.target_year if payload.target_year else 2026
    
    question_with_context = inject_year_context(question, final_year)
    logger.info(f"[INTERPRET] TargetYear={final_year} | Mode={mode}")

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
    response_model=InterpretResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Generate Saju Report (Alias for /interpret)"
)
async def generate_report(
    payload: InterpretRequest,
    raw: Request,
    mode: str = Query("direct", description="direct | type2_rulecards")
):
    """Generate Saju Report - Alias endpoint for /interpret"""
    return await interpret_saju(payload, raw, mode)


@router.get("/interpret/today", summary="Today Date")
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


@router.get("/interpret/gpt-test", summary="GPT API Test")
async def test_gpt_connection():
    """Direct GPT call test - no ping, production ready"""
    from app.config import get_settings
    from app.services.openai_key import get_openai_api_key, key_fingerprint, key_tail
    from openai import AsyncOpenAI
    import httpx
    
    settings = get_settings()
    
    try:
        api_key = get_openai_api_key()
        key_set = True
        key_preview = f"fp={key_fingerprint(api_key)} tail={key_tail(api_key)}"
    except RuntimeError as e:
        api_key = None
        key_set = False
        key_preview = str(e)
    
    result = {
        "api_key_set": key_set,
        "api_key_preview": key_preview,
        "model": settings.openai_model,
        "max_retries": settings.sajuos_max_retries,
        "timeout": settings.sajuos_timeout,
    }
    
    if not api_key:
        result["success"] = False
        result["error"] = "OPENAI_API_KEY not set or invalid"
        return result
    
    # Direct API call only - no ping test
    try:
        client = AsyncOpenAI(
            api_key=api_key,
            timeout=httpx.Timeout(30.0, connect=10.0)
        )
        
        chat_resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": "Say hello"}],
            max_tokens=20
        )
        
        result["success"] = True
        result["response"] = chat_resp.choices[0].message.content
        result["model_used"] = chat_resp.model
        result["status"] = "READY_FOR_PRODUCTION"
        
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)[:300]
        
        result["success"] = False
        result["error_type"] = error_type
        result["error"] = error_msg
        
        # Detailed error guidance
        if "401" in error_msg or "auth" in error_msg.lower():
            result["guidance"] = "Check API key validity and permissions"
        elif "429" in error_msg or "rate" in error_msg.lower():
            result["guidance"] = "Rate limited - wait and retry"
        elif "quota" in error_msg.lower():
            result["guidance"] = "Add billing credits at platform.openai.com"
        elif "404" in error_msg:
            result["guidance"] = f"Model '{settings.openai_model}' not found"
        else:
            result["guidance"] = "Check Railway logs for details"
    
    return result
