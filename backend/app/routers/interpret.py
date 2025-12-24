"""
/interpret 엔드포인트
- GPT 기반 사주 해석
- 구조화된 JSON 응답
- 오늘 날짜 컨텍스트 자동 주입 (연도 착각 방지)
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

# ✅ 룰카드 파이프라인(사업가형 Type2)
from app.services.feature_tags_no_time import build_feature_tags_no_time_from_pillars
from app.services.preset_type2 import BUSINESS_OWNER_PRESET_V2
from app.services.focus_boost import boost_preset_focus
from app.services.rulecard_selector import select_cards_for_preset

logger = logging.getLogger(__name__)
router = APIRouter()


def _compress_rulecards_for_prompt(selection: dict, max_cards_per_section: int = 6) -> str:
    """
    GPT에 넣을 룰카드 컨텍스트를 토큰 폭발 없이 압축.
    - 섹션별로 상위 N장만 요약(Trigger/Mechanism/Action 중심)
    """
    lines = []
    lines.append("[룰카드 근거 컨텍스트: 사업가형(Type2) 프리미엄 모드]")
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

    lines.append("\n[요청사항] 위 룰카드 근거를 인용하여, 단정 대신 실행 가능한 전략을 제시하고, 섹션별로 'Must-Do / Never-Do'를 포함하라.")
    return "\n".join(lines)


@router.post(
    "/interpret",
    response_model=InterpretResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    },
    summary="사주 해석",
    description="""
사주 원국과 고민을 입력받아 AI가 해석합니다.

**오늘 날짜 컨텍스트 자동 주입:**
- GPT에게 "오늘 날짜"를 명시적으로 전달하여 연도 착각 방지

**프리미엄 모드:**
- `POST /interpret?mode=type2_rulecards`
- 사업가형(2번) 룰카드(Quota + focusBoost + Fallback) 기반으로 근거를 주입
"""
)
async def interpret_saju(
    payload: InterpretRequest,
    raw: Request,
    mode: str = Query("direct", description="direct | type2_rulecards")
):
    """
    사주 해석 API
    """

    # 사주 데이터 구성
    saju_data = {}

    if payload.saju_result:
        saju_data = payload.saju_result.model_dump()
    else:
        if not all([payload.year_pillar, payload.month_pillar, payload.day_pillar]):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "MISSING_SAJU_DATA",
                    "message": "사주 정보가 필요합니다. saju_result 또는 각 기둥(년주/월주/일주)을 입력하세요."
                }
            )

        saju_data = {
            "year_pillar": payload.year_pillar,
            "month_pillar": payload.month_pillar,
            "day_pillar": payload.day_pillar,
            "hour_pillar": payload.hour_pillar,
            "day_master": payload.day_pillar[0] if payload.day_pillar else "",
            "day_master_element": ""
        }

    # ✅ 기본: 오늘 날짜 컨텍스트 주입(연도 착각 방지)
    question = payload.question

    # ✅ 프리미엄 모드(사업가형 룰카드 주입)
    if mode == "type2_rulecards":
        # FastAPI app.state에서 룰스토어 가져오기
        store = getattr(raw.app.state, "rulestore", None)
        if store is None:
            raise HTTPException(
                status_code=500,
                detail={
                    "error_code": "RULESTORE_NOT_LOADED",
                    "message": "룰카드 스토어가 로드되지 않았습니다. 서버 startup 로딩을 확인하세요."
                }
            )

        year_p = saju_data.get("year_pillar")
        month_p = saju_data.get("month_pillar")
        day_p = saju_data.get("day_pillar")
        if not (year_p and month_p and day_p):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "MISSING_PILLARS",
                    "message": "룰카드 모드는 year_pillar/month_pillar/day_pillar가 필요합니다."
                }
            )

        # 1) 시 없이 featureTags 생성(2026 오버레이)
        ft = build_feature_tags_no_time_from_pillars(year_p, month_p, day_p, overlay_year=2026)

        # 2) 섹션별 focusTags 자동 보강
        boosted = boost_preset_focus(BUSINESS_OWNER_PRESET_V2, ft["tags"])

        # 3) Quota + 정밀도우선 + 폴백 룰카드 후보 선정
        selection = select_cards_for_preset(store, boosted, ft["tags"])

        # 4) 질문에 룰카드 근거 컨텍스트를 "추가"해서 GPT로 보냄
        rule_context = _compress_rulecards_for_prompt(selection)
        question = f"""{question}

[featureTags 샘플] {", ".join(ft["tags"][:24])}

{rule_context}
"""

        logger.info(f"[PremiumMode] Type2 enabled. featureTags={len(ft['tags'])} sections={len(selection.get('sections', []))}")

    # ⚠️ 핵심: 오늘 날짜 컨텍스트 주입 (연도 착각 방지)
    question_with_context = SajuManager.inject_today_context(question)

    logger.info(f"Interpreting saju - Today: {SajuManager.get_today_string()} mode={mode}")

    # 해석 실행
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
        logger.error(f"Interpretation error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "INTERPRETATION_ERROR",
                "message": "사주 해석 중 오류가 발생했습니다.",
                "detail": str(e)
            }
        )


@router.get(
    "/interpret/today",
    summary="오늘 날짜 확인",
    description="서버가 인식하는 오늘 날짜를 확인합니다. (연도 착각 디버깅용)"
)
async def get_today_context():
    """오늘 날짜 컨텍스트 확인"""
    today = SajuManager.get_today_kst()
    sample_question = "올해 운세가 궁금합니다."

    return {
        "today_kst": SajuManager.get_today_string(),
        "year": today.year,
        "month": today.month,
        "day": today.day,
        "sample_input": sample_question,
        "sample_output": SajuManager.inject_today_context(sample_question)
    }


@router.get(
    "/interpret/cost-estimate",
    summary="비용 추정",
    description="사주 해석 1건당 예상 비용을 조회합니다."
)
async def get_cost_estimate(
    input_tokens: int = 1500,
    output_tokens: int = 1000
):
    """비용 추정 조회"""
    return gpt_interpreter.estimate_cost(input_tokens, output_tokens)


@router.get(
    "/interpret/concern-types",
    summary="고민 유형 목록",
    description="지원하는 고민 유형 목록을 조회합니다."
)
async def get_concern_types():
    """고민 유형 목록"""
    return {
        "concern_types": [
            {"value": "love", "label": "연애/결혼", "emoji": "💕"},
            {"value": "wealth", "label": "재물/금전", "emoji": "💰"},
            {"value": "career", "label": "직장/사업", "emoji": "💼"},
            {"value": "health", "label": "건강", "emoji": "🏥"},
            {"value": "study", "label": "학업/시험", "emoji": "📚"},
            {"value": "general", "label": "종합운세", "emoji": "🔮"}
        ]
    }


@router.get(
    "/interpret/gpt-test",
    summary="GPT API 직접 테스트",
    description="OpenAI API 연결 상태를 직접 테스트합니다."
)
async def test_gpt_connection():
    """GPT API 테스트 (디버깅용)"""
    from app.config import get_settings
    from openai import AsyncOpenAI
    import httpx
    import traceback
    
    settings = get_settings()
    
    result = {
        "api_key_set": bool(settings.openai_api_key),
        "api_key_preview": settings.openai_api_key[:12] + "..." if settings.openai_api_key else "NOT_SET",
        "model": settings.openai_model,
    }
    
    if not settings.openai_api_key:
        result["error"] = "OPENAI_API_KEY 환경변수가 설정되지 않았습니다."
        return result
    
    # 1단계: OpenAI API 서버 연결 테스트
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            ping_resp = await client.get("https://api.openai.com/v1/models")
            result["openai_reachable"] = ping_resp.status_code in [200, 401]
            result["ping_status"] = ping_resp.status_code
    except Exception as e:
        result["openai_reachable"] = False
        result["ping_error"] = str(e)
    
    # 2단계: 실제 API 호출 테스트
    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        # 간단한 테스트 요청
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "user", "content": "Say 'Hello' in Korean"}
            ],
            max_tokens=20
        )
        
        result["success"] = True
        result["response"] = response.choices[0].message.content
        result["tokens_used"] = response.usage.total_tokens if response.usage else None
        
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        result["traceback"] = traceback.format_exc()[-500:]  # 마지막 500자
    
    return result
