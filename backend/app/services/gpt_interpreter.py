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
        return AsyncOpenAI(
            api_key=settings.clean_openai_api_key,
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
                logger.error(f"[LLM] AUTH_ERROR (401) | {error_detail}")
                logger.error(f"[LLM] API Key Preview: {settings.clean_openai_api_key[:15]}...")
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
        
        if not settings.openai_api_key:
            logger.error("[INTERPRET] No API key configured")
            return self._fallback(name, "NO_API_KEY", "API key not configured")
        
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
        return {
            "success": True,
            "summary": data.get("summary", "Analysis complete"),
            "day_master_analysis": data.get("day_master_analysis", ""),
            "strengths": data.get("strengths", []),
            "risks": data.get("risks", []),
            "answer": data.get("answer", ""),
            "action_plan": data.get("action_plan", []),
            "lucky_periods": data.get("lucky_periods", []),
            "caution_periods": data.get("caution_periods", []),
            "lucky_elements": data.get("lucky_elements"),
            "blessing": data.get("blessing", f"{name}, good luck!"),
            "disclaimer": "For entertainment only."
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
