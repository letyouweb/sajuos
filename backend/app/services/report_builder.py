"""
SajuOS Premium Report Builder v3
- 99,000원 30페이지 비즈니스 컨설팅 리포트 엔진
- 7개 섹션 분할 생성 (Chaining) + 순차 처리 (안정성 우선)
- Retry + Exponential Backoff (429/5xx 대응)
- Sprint 섹션 전용 validation
- 상세 에러 로깅
"""
import asyncio
import logging
import time
import json
import re
import random
import traceback
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field

from openai import AsyncOpenAI, APIError, RateLimitError, APIConnectionError, APITimeoutError
import httpx

from app.config import get_settings
from app.services.openai_key import get_openai_api_key
from app.services.terminology_mapper import (
    sanitize_for_business,
    get_business_prompt_rules,
    validate_no_forbidden_terms
)

logger = logging.getLogger(__name__)


# ============ 섹션 정의 (프리미엄 스펙) ============

@dataclass
class SectionSpec:
    id: str
    title: str
    pages: int
    rulecard_quota: int
    topics: List[str]
    min_chars: int  # 최소 글자수
    required_elements: List[str]  # 필수 포함 요소
    validation_type: str = "standard"  # standard | sprint | calendar
    

PREMIUM_SECTIONS: Dict[str, SectionSpec] = {
    "exec": SectionSpec(
        id="exec",
        title="Executive Summary",
        pages=2,
        rulecard_quota=50,
        topics=["general", "personality", "yearly_fortune"],
        min_chars=2000,
        required_elements=[
            "현상 진단",
            "핵심 가설 3개",
            "전략적 방향성",
            "즉시 실행 과제 5개",
            "핵심 KPI 3개"
        ],
        validation_type="standard"
    ),
    "money": SectionSpec(
        id="money",
        title="Money & Cashflow",
        pages=5,
        rulecard_quota=80,
        topics=["wealth", "finance", "investment"],
        min_chars=4000,
        required_elements=[
            "현금흐름 현상 진단",
            "수익 구조 가설 3개",
            "전략 옵션 3개(각각 장단점)",
            "추천 전략 + 주간 실행 계획",
            "재무 KPI 5개",
            "리스크 시나리오 3개 + 방어 전략"
        ],
        validation_type="standard"
    ),
    "business": SectionSpec(
        id="business",
        title="Business Strategy",
        pages=5,
        rulecard_quota=80,
        topics=["career", "business", "leadership"],
        min_chars=4000,
        required_elements=[
            "시장 포지션 진단",
            "성장 가설 3개",
            "전략 옵션 3개(장단점 포함)",
            "추천 전략 + 분기별 실행 로드맵",
            "성과 KPI 5개",
            "경쟁 리스크 분석 + 대응"
        ],
        validation_type="standard"
    ),
    "team": SectionSpec(
        id="team",
        title="Team & Partner Risk",
        pages=4,
        rulecard_quota=60,
        topics=["relationship", "partnership", "conflict"],
        min_chars=3000,
        required_elements=[
            "조직/파트너십 현상 진단",
            "관계 역학 가설 3개",
            "팀 구성 전략 옵션 3개",
            "추천 인재/파트너 프로파일",
            "갈등 조기 경보 지표",
            "위기 대응 프로토콜"
        ],
        validation_type="standard"
    ),
    "health": SectionSpec(
        id="health",
        title="Health & Performance",
        pages=3,
        rulecard_quota=50,
        topics=["health", "energy", "wellness"],
        min_chars=2500,
        required_elements=[
            "에너지/퍼포먼스 현상 진단",
            "번아웃 리스크 가설 3개",
            "워라밸 전략 옵션 3개",
            "주간 루틴 권장안",
            "건강 KPI (체크 주기 포함)",
            "위험 신호 + 대응"
        ],
        validation_type="standard"
    ),
    "calendar": SectionSpec(
        id="calendar",
        title="12-Month Tactical Calendar",
        pages=6,
        rulecard_quota=100,
        topics=["monthly", "timing", "seasonal"],
        min_chars=4000,
        required_elements=[
            "연간 전략 테마",
            "12개월 월별 분석",
            "분기별 마일스톤"
        ],
        validation_type="calendar"
    ),
    "sprint": SectionSpec(
        id="sprint",
        title="90-Day Sprint Plan",
        pages=5,
        rulecard_quota=80,
        topics=["action", "planning", "execution"],
        min_chars=3000,
        required_elements=[
            "90일 미션 선언문",
            "주간 실행 계획",
            "마일스톤"
        ],
        validation_type="sprint"
    )
}


# ============ Sprint 전용 프롬프트 ============

def get_sprint_system_prompt(target_year: int) -> str:
    """Sprint 섹션 전용 시스템 프롬프트 (간소화된 구조)"""
    
    terminology_rules = get_business_prompt_rules()
    
    return f"""당신은 99,000원 프리미엄 비즈니스 컨설팅 보고서를 작성하는 시니어 전략 컨설턴트입니다.

## 분석 기준년도: {target_year}년

{terminology_rules}

## 이 섹션: 90-Day Sprint Plan
구체적이고 실행 가능한 90일 액션 플랜을 작성합니다.

## 출력 형식 (반드시 이 JSON 구조로만 응답)

{{
  "title": "90-Day Sprint Plan",
  "mission_statement": "90일 동안 달성할 핵심 미션 (2-3문장)",
  "weekly_plans": [
    {{
      "week": 1,
      "theme": "주간 테마",
      "goals": ["목표1", "목표2"],
      "daily_actions": ["월요일 액션", "화요일 액션", "수요일 액션", "목요일 액션", "금요일 액션"],
      "kpis": ["KPI1", "KPI2"],
      "checkpoint": "주말 점검 사항"
    }},
    {{"week": 2, ...}},
    ...최대 12주까지
  ],
  "milestones": {{
    "day_30": {{"goal": "30일 목표", "success_criteria": "성공 기준", "deliverables": ["산출물1"]}},
    "day_60": {{"goal": "60일 목표", "success_criteria": "성공 기준", "deliverables": ["산출물1"]}},
    "day_90": {{"goal": "90일 목표", "success_criteria": "성공 기준", "deliverables": ["산출물1"]}}
  }},
  "risk_scenarios": [
    {{"scenario": "실패 시나리오", "trigger": "발생 조건", "pivot_plan": "피벗 플랜"}}
  ],
  "body_markdown": "## 90-Day Sprint Plan\\n\\n(위 내용을 통합한 마크다운 본문, 3000자 이상)",
  "confidence": "HIGH"
}}

중요: 반드시 위 JSON 구조로만 응답하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.
"""


def get_calendar_system_prompt(target_year: int) -> str:
    """Calendar 섹션 전용 시스템 프롬프트 (간소화된 구조)"""
    
    terminology_rules = get_business_prompt_rules()
    
    return f"""당신은 99,000원 프리미엄 비즈니스 컨설팅 보고서를 작성하는 시니어 전략 컨설턴트입니다.

## 분석 기준년도: {target_year}년

{terminology_rules}

## 이 섹션: 12-Month Tactical Calendar
{target_year}년 1월부터 12월까지 월별 전략 캘린더를 작성합니다.

## 출력 형식 (반드시 이 JSON 구조로만 응답)

{{
  "title": "12-Month Tactical Calendar",
  "annual_theme": "{target_year}년 연간 전략 테마 (1-2문장)",
  "monthly_plans": [
    {{
      "month": 1,
      "month_name": "1월",
      "theme": "월간 테마",
      "energy_level": "HIGH/MEDIUM/LOW",
      "key_focus": "핵심 집중 영역",
      "recommended_actions": ["권장 액션1", "권장 액션2", "권장 액션3"],
      "cautions": ["금기 사항1", "금기 사항2"],
      "kpi_targets": ["월간 KPI1", "월간 KPI2"]
    }},
    {{"month": 2, ...}},
    ...12개월 전체
  ],
  "quarterly_milestones": {{
    "Q1": {{"theme": "1분기 테마", "milestone": "마일스톤", "key_metric": "핵심 지표"}},
    "Q2": {{"theme": "2분기 테마", "milestone": "마일스톤", "key_metric": "핵심 지표"}},
    "Q3": {{"theme": "3분기 테마", "milestone": "마일스톤", "key_metric": "핵심 지표"}},
    "Q4": {{"theme": "4분기 테마", "milestone": "마일스톤", "key_metric": "핵심 지표"}}
  }},
  "peak_months": ["최고 성과 예상 월 Top 3"],
  "risk_months": ["고위험 월 + 대응 전략"],
  "body_markdown": "## 12-Month Tactical Calendar\\n\\n(위 내용을 통합한 마크다운 본문, 4000자 이상)",
  "confidence": "HIGH"
}}

중요: 반드시 위 JSON 구조로만 응답하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.
"""


def get_premium_system_prompt(section_id: str, target_year: int) -> str:
    """프리미엄 섹션별 시스템 프롬프트"""
    
    # Sprint/Calendar는 전용 프롬프트 사용
    if section_id == "sprint":
        return get_sprint_system_prompt(target_year)
    if section_id == "calendar":
        return get_calendar_system_prompt(target_year)
    
    spec = PREMIUM_SECTIONS.get(section_id)
    if not spec:
        spec = PREMIUM_SECTIONS["exec"]
    
    terminology_rules = get_business_prompt_rules()
    
    base = f"""당신은 99,000원 프리미엄 비즈니스 컨설팅 보고서를 작성하는 시니어 전략 컨설턴트입니다.
맥킨지, BCG, 베인 수준의 분석적 깊이와 실행 가능성을 갖춘 보고서를 작성합니다.

## 분석 기준년도: {target_year}년

## 핵심 원칙
1. **사주 풀이 금지**: 이 보고서는 '운세'가 아니라 '경영 전략 보고서'입니다
2. **데이터 기반**: 제공된 RuleCard 데이터를 근거로 가설을 세우고 전략을 도출합니다
3. **실행 가능성**: 모든 제안은 구체적 일정, 담당자, 예산 수준을 포함해야 합니다
4. **측정 가능성**: 모든 목표는 KPI로 측정 가능해야 합니다

{terminology_rules}

## 이 섹션의 요구사항: {spec.title}
- 최소 분량: {spec.min_chars}자 이상
- 필수 포함 요소:
{chr(10).join(f'  - {elem}' for elem in spec.required_elements)}

## 출력 형식
반드시 아래 JSON 구조로만 응답하세요 (마크다운 코드블록 없이):

{{
  "title": "{spec.title}",
  "diagnosis": {{
    "current_state": "현상 진단 (500자 이상)",
    "key_issues": ["이슈1", "이슈2", "이슈3"]
  }},
  "hypotheses": [
    {{"id": "H1", "statement": "가설 내용", "confidence": "HIGH/MEDIUM/LOW", "evidence": "근거 요약"}},
    {{"id": "H2", "statement": "...", "confidence": "...", "evidence": "..."}},
    {{"id": "H3", "statement": "...", "confidence": "...", "evidence": "..."}}
  ],
  "strategy_options": [
    {{
      "id": "S1",
      "name": "전략명",
      "description": "전략 설명 (200자 이상)",
      "pros": ["장점1", "장점2"],
      "cons": ["단점1", "단점2"],
      "required_resources": "필요 자원",
      "timeline": "예상 소요 기간"
    }},
    {{"id": "S2", ...}},
    {{"id": "S3", ...}}
  ],
  "recommended_strategy": {{
    "selected_option": "S1",
    "rationale": "선택 이유 (200자 이상)",
    "execution_plan": [
      {{"week": 1, "focus": "집중 영역", "actions": ["액션1", "액션2"], "deliverables": ["산출물1"]}},
      {{"week": 2, ...}}
    ]
  }},
  "kpis": [
    {{"metric": "지표명", "current": "현재값", "target": "목표값", "measurement": "측정 방법", "frequency": "측정 주기"}}
  ],
  "risks": [
    {{"risk": "리스크 내용", "probability": "HIGH/MEDIUM/LOW", "impact": "HIGH/MEDIUM/LOW", "mitigation": "방어 전략", "early_warning": "조기 경보 신호"}}
  ],
  "evidence": {{
    "rulecard_ids": ["사용된 RuleCard ID 목록"],
    "evidence_summary": "근거 요약 (100자 이상)"
  }},
  "body_markdown": "## {spec.title}\\n\\n(위 내용을 통합한 마크다운 본문, {spec.min_chars}자 이상)",
  "confidence": "HIGH/MEDIUM/LOW"
}}
"""
    return base


def get_premium_user_prompt(
    section_id: str,
    saju_data: Dict[str, Any],
    rulecards_context: str,
    target_year: int,
    user_question: str = ""
) -> str:
    """섹션별 유저 프롬프트 생성"""
    
    spec = PREMIUM_SECTIONS.get(section_id)
    
    saju = saju_data.get("saju", saju_data)
    day_master = saju_data.get("day_master", "")
    day_master_element = saju_data.get("day_master_element", "")
    
    return f"""## 클라이언트 비즈니스 프로파일

### 의사결정자 특성 분석 데이터
- 핵심 역량 코드: {day_master} ({day_master_element})
- 분석 기준년도: {target_year}년

### 클라이언트 질문/관심사
{user_question or "종합적인 비즈니스 전략 수립"}

## 분석 근거 데이터 (RuleCard)
{rulecards_context}

---

위 데이터를 기반으로 **{spec.title if spec else section_id}** 섹션을 작성해주세요.

중요 체크리스트:
✅ 명리학/사주 용어 사용 금지 (비즈니스 용어만 사용)
✅ 최소 {spec.min_chars if spec else 3000}자 이상 작성
✅ 구체적 숫자, 날짜, 담당 포함
✅ 실행 가능한 액션 아이템
✅ 측정 가능한 KPI

반드시 JSON 형식으로만 응답하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.
"""


# ============ 룰카드 분배 ============

def distribute_rulecards_premium(
    all_cards: List[Dict[str, Any]],
    section_id: str,
    max_cards: int = 60
) -> Tuple[str, List[str]]:
    """섹션 주제에 맞게 RuleCards 분배"""
    spec = PREMIUM_SECTIONS.get(section_id)
    if not spec:
        return "", []
    
    target_topics = spec.topics
    quota = min(spec.rulecard_quota, max_cards)
    
    scored_cards = []
    for card in all_cards:
        card_topic = card.get("topic", "").lower()
        card_tags = [t.lower() for t in card.get("tags", [])]
        
        score = 0
        for topic in target_topics:
            if topic.lower() in card_topic:
                score += 3
            if any(topic.lower() in tag for tag in card_tags):
                score += 2
        
        if score > 0:
            scored_cards.append((score, card))
    
    scored_cards.sort(key=lambda x: x[0], reverse=True)
    selected = [card for _, card in scored_cards[:quota]]
    
    if len(selected) < quota:
        used_ids = {c.get("id", "") for c in selected}
        for card in all_cards:
            if card.get("id", "") not in used_ids:
                selected.append(card)
                if len(selected) >= quota:
                    break
    
    context_lines = []
    card_ids = []
    
    for card in selected:
        card_id = card.get("id", card.get("_id", f"card_{len(card_ids)}"))
        card_ids.append(card_id)
        
        topic = card.get("topic", "")
        mechanism = sanitize_for_business(card.get("mechanism", "")[:150])
        action = sanitize_for_business(card.get("action", "")[:150])
        
        line = f"[{card_id}] 분석 영역: {topic}"
        if mechanism:
            line += f"\n  → 비즈니스 시사점: {mechanism}"
        if action:
            line += f"\n  → 권장 액션: {action}"
        
        context_lines.append(line)
    
    context_str = "\n".join(context_lines) if context_lines else "분석 데이터 없음"
    
    return context_str, card_ids


# ============ 섹션별 Validation ============

@dataclass
class ValidationResult:
    is_valid: bool
    char_count: int
    missing_elements: List[str]
    forbidden_terms_found: List[str]
    needs_expansion: bool
    details: str = ""


def validate_sprint_section(content: Dict[str, Any]) -> ValidationResult:
    """Sprint 섹션 전용 검증 (간소화)"""
    missing = []
    
    body_md = content.get("body_markdown", "")
    char_count = len(body_md)
    
    # 미션 선언문
    if not content.get("mission_statement"):
        missing.append("미션 선언문")
    
    # 주간 계획 (최소 4주)
    weekly = content.get("weekly_plans", [])
    if len(weekly) < 4:
        missing.append(f"주간 계획 ({len(weekly)}/4주 이상)")
    
    # 마일스톤
    milestones = content.get("milestones", {})
    if not milestones.get("day_30") and not milestones.get("day_60") and not milestones.get("day_90"):
        missing.append("30/60/90일 마일스톤")
    
    # 금칙어 체크
    is_clean, forbidden = validate_no_forbidden_terms(body_md)
    
    # Sprint는 분량 기준 완화 (2000자 이상이면 OK)
    min_chars = 2000
    is_valid = char_count >= min_chars and len(missing) == 0
    needs_expansion = char_count < min_chars or len(missing) > 0
    
    return ValidationResult(
        is_valid=is_valid,
        char_count=char_count,
        missing_elements=missing,
        forbidden_terms_found=forbidden,
        needs_expansion=needs_expansion,
        details=f"Sprint validation: chars={char_count}, weekly={len(weekly)}"
    )


def validate_calendar_section(content: Dict[str, Any]) -> ValidationResult:
    """Calendar 섹션 전용 검증 (간소화)"""
    missing = []
    
    body_md = content.get("body_markdown", "")
    char_count = len(body_md)
    
    # 연간 테마
    if not content.get("annual_theme"):
        missing.append("연간 테마")
    
    # 월별 계획 (최소 6개월)
    monthly = content.get("monthly_plans", [])
    if len(monthly) < 6:
        missing.append(f"월별 계획 ({len(monthly)}/6개월 이상)")
    
    # 금칙어 체크
    is_clean, forbidden = validate_no_forbidden_terms(body_md)
    
    min_chars = 2500
    is_valid = char_count >= min_chars and len(missing) == 0
    needs_expansion = char_count < min_chars or len(missing) > 0
    
    return ValidationResult(
        is_valid=is_valid,
        char_count=char_count,
        missing_elements=missing,
        forbidden_terms_found=forbidden,
        needs_expansion=needs_expansion,
        details=f"Calendar validation: chars={char_count}, monthly={len(monthly)}"
    )


def validate_standard_section(content: Dict[str, Any], section_id: str) -> ValidationResult:
    """표준 섹션 검증"""
    spec = PREMIUM_SECTIONS.get(section_id)
    if not spec:
        return ValidationResult(True, 0, [], [], False)
    
    body_md = content.get("body_markdown", "")
    char_count = len(body_md)
    
    missing = []
    
    if not content.get("diagnosis", {}).get("current_state"):
        missing.append("현상 진단")
    
    hypotheses = content.get("hypotheses", [])
    if len(hypotheses) < 2:
        missing.append(f"핵심 가설 ({len(hypotheses)}/2개 이상)")
    
    options = content.get("strategy_options", [])
    if len(options) < 2:
        missing.append(f"전략 옵션 ({len(options)}/2개 이상)")
    
    kpis = content.get("kpis", [])
    if len(kpis) < 2:
        missing.append(f"KPI ({len(kpis)}/2개 이상)")
    
    is_clean, forbidden = validate_no_forbidden_terms(body_md)
    
    # 분량 기준 완화 (원래의 70%)
    min_chars = int(spec.min_chars * 0.7)
    is_valid = char_count >= min_chars and len(missing) == 0
    needs_expansion = char_count < min_chars or len(missing) > 0
    
    return ValidationResult(
        is_valid=is_valid,
        char_count=char_count,
        missing_elements=missing,
        forbidden_terms_found=forbidden,
        needs_expansion=needs_expansion,
        details=f"Standard validation: chars={char_count}/{min_chars}"
    )


def validate_section_output(content: Dict[str, Any], section_id: str) -> ValidationResult:
    """섹션 타입에 따른 검증 분기"""
    spec = PREMIUM_SECTIONS.get(section_id)
    if not spec:
        return ValidationResult(True, 0, [], [], False, "No spec found")
    
    if spec.validation_type == "sprint":
        return validate_sprint_section(content)
    elif spec.validation_type == "calendar":
        return validate_calendar_section(content)
    else:
        return validate_standard_section(content, section_id)


# ============ Polish Pass ============

def polish_section(content: Dict[str, Any], section_id: str) -> Dict[str, Any]:
    """섹션 후처리: 문체 통일, 금칙어 제거"""
    
    if "body_markdown" in content:
        content["body_markdown"] = sanitize_for_business(content["body_markdown"])
    
    if "diagnosis" in content and isinstance(content["diagnosis"], dict):
        if "current_state" in content["diagnosis"]:
            content["diagnosis"]["current_state"] = sanitize_for_business(
                content["diagnosis"]["current_state"]
            )
    
    if "hypotheses" in content:
        for h in content["hypotheses"]:
            if isinstance(h, dict):
                h["statement"] = sanitize_for_business(h.get("statement", ""))
                h["evidence"] = sanitize_for_business(h.get("evidence", ""))
    
    if "strategy_options" in content:
        for s in content["strategy_options"]:
            if isinstance(s, dict):
                s["description"] = sanitize_for_business(s.get("description", ""))
    
    if "recommended_strategy" in content and isinstance(content["recommended_strategy"], dict):
        content["recommended_strategy"]["rationale"] = sanitize_for_business(
            content["recommended_strategy"].get("rationale", "")
        )
    
    if "risks" in content:
        for r in content["risks"]:
            if isinstance(r, dict):
                r["risk"] = sanitize_for_business(r.get("risk", ""))
                r["mitigation"] = sanitize_for_business(r.get("mitigation", ""))
    
    # Sprint 전용 필드
    if "mission_statement" in content:
        content["mission_statement"] = sanitize_for_business(content["mission_statement"])
    
    if "weekly_plans" in content:
        for wp in content["weekly_plans"]:
            if isinstance(wp, dict) and "theme" in wp:
                wp["theme"] = sanitize_for_business(wp["theme"])
    
    # Calendar 전용 필드
    if "annual_theme" in content:
        content["annual_theme"] = sanitize_for_business(content["annual_theme"])
    
    return content


# ============ 메인 빌더 ============

class PremiumReportBuilder:
    """99,000원 프리미엄 리포트 빌더 v3"""
    
    def __init__(self):
        self._client = None
        self._semaphore = None
    
    def _get_client(self) -> AsyncOpenAI:
        settings = get_settings()
        api_key = get_openai_api_key()
        return AsyncOpenAI(
            api_key=api_key,
            timeout=httpx.Timeout(float(settings.report_section_timeout), connect=15.0),
            max_retries=0  # 수동 retry 구현
        )
    
    async def _call_openai_with_retry(
        self,
        messages: List[Dict[str, str]],
        section_id: str,
        max_retries: int = 3,
        base_delay: float = 2.0
    ) -> str:
        """
        OpenAI 호출 + Exponential Backoff Retry
        429 (Rate Limit), 5xx (Server Error) 시 재시도
        """
        settings = get_settings()
        last_error = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"[Section:{section_id}] OpenAI 호출 시도 {attempt + 1}/{max_retries}")
                
                response = await self._client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    max_tokens=settings.report_section_max_output_tokens,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                logger.info(f"[Section:{section_id}] OpenAI 호출 성공 | 응답 길이: {len(content or '')}자")
                return content
                
            except RateLimitError as e:
                last_error = e
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"[Section:{section_id}] 429 Rate Limit | "
                    f"Attempt {attempt + 1}/{max_retries} | "
                    f"Retry after {delay:.1f}s | Error: {str(e)[:100]}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    
            except (APIError, APIConnectionError, APITimeoutError) as e:
                last_error = e
                status = getattr(e, 'status_code', 'N/A')
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"[Section:{section_id}] API Error (status={status}) | "
                    f"Attempt {attempt + 1}/{max_retries} | "
                    f"Retry after {delay:.1f}s | Error: {str(e)[:100]}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                last_error = e
                logger.error(
                    f"[Section:{section_id}] 예상치 못한 에러 | "
                    f"Type: {type(e).__name__} | Error: {str(e)[:200]}"
                )
                # 예상치 못한 에러는 즉시 raise
                raise
        
        # 모든 재시도 실패
        raise last_error or Exception("Unknown error after retries")
    
    async def build_premium_report(
        self,
        saju_data: Dict[str, Any],
        rulecards: List[Dict[str, Any]],
        target_year: int = 2026,
        user_question: str = "",
        name: str = "고객",
        mode: str = "premium"
    ) -> Dict[str, Any]:
        """7개 섹션 순차 생성 + 합성 + Polish (안정성 우선)"""
        settings = get_settings()
        start_time = time.time()
        
        # 동시성 1로 제한 (안정성 우선)
        concurrency = settings.report_max_concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._client = self._get_client()
        
        logger.info(
            f"[PremiumReport] ========== 시작 ==========\n"
            f"  Year={target_year} | Cards={len(rulecards)} | Mode={mode} | Concurrency={concurrency}"
        )
        
        section_ids = list(PREMIUM_SECTIONS.keys())
        tasks = [
            self._generate_section_with_expansion(
                section_id=sid,
                saju_data=saju_data,
                rulecards=rulecards,
                target_year=target_year,
                user_question=user_question
            )
            for sid in section_ids
        ]
        
        # 병렬 실행 (semaphore로 동시성 제한)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 결과 수집 + 상세 에러 로깅
        sections = []
        total_rulecards = 0
        errors = []
        
        for sid, result in zip(section_ids, results):
            if isinstance(result, Exception):
                error_detail = {
                    "section": sid,
                    "error_type": type(result).__name__,
                    "error_message": str(result)[:500],
                    "traceback": traceback.format_exc()[:1000]
                }
                errors.append(error_detail)
                
                logger.error(
                    f"[PremiumReport] ❌ 섹션 실패: {sid}\n"
                    f"  Error Type: {type(result).__name__}\n"
                    f"  Error: {str(result)[:300]}\n"
                    f"  Traceback: {traceback.format_exc()[:500]}"
                )
                
                sections.append(self._create_error_section(sid, target_year, str(result)[:200]))
            else:
                polished = polish_section(result["content"], sid)
                
                spec = PREMIUM_SECTIONS.get(sid)
                
                # Sprint/Calendar 전용 필드 처리
                section_data = {
                    "id": sid,
                    "title": spec.title if spec else sid,
                    "confidence": polished.get("confidence", "MEDIUM"),
                    "rulecard_ids": result.get("rulecard_ids", []),
                    "body_markdown": polished.get("body_markdown", ""),
                    "char_count": result.get("char_count", 0),
                    "latency_ms": result.get("latency_ms", 0)
                }
                
                # 표준 섹션 필드
                if spec and spec.validation_type == "standard":
                    section_data.update({
                        "diagnosis": polished.get("diagnosis", {}),
                        "hypotheses": polished.get("hypotheses", []),
                        "strategy_options": polished.get("strategy_options", []),
                        "recommended_strategy": polished.get("recommended_strategy", {}),
                        "kpis": polished.get("kpis", []),
                        "risks": polished.get("risks", []),
                        "evidence": polished.get("evidence", {}),
                    })
                
                # Sprint 전용 필드
                if spec and spec.validation_type == "sprint":
                    section_data.update({
                        "mission_statement": polished.get("mission_statement", ""),
                        "weekly_plans": polished.get("weekly_plans", []),
                        "milestones": polished.get("milestones", {}),
                        "risk_scenarios": polished.get("risk_scenarios", []),
                    })
                
                # Calendar 전용 필드
                if spec and spec.validation_type == "calendar":
                    section_data.update({
                        "annual_theme": polished.get("annual_theme", ""),
                        "monthly_plans": polished.get("monthly_plans", []),
                        "quarterly_milestones": polished.get("quarterly_milestones", {}),
                        "peak_months": polished.get("peak_months", []),
                        "risk_months": polished.get("risk_months", []),
                    })
                
                sections.append(section_data)
                total_rulecards += len(result.get("rulecard_ids", []))
                
                logger.info(f"[PremiumReport] ✅ 섹션 성공: {sid} | Chars={result.get('char_count', 0)}")
        
        total_latency = int((time.time() - start_time) * 1000)
        total_chars = sum(s.get("char_count", 0) for s in sections)
        
        report = {
            "target_year": target_year,
            "sections": sections,
            "meta": {
                "total_tokens_estimate": int(total_chars / 2),
                "total_chars": total_chars,
                "mode": "premium_business_30p",
                "generated_at": datetime.now().isoformat(),
                "llm_model": settings.openai_model,
                "section_count": len(sections),
                "success_count": len(sections) - len(errors),
                "error_count": len(errors),
                "rulecards_used_total": total_rulecards,
                "latency_ms": total_latency,
                "concurrency": concurrency,
                "errors": errors if errors else None
            },
            "legacy": self._create_legacy_compat(sections, target_year, name)
        }
        
        logger.info(
            f"[PremiumReport] ========== 완료 ==========\n"
            f"  Sections={len(sections)} | Success={len(sections) - len(errors)} | Errors={len(errors)}\n"
            f"  Chars={total_chars} | Latency={total_latency}ms"
        )
        
        return report
    
    async def regenerate_single_section(
        self,
        section_id: str,
        saju_data: Dict[str, Any],
        rulecards: List[Dict[str, Any]],
        target_year: int = 2026,
        user_question: str = ""
    ) -> Dict[str, Any]:
        """단일 섹션만 재생성 (Sprint 복구용)"""
        
        if section_id not in PREMIUM_SECTIONS:
            raise ValueError(f"Invalid section_id: {section_id}. Valid: {list(PREMIUM_SECTIONS.keys())}")
        
        settings = get_settings()
        self._semaphore = asyncio.Semaphore(1)
        self._client = self._get_client()
        
        logger.info(f"[SingleSection] 단독 재생성 시작: {section_id}")
        
        try:
            result = await self._generate_section_with_expansion(
                section_id=section_id,
                saju_data=saju_data,
                rulecards=rulecards,
                target_year=target_year,
                user_question=user_question
            )
            
            polished = polish_section(result["content"], section_id)
            spec = PREMIUM_SECTIONS[section_id]
            
            section_data = {
                "id": section_id,
                "title": spec.title,
                "confidence": polished.get("confidence", "MEDIUM"),
                "rulecard_ids": result.get("rulecard_ids", []),
                "body_markdown": polished.get("body_markdown", ""),
                "char_count": result.get("char_count", 0),
                "latency_ms": result.get("latency_ms", 0),
                "regenerated": True
            }
            
            # 타입별 필드 추가
            if spec.validation_type == "sprint":
                section_data.update({
                    "mission_statement": polished.get("mission_statement", ""),
                    "weekly_plans": polished.get("weekly_plans", []),
                    "milestones": polished.get("milestones", {}),
                    "risk_scenarios": polished.get("risk_scenarios", []),
                })
            elif spec.validation_type == "calendar":
                section_data.update({
                    "annual_theme": polished.get("annual_theme", ""),
                    "monthly_plans": polished.get("monthly_plans", []),
                    "quarterly_milestones": polished.get("quarterly_milestones", {}),
                })
            else:
                section_data.update({
                    "diagnosis": polished.get("diagnosis", {}),
                    "hypotheses": polished.get("hypotheses", []),
                    "strategy_options": polished.get("strategy_options", []),
                    "recommended_strategy": polished.get("recommended_strategy", {}),
                    "kpis": polished.get("kpis", []),
                    "risks": polished.get("risks", []),
                })
            
            logger.info(f"[SingleSection] 완료: {section_id} | Chars={result.get('char_count', 0)}")
            
            return {
                "success": True,
                "section": section_data
            }
            
        except Exception as e:
            logger.error(f"[SingleSection] 실패: {section_id} | {str(e)[:200]}")
            return {
                "success": False,
                "section_id": section_id,
                "error": str(e)[:500],
                "error_type": type(e).__name__
            }
    
    async def _generate_section_with_expansion(
        self,
        section_id: str,
        saju_data: Dict[str, Any],
        rulecards: List[Dict[str, Any]],
        target_year: int,
        user_question: str,
        max_expansions: int = 1  # 확장 1회로 제한 (안정성)
    ) -> Dict[str, Any]:
        """섹션 생성 + 자동 확장 루프"""
        
        async with self._semaphore:
            start_time = time.time()
            settings = get_settings()
            
            rulecards_context, rulecard_ids = distribute_rulecards_premium(
                rulecards,
                section_id,
                settings.report_section_max_rulecards
            )
            
            system_prompt = get_premium_system_prompt(section_id, target_year)
            user_prompt = get_premium_user_prompt(
                section_id, saju_data, rulecards_context, target_year, user_question
            )
            
            logger.info(f"[Section:{section_id}] 생성 시작 | Cards={len(rulecard_ids)}")
            
            content = None
            expansion_count = 0
            last_validation = None
            
            while expansion_count <= max_expansions:
                try:
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                    
                    # Retry 로직 포함된 OpenAI 호출
                    content_str = await self._call_openai_with_retry(
                        messages=messages,
                        section_id=section_id,
                        max_retries=3,
                        base_delay=2.0
                    )
                    
                    content = self._parse_json(content_str)
                    
                    if not content:
                        raise ValueError(f"JSON 파싱 실패. 응답 길이: {len(content_str or '')}자")
                    
                    # 검증
                    validation = validate_section_output(content, section_id)
                    last_validation = validation
                    
                    logger.info(
                        f"[Section:{section_id}] 검증 결과 | "
                        f"Valid={validation.is_valid} | Chars={validation.char_count} | "
                        f"Missing={validation.missing_elements} | {validation.details}"
                    )
                    
                    if validation.is_valid:
                        break
                    
                    if expansion_count >= max_expansions:
                        logger.warning(f"[Section:{section_id}] 최대 확장 도달, 현재 결과 사용")
                        break
                    
                    expansion_count += 1
                    
                except Exception as e:
                    logger.error(
                        f"[Section:{section_id}] 생성 에러 (attempt {expansion_count + 1}) | "
                        f"Type: {type(e).__name__} | Error: {str(e)[:200]}"
                    )
                    if expansion_count >= max_expansions:
                        raise
                    expansion_count += 1
            
            latency_ms = int((time.time() - start_time) * 1000)
            char_count = len(content.get("body_markdown", "")) if content else 0
            
            logger.info(
                f"[Section:{section_id}] 완료 | "
                f"Chars={char_count} | Latency={latency_ms}ms | Expansions={expansion_count}"
            )
            
            return {
                "content": content,
                "rulecard_ids": rulecard_ids,
                "char_count": char_count,
                "latency_ms": latency_ms
            }
    
    def _create_error_section(self, section_id: str, target_year: int, error_msg: str = "") -> Dict[str, Any]:
        """에러 발생 시 폴백 섹션"""
        spec = PREMIUM_SECTIONS.get(section_id)
        return {
            "id": section_id,
            "title": spec.title if spec else section_id,
            "confidence": "LOW",
            "rulecard_ids": [],
            "body_markdown": f"## {spec.title if spec else section_id}\n\n"
                           f"{target_year}년 분석 데이터 처리 중 일시적 오류가 발생했습니다.\n"
                           f"잠시 후 다시 시도해주세요.\n\n"
                           f"_Error: {error_msg[:100]}_" if error_msg else "",
            "diagnosis": {"current_state": "데이터 처리 오류", "key_issues": []},
            "hypotheses": [],
            "strategy_options": [],
            "recommended_strategy": {},
            "kpis": [],
            "risks": [],
            "evidence": {"rulecard_ids": [], "evidence_summary": ""},
            "char_count": 0,
            "latency_ms": 0,
            "error": True,
            "error_message": error_msg[:200]
        }
    
    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        """JSON 파싱 (강화)"""
        if not content:
            return None
        
        text = content.strip()
        
        # 코드블록 제거
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].strip().startswith("```") else lines
            text = "\n".join(lines)
        
        # 직접 파싱
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # JSON 부분 추출
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        logger.warning(f"JSON 파싱 실패. 원문 앞 500자: {text[:500]}")
        return None
    
    def _create_legacy_compat(
        self,
        sections: List[Dict[str, Any]],
        target_year: int,
        name: str
    ) -> Dict[str, Any]:
        """레거시 프론트엔드 호환용 필드"""
        
        exec_section = next((s for s in sections if s["id"] == "exec"), {})
        
        strengths = []
        for h in exec_section.get("hypotheses", []):
            if h.get("confidence") == "HIGH":
                strengths.append(h.get("statement", ""))
        
        risks = []
        for r in exec_section.get("risks", [])[:3]:
            risks.append(r.get("risk", ""))
        
        action_plan = []
        rec = exec_section.get("recommended_strategy", {})
        for step in rec.get("execution_plan", [])[:5]:
            if step.get("actions"):
                action_plan.extend(step["actions"][:2])
        
        return {
            "success": True,
            "summary": f"{target_year}년 프리미엄 비즈니스 컨설팅 보고서",
            "day_master_analysis": exec_section.get("diagnosis", {}).get("current_state", ""),
            "strengths": strengths[:5],
            "risks": risks,
            "answer": exec_section.get("body_markdown", "")[:1000],
            "action_plan": action_plan[:5],
            "lucky_periods": [],
            "caution_periods": [],
            "lucky_elements": {},
            "blessing": f"{name}님의 {target_year}년 성공을 응원합니다!",
            "disclaimer": "본 보고서는 데이터 기반 분석 참고 자료이며, 전문적 조언을 대체하지 않습니다."
        }


# 싱글톤 인스턴스
premium_report_builder = PremiumReportBuilder()
report_builder = premium_report_builder
