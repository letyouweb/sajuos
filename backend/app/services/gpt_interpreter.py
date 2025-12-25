"""
GPT Interpreter - Production Ready
- Chat Completions API only
- Detailed error logging for Railway
- Robust fallback handling
"""
import json
import logging
import random
import asyncio
import re
from typing import Optional, Dict, Any, Tuple
from openai import AsyncOpenAI, APIError, RateLimitError, APIConnectionError, AuthenticationError
import httpx

from app.config import get_settings
from app.models.schemas import ConcernType, InterpretResponse
from app.rules.interpretation_rules import get_full_system_prompt
from app.services.openai_key import get_openai_api_key, key_fingerprint, key_tail

logger = logging.getLogger(__name__)

GUARDRAIL_ADDON = """
## Rules
1. No specific person names
2. Professional consulting tone
3. No lecture-style language
4. Use JSON output only
"""


class GptInterpreter:
    def __init__(self):
        self._client = None
    
    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client with fresh settings"""
        settings = get_settings()
        api_key = get_openai_api_key()
        logger.debug("OpenAI client fp=%s tail=%s", key_fingerprint(api_key), key_tail(api_key))
        return AsyncOpenAI(
            api_key=api_key,
            timeout=httpx.Timeout(float(settings.sajuos_timeout), connect=15.0),
            max_retries=0
        )

    async def _call_llm_json(self, system_prompt: str, user_prompt: str) -> Tuple[Dict[str, Any], int]:
        """Direct LLM call - no ping, no model list check"""
        settings = get_settings()
        client = self._get_client()
        full_system = system_prompt + "\n\n" + GUARDRAIL_ADDON
        last_error = None
        
        for attempt in range(settings.sajuos_max_retries):
            try:
                logger.info(f"[LLM] Attempt {attempt + 1}/{settings.sajuos_max_retries} | Model: {settings.openai_model}")
                
                # Direct chat.completions.create call only
                response = await client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": full_system},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=settings.max_output_tokens,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                tokens_used = response.usage.total_tokens if response.usage else 0
                model_used = response.model
                
                logger.info(f"[LLM] Success | Tokens: {tokens_used} | Model: {model_used}")
                
                parsed = self._parse_json(content)
                if parsed:
                    return parsed, tokens_used
                
                logger.warning("[LLM] JSON parse failed, retrying")
                last_error = Exception("JSON parsing failed")
                
            except AuthenticationError as e:
                # 401 Error - API key issue
                error_detail = self._extract_error_detail(e)
                api_key = get_openai_api_key()
                logger.error(f"[LLM] AUTH_ERROR (401) | {error_detail}")
                logger.error("[LLM] API Key fp=%s tail=%s", key_fingerprint(api_key), key_tail(api_key))
                logger.error("[LLM] Check: 1) API key valid 2) Key has permissions 3) No billing issue")
                raise Exception(f"Authentication failed: {error_detail}")
                
            except RateLimitError as e:
                error_detail = self._extract_error_detail(e)
                
                if "insufficient_quota" in str(e).lower():
                    logger.error(f"[LLM] QUOTA_EXHAUSTED | {error_detail}")
                    logger.error("[LLM] Action: Add credits at platform.openai.com/account/billing")
                    raise Exception("API quota exhausted - add billing credits")
                
                last_error = e
                delay = self._backoff(attempt, settings)
                logger.warning(f"[LLM] RATE_LIMIT | Waiting {delay:.1f}s | {error_detail}")
                await asyncio.sleep(delay)
                
            except APIConnectionError as e:
                error_detail = self._extract_error_detail(e)
                last_error = e
                delay = self._backoff(attempt, settings)
                logger.warning(f"[LLM] CONNECTION_ERROR | Waiting {delay:.1f}s | {error_detail}")
                await asyncio.sleep(delay)
                
            except APIError as e:
                error_detail = self._extract_error_detail(e)
                status_code = getattr(e, 'status_code', 'unknown')
                
                if status_code == 401:
                    logger.error(f"[LLM] AUTH_ERROR (401) | {error_detail}")
                    raise Exception(f"Authentication failed: {error_detail}")
                elif status_code == 403:
                    logger.error(f"[LLM] FORBIDDEN (403) | {error_detail}")
                    raise Exception(f"Access forbidden: {error_detail}")
                elif status_code == 404:
                    logger.error(f"[LLM] MODEL_NOT_FOUND (404) | Model: {settings.openai_model}")
                    raise Exception(f"Model not found: {settings.openai_model}")
                elif status_code >= 500:
                    last_error = e
                    delay = self._backoff(attempt, settings)
                    logger.warning(f"[LLM] SERVER_ERROR ({status_code}) | Waiting {delay:.1f}s")
                    await asyncio.sleep(delay)
                else:
                    last_error = e
                    logger.error(f"[LLM] API_ERROR ({status_code}) | {error_detail}")
                    delay = self._backoff(attempt, settings)
                    await asyncio.sleep(delay)
                
            except Exception as e:
                last_error = e
                logger.error(f"[LLM] UNEXPECTED_ERROR | Type: {type(e).__name__} | {str(e)[:200]}")
                delay = self._backoff(attempt, settings)
                await asyncio.sleep(delay)
        
        logger.error(f"[LLM] ALL_RETRIES_FAILED | Last error: {type(last_error).__name__}")
        raise Exception(f"LLM call failed after {settings.sajuos_max_retries} retries")

    def _extract_error_detail(self, error: Exception) -> str:
        """Extract readable error detail"""
        try:
            if hasattr(error, 'message'):
                return str(error.message)[:200]
            if hasattr(error, 'body') and error.body:
                if isinstance(error.body, dict):
                    return str(error.body.get('error', {}).get('message', str(error.body)))[:200]
            return str(error)[:200]
        except:
            return str(error)[:200]

    def _backoff(self, attempt: int, settings) -> float:
        delay = min(settings.sajuos_retry_base_delay * (2 ** attempt), settings.sajuos_retry_max_delay)
        return delay * random.uniform(0.5, 1.5)

    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        if not content:
            return None
        
        text = content.strip()
        
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
            text = "\n".join(lines)
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        return None

    async def interpret(
        self,
        saju_data: Dict[str, Any],
        name: str,
        gender: Optional[str],
        concern_type: ConcernType,
        question: str
    ) -> InterpretResponse:
        settings = get_settings()
        
        try:
            api_key = get_openai_api_key()
        except RuntimeError as e:
            logger.error(f"[INTERPRET] API key error: {e}")
            return self._fallback(name, "NO_API_KEY", str(e))
        
        system_prompt = get_full_system_prompt(concern_type)
        user_prompt = self._build_prompt(saju_data, name, gender, concern_type, question)
        
        try:
            data, tokens = await self._call_llm_json(system_prompt, user_prompt)
            result = self._build_result(data, name)
            result["model_used"] = settings.openai_model
            result["tokens_used"] = tokens
            logger.info(f"[INTERPRET] Success | Name: {name[:10]}... | Tokens: {tokens}")
            return InterpretResponse(**result)
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)[:100]
            logger.error(f"[INTERPRET] Failed | Error: {error_type} | {error_msg}")
            return self._fallback(name, error_type, error_msg)

    def _build_prompt(self, saju_data: Dict, name: str, gender: Optional[str], concern_type: ConcernType, question: str) -> str:
        year_p = self._get_pillar(saju_data, "year_pillar", "year")
        month_p = self._get_pillar(saju_data, "month_pillar", "month")
        day_p = self._get_pillar(saju_data, "day_pillar", "day")
        hour_p = self._get_pillar(saju_data, "hour_pillar", "hour") or "N/A"
        
        day_master = saju_data.get("day_master", day_p[0] if day_p else "")
        day_master_elem = saju_data.get("day_master_element", "")
        
        gender_map = {"male": "Male", "female": "Female", "other": "Other"}
        gender_text = gender_map.get(gender, "N/A")
        
        concern_map = {
            ConcernType.LOVE: "Love/Marriage",
            ConcernType.WEALTH: "Wealth/Finance",
            ConcernType.CAREER: "Career/Business",
            ConcernType.HEALTH: "Health",
            ConcernType.STUDY: "Study/Exam",
            ConcernType.GENERAL: "General Fortune"
        }
        concern_text = concern_map.get(concern_type, "General")
        
        return f"""[User Info]
- Gender: {gender_text}
- Concern: {concern_text}
- Question: {question}

[Saju]
- Year: {year_p}
- Month: {month_p}
- Day: {day_p}
- Hour: {hour_p}

[Day Master]
- Stem: {day_master}
- Element: {day_master_elem}

Analyze and respond in JSON format."""

    def _get_pillar(self, data: Dict, key1: str, key2: str) -> str:
        pillar = data.get(key1, data.get(key2, ""))
        if isinstance(pillar, dict):
            return pillar.get("ganji", str(pillar))
        return str(pillar) if pillar else ""

    def _build_result(self, data: Dict[str, Any], name: str) -> Dict[str, Any]:
        """
        GPT 응답을 InterpretResponse 형식으로 변환
        - 30페이지 프리미엄 구조: structure 필드에 전체 저장
        - 레거시 필드: 기존 프론트엔드 호환성 유지
        """
        # 레거시 필드 추출 (legacy_fields 또는 최상위)
        legacy = data.get("legacy_fields", {})
        
        # 요약 (summary)
        summary = (
            data.get("summary") or
            legacy.get("summary") or
            data.get("section_1_executive_summary", {}).get("one_line_insight") or
            "2026년 프리미엄 사주 분석 완료"
        )
        
        # 일간 분석
        day_master_analysis = (
            data.get("day_master_analysis") or
            legacy.get("day_master_analysis") or
            data.get("section_2_day_master_profile", {}).get("personality_analysis") or
            ""
        )
        
        # 강점
        strengths = (
            data.get("strengths") or
            legacy.get("strengths") or
            data.get("section_1_executive_summary", {}).get("key_opportunities") or
            []
        )
        
        # 리스크
        risks = (
            data.get("risks") or
            legacy.get("risks") or
            data.get("section_1_executive_summary", {}).get("key_risks") or
            []
        )
        
        # 답변
        answer = (
            data.get("answer") or
            legacy.get("answer") or
            data.get("section_1_executive_summary", {}).get("year_overview") or
            ""
        )
        
        # 액션 플랜
        action_plan = (
            data.get("action_plan") or
            legacy.get("action_plan") or
            data.get("section_8_90day_sprint", {}).get("week_1_4", {}).get("actions") or
            []
        )
        
        # 좋은 시기
        lucky_periods = (
            data.get("lucky_periods") or
            legacy.get("lucky_periods") or
            data.get("section_7_monthly_calendar", {}).get("best_months") or
            []
        )
        
        # 주의 시기
        caution_periods = (
            data.get("caution_periods") or
            legacy.get("caution_periods") or
            data.get("section_7_monthly_calendar", {}).get("caution_months") or
            []
        )
        
        # 행운 요소
        lucky_elements = (
            data.get("lucky_elements") or
            legacy.get("lucky_elements") or
            data.get("section_9_lucky_elements")
        )
        if lucky_elements and isinstance(lucky_elements, dict):
            # 새 구조면 레거시 형식으로 변환
            if "lucky_colors" in lucky_elements:
                lucky_elements = {
                    "color": lucky_elements.get("lucky_colors", [""])[0] if lucky_elements.get("lucky_colors") else "",
                    "direction": lucky_elements.get("lucky_directions", [""])[0] if lucky_elements.get("lucky_directions") else "",
                    "number": lucky_elements.get("lucky_numbers", [""])[0] if lucky_elements.get("lucky_numbers") else ""
                }
        
        # 축복 메시지
        blessing = (
            data.get("blessing") or
            legacy.get("blessing") or
            data.get("closing_message", {}).get("blessing") or
            f"{name}님, 2026년 큰 성취를 응원합니다!"
        )
        
        return {
            "success": True,
            "summary": summary,
            "structure": data,  # 30페이지 전체 구조 저장
            "day_master_analysis": day_master_analysis,
            "strengths": strengths if isinstance(strengths, list) else [strengths],
            "risks": risks if isinstance(risks, list) else [risks],
            "answer": answer,
            "action_plan": action_plan if isinstance(action_plan, list) else [action_plan],
            "lucky_periods": lucky_periods if isinstance(lucky_periods, list) else [lucky_periods],
            "caution_periods": caution_periods if isinstance(caution_periods, list) else [caution_periods],
            "lucky_elements": lucky_elements,
            "blessing": blessing,
            "disclaimer": data.get("disclaimer", "오락/참고 목적으로 제공되며, 전문적 조언을 대체하지 않습니다.")
        }

    def _fallback(self, name: str, error_code: str = "UNKNOWN", error_msg: str = "") -> InterpretResponse:
        """Fallback response with error tracking"""
        logger.warning(f"[FALLBACK] Triggered | Code: {error_code} | Msg: {error_msg[:50]}")
        
        return InterpretResponse(
            success=False,
            summary="Service temporarily unavailable",
            day_master_analysis="Please try again in a moment.",
            strengths=["System recovering"],
            risks=["Temporary service issue"],
            answer="Our interpretation service encountered a temporary issue. Please try again shortly.",
            action_plan=["Wait 30 seconds", "Refresh and retry", "Contact support if persists"],
            lucky_periods=[],
            caution_periods=[],
            lucky_elements=None,
            blessing=f"{name}, we'll be back shortly!",
            disclaimer="For entertainment only.",
            model_used=f"fallback_{error_code}",
            tokens_used=0
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> dict:
        settings = get_settings()
        input_cost = (input_tokens / 1_000_000) * 2.50
        output_cost = (output_tokens / 1_000_000) * 10.00
        total_usd = input_cost + output_cost
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(total_usd, 6),
            "cost_krw": round(total_usd * 1450, 2),
            "note": settings.openai_model
        }


gpt_interpreter = GptInterpreter()
