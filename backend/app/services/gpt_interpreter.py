"""
GPT 해석 엔진
- OpenAI API를 통한 사주 해석
- 토큰 비용 통제
- 구조화된 JSON 응답
"""
import json
import logging
from typing import Optional, Dict, Any
from openai import AsyncOpenAI

from app.config import get_settings
from app.models.schemas import (
    ConcernType, 
    InterpretResponse,
    CalculateResponse
)
from app.rules.interpretation_rules import (
    get_full_system_prompt,
    get_lucky_elements
)

logger = logging.getLogger(__name__)


class GptInterpreter:
    """
    GPT 기반 사주 해석 엔진
    """
    
    def __init__(self):
        self.settings = get_settings()
        
        # API 키 검증
        if not self.settings.openai_api_key:
            logger.error("❌ OPENAI_API_KEY가 설정되지 않았습니다!")
        else:
            # 키 일부만 로깅 (보안)
            key_preview = self.settings.openai_api_key[:8] + "..." if len(self.settings.openai_api_key) > 8 else "???"
            logger.info(f"✅ OpenAI API Key loaded: {key_preview}")
        
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.model = self.settings.openai_model
        self.max_output_tokens = self.settings.max_output_tokens
    
    async def interpret(
        self,
        saju_data: Dict[str, Any],
        name: str,
        gender: Optional[str],
        concern_type: ConcernType,
        question: str
    ) -> InterpretResponse:
        """
        사주 해석 실행
        """
        
        # API 키 검증
        if not self.settings.openai_api_key:
            logger.error("❌ OPENAI_API_KEY가 비어있음 - fallback 반환")
            return self._create_fallback_response(name, "API 키가 설정되지 않았습니다.")
        
        # 1. 시스템 프롬프트 구성
        system_prompt = get_full_system_prompt(concern_type)
        
        # 2. 사용자 프롬프트 구성
        user_prompt = self._build_user_prompt(
            saju_data, name, gender, concern_type, question
        )
        
        # 3. GPT API 호출
        try:
            logger.info(f"🚀 GPT 호출 시작: model={self.model}, name={name}")
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.max_output_tokens,
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            logger.info(f"✅ GPT 응답 성공")
            
            # 4. 응답 파싱
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else None
            
            result = self._parse_response(content, name)
            result["model_used"] = self.model
            result["tokens_used"] = tokens_used
            
            return InterpretResponse(**result)
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 파싱 오류: {e}")
            return self._create_fallback_response(name, f"응답 파싱 오류: {e}")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ GPT API 오류: {error_msg}")
            
            # 상세 에러 분류
            if "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
                logger.error("💡 API 키 인증 실패 - Railway 환경변수 확인 필요")
            elif "rate_limit" in error_msg.lower():
                logger.error("💡 Rate limit 초과")
            elif "timeout" in error_msg.lower():
                logger.error("💡 타임아웃 발생")
            
            return self._create_fallback_response(name, error_msg)
    
    def _build_user_prompt(
        self,
        saju_data: Dict[str, Any],
        name: str,
        gender: Optional[str],
        concern_type: ConcernType,
        question: str
    ) -> str:
        """사용자 프롬프트 구성"""
        
        year_pillar = saju_data.get("year_pillar", saju_data.get("year", ""))
        month_pillar = saju_data.get("month_pillar", saju_data.get("month", ""))
        day_pillar = saju_data.get("day_pillar", saju_data.get("day", ""))
        hour_pillar = saju_data.get("hour_pillar", saju_data.get("hour", "없음"))
        
        if isinstance(year_pillar, dict):
            year_pillar = year_pillar.get("ganji", str(year_pillar))
        if isinstance(month_pillar, dict):
            month_pillar = month_pillar.get("ganji", str(month_pillar))
        if isinstance(day_pillar, dict):
            day_pillar = day_pillar.get("ganji", str(day_pillar))
        if isinstance(hour_pillar, dict):
            hour_pillar = hour_pillar.get("ganji", str(hour_pillar))
        
        day_master = saju_data.get("day_master", day_pillar[0] if day_pillar else "")
        day_master_element = saju_data.get("day_master_element", "")
        
        gender_text = {
            "male": "남성",
            "female": "여성",
            "other": "기타"
        }.get(gender, "미입력")
        
        concern_text = {
            ConcernType.LOVE: "연애/결혼",
            ConcernType.WEALTH: "재물/금전",
            ConcernType.CAREER: "직장/사업",
            ConcernType.HEALTH: "건강",
            ConcernType.STUDY: "학업/시험",
            ConcernType.GENERAL: "종합운세"
        }.get(concern_type, "종합운세")
        
        return f"""[사용자 정보]
- 이름: {name}
- 성별: {gender_text}
- 고민 분야: {concern_text}
- 질문: {question}

[사주 원국]
- 년주: {year_pillar}
- 월주: {month_pillar}
- 일주: {day_pillar}
- 시주: {hour_pillar if hour_pillar else "미입력"}

[일간 정보]
- 일간(나): {day_master}
- 일간 오행: {day_master_element}

위 정보를 바탕으로 사용자의 고민에 맞는 사주 풀이를 JSON 형식으로 작성해주세요."""
    
    def _parse_response(self, content: str, name: str) -> Dict[str, Any]:
        """GPT 응답 파싱"""
        try:
            data = json.loads(content)
            
            return {
                "success": True,
                "summary": data.get("summary", "사주 분석이 완료되었습니다."),
                "day_master_analysis": data.get("day_master_analysis", ""),
                "strengths": data.get("strengths", ["분석 중"]),
                "risks": data.get("risks", ["분석 중"]),
                "answer": data.get("answer", ""),
                "action_plan": data.get("action_plan", ["자세한 상담이 필요합니다."]),
                "lucky_periods": data.get("lucky_periods", []),
                "caution_periods": data.get("caution_periods", []),
                "lucky_elements": data.get("lucky_elements"),
                "blessing": data.get("blessing", f"{name}님의 앞날에 행운이 가득하길 바랍니다. 🌸"),
                "disclaimer": "본 해석은 오락/참고 목적으로 제공되며, 의학/법률/투자 등 전문적 조언을 대체하지 않습니다."
            }
        except json.JSONDecodeError:
            return {
                "success": True,
                "summary": "사주 분석이 완료되었습니다.",
                "day_master_analysis": content[:500] if content else "",
                "strengths": ["자세한 내용은 아래를 참고하세요."],
                "risks": ["주의 사항을 확인하세요."],
                "answer": content[:1000] if content else "",
                "action_plan": ["구체적인 상담이 필요합니다."],
                "lucky_periods": [],
                "caution_periods": [],
                "lucky_elements": None,
                "blessing": f"{name}님의 앞날에 행운이 가득하길 바랍니다. 🌸",
                "disclaimer": "본 해석은 오락/참고 목적으로 제공되며, 의학/법률/투자 등 전문적 조언을 대체하지 않습니다."
            }
    
    def _create_fallback_response(self, name: str, error_detail: str = "") -> InterpretResponse:
        """오류 시 기본 응답 (에러 원인 포함)"""
        logger.warning(f"⚠️ Fallback 응답 생성: {error_detail}")
        
        return InterpretResponse(
            success=False,
            summary="일시적인 오류가 발생했습니다.",
            day_master_analysis="잠시 후 다시 시도해주세요.",
            strengths=["서비스 복구 중입니다."],
            risks=["일시적 오류"],
            answer=f"해석 서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.",
            action_plan=["잠시 후 다시 시도해주세요."],
            lucky_periods=[],
            caution_periods=[],
            lucky_elements=None,
            blessing=f"{name}님, 곧 정상화됩니다. 양해 부탁드립니다.",
            disclaimer="본 해석은 오락/참고 목적으로 제공되며, 의학/법률/투자 등 전문적 조언을 대체하지 않습니다.",
            model_used="fallback",
            tokens_used=0
        )
    
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> dict:
        """비용 추정"""
        input_cost_usd = (input_tokens / 1_000_000) * 0.15
        output_cost_usd = (output_tokens / 1_000_000) * 0.60
        total_usd = input_cost_usd + output_cost_usd
        total_krw = total_usd * 1400
        
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(total_usd, 6),
            "cost_krw": round(total_krw, 2),
            "note": "GPT-4o-mini 기준"
        }


# 싱글톤 인스턴스
gpt_interpreter = GptInterpreter()
