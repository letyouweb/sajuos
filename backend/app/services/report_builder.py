"""
SajuOS Premium Report Builder
- 7개 섹션 분할 생성 (Chaining)
- 병렬 처리 (asyncio.gather + Semaphore)
- 룰카드 분배 + 압축형 payload
- 최종 합성 JSON 반환
"""
import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from openai import AsyncOpenAI
import httpx

from app.config import get_settings
from app.services.openai_key import get_openai_api_key

logger = logging.getLogger(__name__)


# ============ 섹션 정의 ============

SECTION_SPECS = {
    "exec": {
        "id": "exec",
        "title": "Executive Summary",
        "pages": 2,
        "rulecard_quota": 50,
        "topics": ["general", "personality", "yearly_fortune"],
        "min_requirements": {
            "key_insights": 10,
            "risks": 5,
            "action_items_30day": 10
        }
    },
    "money": {
        "id": "money",
        "title": "Money & Cashflow",
        "pages": 5,
        "rulecard_quota": 80,
        "topics": ["wealth", "finance", "investment"],
        "min_requirements": {
            "cashflow_checklist": 25,
            "risk_cases": 10,
            "improvement_plans": 12
        }
    },
    "business": {
        "id": "business",
        "title": "Business Strategy",
        "pages": 5,
        "rulecard_quota": 80,
        "topics": ["career", "business", "leadership"],
        "min_requirements": {
            "strategy_points": 15,
            "opportunities": 10,
            "action_plans": 12
        }
    },
    "team": {
        "id": "team",
        "title": "Team & Partner Risk",
        "pages": 4,
        "rulecard_quota": 60,
        "topics": ["relationship", "partnership", "conflict"],
        "min_requirements": {
            "partner_profiles": 5,
            "risk_scenarios": 8,
            "mitigation_strategies": 10
        }
    },
    "health": {
        "id": "health",
        "title": "Health & Performance",
        "pages": 3,
        "rulecard_quota": 50,
        "topics": ["health", "energy", "wellness"],
        "min_requirements": {
            "health_checkpoints": 15,
            "energy_tips": 10,
            "warning_signs": 8
        }
    },
    "calendar": {
        "id": "calendar",
        "title": "12-Month Calendar",
        "pages": 6,
        "rulecard_quota": 100,
        "topics": ["monthly", "timing", "seasonal"],
        "min_requirements": {
            "months": 12,
            "keywords_per_month": 3,
            "actions_per_month": 5,
            "taboos_per_month": 3
        }
    },
    "sprint": {
        "id": "sprint",
        "title": "90-Day Sprint Plan",
        "pages": 5,
        "rulecard_quota": 80,
        "topics": ["action", "planning", "execution"],
        "min_requirements": {
            "weeks": 12,
            "goals_per_week": 2,
            "kpis_per_week": 2,
            "checkpoints": 4
        }
    }
}


# ============ 섹션별 프롬프트 ============

def get_section_system_prompt(section_id: str, target_year: int) -> str:
    """섹션별 시스템 프롬프트 생성"""
    
    base = f"""당신은 SajuOS 프리미엄 비즈니스 컨설팅 시스템입니다.
50년 경력 명리학 마스터 + 맥킨지급 전략 컨설턴트의 융합 지능입니다.

## 절대 규칙
1. 모든 분석은 {target_year}년 기준입니다
2. 출력은 반드시 JSON 형식만 (마크다운 코드블록 없이)
3. 제공된 RuleCard 근거를 반드시 활용
4. 추상적 표현 금지 → 구체적 숫자/날짜/체크리스트로
5. 의학/법률/투자 단정적 조언 금지

## 톤앤매너
- 프리미엄 비즈니스 컨설팅 어조
- 전문적이면서 따뜻한 조언
- 실행 가능한 구체적 가이드
"""

    section_prompts = {
        "exec": f"""{base}

## Executive Summary 섹션 작성 지침
{target_year}년 전체 운세의 핵심 요약을 작성합니다.

### 필수 출력 JSON 구조:
{{
  "title": "Executive Summary",
  "markdown": "## Executive Summary\\n\\n...(상세 마크다운 내용)...",
  "highlights": [
    {{"category": "기회", "content": "...", "priority": "HIGH"}},
    ... (최소 10개)
  ],
  "risks": [
    {{"category": "재물", "content": "...", "severity": "MEDIUM", "mitigation": "..."}},
    ... (최소 5개)
  ],
  "actionItems": [
    {{"timeframe": "30일 내", "action": "...", "expected_outcome": "..."}},
    ... (최소 10개)
  ],
  "keyMetrics": {{
    "overall_fortune_score": 85,
    "wealth_potential": "HIGH",
    "career_momentum": "RISING",
    "relationship_stability": "STABLE"
  }},
  "evidence": {{
    "ruleCardIds": ["card_id_1", "card_id_2", ...],
    "topTags": ["태그1", "태그2", ...]
  }},
  "confidence": "HIGH"
}}

### 분량 요구사항:
- markdown: 최소 1500자 이상
- highlights: 최소 10개
- risks: 최소 5개
- actionItems: 최소 10개 (30일 내 실행 가능한 것)
""",

        "money": f"""{base}

## Money & Cashflow 섹션 작성 지침
{target_year}년 재물운과 현금흐름 전략을 상세 분석합니다.

### 필수 출력 JSON 구조:
{{
  "title": "Money & Cashflow",
  "markdown": "## Money & Cashflow\\n\\n...(상세 마크다운 내용)...",
  "wealthStructure": {{
    "type": "정재형/편재형/혼합형",
    "description": "...",
    "strengths": ["...", "..."],
    "weaknesses": ["...", "..."]
  }},
  "cashflowChecklist": [
    {{"id": 1, "category": "수입", "item": "...", "status": "점검필요", "action": "..."}},
    ... (최소 25개)
  ],
  "riskCases": [
    {{"scenario": "...", "probability": "HIGH/MEDIUM/LOW", "impact": "...", "prevention": "..."}},
    ... (최소 10개)
  ],
  "improvementPlans": [
    {{"area": "...", "currentState": "...", "targetState": "...", "steps": ["...", "..."], "timeline": "..."}},
    ... (최소 12개)
  ],
  "monthlyForecast": [
    {{"month": "1월", "income_energy": "HIGH", "expense_risk": "LOW", "advice": "..."}},
    ... (12개월 전체)
  ],
  "evidence": {{
    "ruleCardIds": [...],
    "topTags": [...]
  }},
  "confidence": "HIGH"
}}

### 분량 요구사항:
- markdown: 최소 2500자 이상
- cashflowChecklist: 최소 25개
- riskCases: 최소 10개
- improvementPlans: 최소 12개
""",

        "business": f"""{base}

## Business Strategy 섹션 작성 지침
{target_year}년 사업/커리어 전략을 상세 분석합니다.

### 필수 출력 JSON 구조:
{{
  "title": "Business Strategy",
  "markdown": "## Business Strategy\\n\\n...(상세 마크다운 내용)...",
  "careerDNA": {{
    "type": "창업형/조직형/하이브리드",
    "coreCompetencies": ["...", "..."],
    "blindSpots": ["...", "..."],
    "idealRoles": ["...", "..."]
  }},
  "strategyPoints": [
    {{"priority": 1, "strategy": "...", "rationale": "...", "expectedROI": "..."}},
    ... (최소 15개)
  ],
  "opportunities": [
    {{"area": "...", "timing": "...", "actionRequired": "...", "successProbability": "HIGH"}},
    ... (최소 10개)
  ],
  "actionPlans": [
    {{"quarter": "Q1", "focus": "...", "goals": ["...", "..."], "kpis": ["...", "..."]}},
    ... (최소 12개, 분기별 + 월별)
  ],
  "competitorAnalysis": {{
    "yourPosition": "...",
    "differentiators": ["...", "..."],
    "threatsToWatch": ["...", "..."]
  }},
  "evidence": {{
    "ruleCardIds": [...],
    "topTags": [...]
  }},
  "confidence": "HIGH"
}}

### 분량 요구사항:
- markdown: 최소 2500자 이상
- strategyPoints: 최소 15개
- opportunities: 최소 10개
- actionPlans: 최소 12개
""",

        "team": f"""{base}

## Team & Partner Risk 섹션 작성 지침
{target_year}년 대인관계 및 파트너십 리스크를 분석합니다.

### 필수 출력 JSON 구조:
{{
  "title": "Team & Partner Risk",
  "markdown": "## Team & Partner Risk\\n\\n...(상세 마크다운 내용)...",
  "relationshipPattern": {{
    "style": "협력형/독립형/리더형",
    "strengths": ["...", "..."],
    "watchPoints": ["...", "..."]
  }},
  "partnerProfiles": [
    {{"type": "이상적 파트너", "characteristics": ["...", "..."], "howToFind": "...", "redFlags": ["...", "..."]}},
    ... (최소 5개 유형)
  ],
  "riskScenarios": [
    {{"scenario": "...", "triggers": ["...", "..."], "earlyWarnings": ["...", "..."], "response": "..."}},
    ... (최소 8개)
  ],
  "mitigationStrategies": [
    {{"risk": "...", "strategy": "...", "timeline": "...", "checkpoints": ["...", "..."]}},
    ... (최소 10개)
  ],
  "teamDynamics": {{
    "optimalTeamSize": "...",
    "rolesYouExcelAt": ["...", "..."],
    "rolestoDelegate": ["...", "..."]
  }},
  "evidence": {{
    "ruleCardIds": [...],
    "topTags": [...]
  }},
  "confidence": "HIGH"
}}

### 분량 요구사항:
- markdown: 최소 2000자 이상
- partnerProfiles: 최소 5개
- riskScenarios: 최소 8개
- mitigationStrategies: 최소 10개
""",

        "health": f"""{base}

## Health & Performance 섹션 작성 지침
{target_year}년 건강 및 에너지 관리 전략을 분석합니다.

### 필수 출력 JSON 구조:
{{
  "title": "Health & Performance",
  "markdown": "## Health & Performance\\n\\n...(상세 마크다운 내용)...",
  "energyProfile": {{
    "constitution": "...",
    "peakHours": ["...", "..."],
    "lowEnergyPeriods": ["...", "..."],
    "seasonalPattern": "..."
  }},
  "healthCheckpoints": [
    {{"area": "심혈관", "checkItem": "...", "frequency": "월1회", "warningLevel": "관심필요"}},
    ... (최소 15개)
  ],
  "energyTips": [
    {{"category": "수면", "tip": "...", "expectedBenefit": "...", "implementation": "..."}},
    ... (최소 10개)
  ],
  "warningSigns": [
    {{"sign": "...", "possibleCause": "...", "immediateAction": "...", "professionalHelp": "..."}},
    ... (최소 8개)
  ],
  "seasonalGuide": [
    {{"season": "봄", "focus": "...", "dos": ["...", "..."], "donts": ["...", "..."]}},
    ... (4계절)
  ],
  "burnoutPrevention": {{
    "riskLevel": "MEDIUM",
    "triggers": ["...", "..."],
    "recoveryPlan": ["...", "..."]
  }},
  "evidence": {{
    "ruleCardIds": [...],
    "topTags": [...]
  }},
  "confidence": "HIGH"
}}

### 분량 요구사항:
- markdown: 최소 1500자 이상
- healthCheckpoints: 최소 15개
- energyTips: 최소 10개
- warningSigns: 최소 8개

주의: 의학적 진단은 하지 않습니다. "전문가 상담 권장" 문구를 포함하세요.
""",

        "calendar": f"""{base}

## 12-Month Calendar 섹션 작성 지침
{target_year}년 월별 전술 캘린더를 상세 작성합니다.

### 필수 출력 JSON 구조:
{{
  "title": "12-Month Calendar",
  "markdown": "## 12-Month Calendar\\n\\n...(상세 마크다운 내용)...",
  "yearOverview": {{
    "theme": "{target_year}년 테마",
    "bestMonths": ["...월", "...월", "...월"],
    "cautionMonths": ["...월", "...월"],
    "pivotPoints": ["..."]
  }},
  "monthlyCalendar": [
    {{
      "month": "1월",
      "theme": "...",
      "keywords": ["키워드1", "키워드2", "키워드3"],
      "energy": {{"level": "HIGH/MEDIUM/LOW", "trend": "상승/하락/유지"}},
      "recommendedActions": [
        {{"priority": 1, "action": "...", "timing": "상순/중순/하순", "expected": "..."}},
        ... (최소 5개)
      ],
      "taboos": [
        {{"item": "...", "reason": "...", "alternative": "..."}},
        ... (최소 3개)
      ],
      "luckyElements": {{"color": "...", "direction": "...", "number": "..."}},
      "keyDates": ["1월 X일: ...", "1월 Y일: ..."]
    }},
    ... (12개월 전체)
  ],
  "quarterSummary": [
    {{"quarter": "Q1", "focus": "...", "goals": ["...", "..."], "risks": ["...", "..."]}},
    ... (4분기)
  ],
  "evidence": {{
    "ruleCardIds": [...],
    "topTags": [...]
  }},
  "confidence": "HIGH"
}}

### 분량 요구사항:
- markdown: 최소 3000자 이상
- monthlyCalendar: 12개월 전체 필수
- 각 월별 recommendedActions: 최소 5개
- 각 월별 taboos: 최소 3개
- 각 월별 keywords: 정확히 3개
""",

        "sprint": f"""{base}

## 90-Day Sprint Plan 섹션 작성 지침
{target_year}년 시작 90일 실행 계획을 상세 작성합니다.

### 필수 출력 JSON 구조:
{{
  "title": "90-Day Sprint Plan",
  "markdown": "## 90-Day Sprint Plan\\n\\n...(상세 마크다운 내용)...",
  "sprintOverview": {{
    "mission": "90일 미션 한 줄",
    "northStar": "궁극적 목표",
    "successCriteria": ["...", "...", "..."]
  }},
  "weeklyPlan": [
    {{
      "week": 1,
      "theme": "...",
      "goals": [
        {{"goal": "...", "measurable": "...", "deadline": "..."}},
        {{"goal": "...", "measurable": "...", "deadline": "..."}}
      ],
      "kpis": [
        {{"metric": "...", "target": "...", "current": "baseline"}},
        {{"metric": "...", "target": "...", "current": "baseline"}}
      ],
      "actions": [
        {{"day": "월", "action": "...", "duration": "..."}},
        ... (매일 액션)
      ],
      "risks": ["...", "..."],
      "checkpoint": "주말 점검 포인트"
    }},
    ... (12주 전체)
  ],
  "milestones": [
    {{"day": 30, "milestone": "...", "deliverables": ["...", "..."], "celebration": "..."}},
    {{"day": 60, "milestone": "...", "deliverables": ["...", "..."], "celebration": "..."}},
    {{"day": 90, "milestone": "...", "deliverables": ["...", "..."], "celebration": "..."}}
  ],
  "contingencyPlans": [
    {{"ifScenario": "...", "thenAction": "...", "adjustedTimeline": "..."}}
  ],
  "accountability": {{
    "dailyHabit": "...",
    "weeklyReview": "...",
    "monthlyRetro": "..."
  }},
  "evidence": {{
    "ruleCardIds": [...],
    "topTags": [...]
  }},
  "confidence": "HIGH"
}}

### 분량 요구사항:
- markdown: 최소 2500자 이상
- weeklyPlan: 12주 전체 필수
- 각 주별 goals: 최소 2개
- 각 주별 kpis: 최소 2개
- milestones: 30일/60일/90일 필수
"""
    }
    
    return section_prompts.get(section_id, base)


def get_section_user_prompt(
    section_id: str,
    saju_data: Dict[str, Any],
    rulecards_context: str,
    target_year: int,
    user_question: str = ""
) -> str:
    """섹션별 유저 프롬프트 생성"""
    
    # 사주 정보 추출
    saju = saju_data.get("saju", saju_data)
    year_p = _get_pillar_str(saju.get("year_pillar", {}))
    month_p = _get_pillar_str(saju.get("month_pillar", {}))
    day_p = _get_pillar_str(saju.get("day_pillar", {}))
    hour_p = _get_pillar_str(saju.get("hour_pillar", {})) or "미상"
    
    day_master = saju_data.get("day_master", "")
    day_master_element = saju_data.get("day_master_element", "")
    
    return f"""## 분석 대상 사주 정보

- 년주: {year_p}
- 월주: {month_p}
- 일주: {day_p}
- 시주: {hour_p}
- 일간: {day_master} ({day_master_element})

## 분석 기준년도: {target_year}년

## 사용자 질문/관심사
{user_question or "종합 운세 분석"}

## 참고 RuleCard 데이터 (근거로 활용)
{rulecards_context}

위 정보를 바탕으로 해당 섹션을 작성해주세요.
반드시 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이).
"""


def _get_pillar_str(pillar_data) -> str:
    """기둥 데이터에서 간지 문자열 추출"""
    if isinstance(pillar_data, dict):
        if pillar_data.get("ganji"):
            return pillar_data["ganji"]
        gan = pillar_data.get("gan", "")
        ji = pillar_data.get("ji", "")
        if gan and ji:
            return gan + ji
    elif isinstance(pillar_data, str):
        return pillar_data
    return ""


# ============ 룰카드 분배 ============

def distribute_rulecards(
    all_cards: List[Dict[str, Any]],
    section_id: str,
    saju_data: Dict[str, Any],
    max_cards: int = 60
) -> Tuple[str, List[str]]:
    """
    섹션에 맞는 룰카드 분배 + 압축형 payload 생성
    
    Returns:
        (압축된 컨텍스트 문자열, 사용된 카드 ID 리스트)
    """
    spec = SECTION_SPECS.get(section_id, {})
    target_topics = spec.get("topics", [])
    quota = min(spec.get("rulecard_quota", 60), max_cards)
    
    # 1. 토픽 매칭 카드 우선
    matched_cards = []
    other_cards = []
    
    for card in all_cards:
        card_topic = card.get("topic", "").lower()
        card_tags = [t.lower() for t in card.get("tags", [])]
        
        # 토픽 매칭 체크
        is_matched = any(
            topic.lower() in card_topic or 
            any(topic.lower() in tag for tag in card_tags)
            for topic in target_topics
        )
        
        if is_matched:
            matched_cards.append(card)
        else:
            other_cards.append(card)
    
    # 2. 매칭 카드 + 나머지로 quota 채우기
    selected = matched_cards[:quota]
    if len(selected) < quota:
        remaining = quota - len(selected)
        selected.extend(other_cards[:remaining])
    
    # 3. 압축형 payload 생성
    compressed_cards = []
    card_ids = []
    
    for card in selected:
        card_id = card.get("id", card.get("_id", f"card_{len(card_ids)}"))
        card_ids.append(card_id)
        
        compressed = {
            "id": card_id,
            "topic": card.get("topic", ""),
            "tags": card.get("tags", [])[:3],  # 태그 3개까지
            "title": card.get("title", card.get("heading", "")),
            "summary": _extract_summary(card)
        }
        compressed_cards.append(compressed)
    
    # 4. 컨텍스트 문자열 생성
    context_lines = []
    for c in compressed_cards:
        line = f"[{c['id']}] {c['topic']} | {c['title']}"
        if c['summary']:
            line += f" - {c['summary']}"
        context_lines.append(line)
    
    context_str = "\n".join(context_lines) if context_lines else "RuleCard 데이터 없음"
    
    return context_str, card_ids


def _extract_summary(card: Dict[str, Any]) -> str:
    """카드에서 1-2문장 핵심 요약 추출"""
    # mechanism, action, description 등에서 추출
    for field in ["mechanism", "action", "description", "content"]:
        value = card.get(field, "")
        if value:
            # 첫 문장만 (100자 제한)
            sentences = value.split(".")
            if sentences:
                summary = sentences[0].strip()
                if len(summary) > 100:
                    summary = summary[:97] + "..."
                return summary
    return ""


# ============ 섹션 생성 ============

class ReportBuilder:
    """프리미엄 리포트 빌더"""
    
    def __init__(self):
        self._client = None
        self._semaphore = None
    
    def _get_client(self) -> AsyncOpenAI:
        """OpenAI 클라이언트 생성"""
        settings = get_settings()
        api_key = get_openai_api_key()
        return AsyncOpenAI(
            api_key=api_key,
            timeout=httpx.Timeout(float(settings.report_section_timeout), connect=15.0),
            max_retries=0
        )
    
    async def build_report(
        self,
        saju_data: Dict[str, Any],
        rulecards: List[Dict[str, Any]],
        target_year: int = 2026,
        user_question: str = "",
        name: str = "고객"
    ) -> Dict[str, Any]:
        """
        7개 섹션 병렬 생성 + 합성
        
        Returns:
            최종 합성 JSON 리포트
        """
        settings = get_settings()
        start_time = time.time()
        
        # Semaphore로 동시성 제한
        self._semaphore = asyncio.Semaphore(settings.report_max_concurrency)
        self._client = self._get_client()
        
        logger.info(f"[ReportBuilder] 시작 | Year={target_year} | Cards={len(rulecards)} | Concurrency={settings.report_max_concurrency}")
        
        # 섹션별 생성 태스크
        section_ids = list(SECTION_SPECS.keys())
        tasks = [
            self._generate_section(
                section_id=sid,
                saju_data=saju_data,
                rulecards=rulecards,
                target_year=target_year,
                user_question=user_question
            )
            for sid in section_ids
        ]
        
        # 병렬 실행
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 결과 수집
        sections = {}
        latency_by_section = {}
        rulecards_used_total = 0
        confidence_by_section = {}
        
        for sid, result in zip(section_ids, results):
            if isinstance(result, Exception):
                logger.error(f"[ReportBuilder] 섹션 실패: {sid} | {type(result).__name__}: {str(result)[:100]}")
                # 폴백 섹션 생성
                sections[sid] = self._create_fallback_section(sid, target_year)
                confidence_by_section[sid] = "LOW"
                latency_by_section[sid] = 0
            else:
                sections[sid] = result["content"]
                latency_by_section[sid] = result["latency_ms"]
                rulecards_used_total += len(result.get("rulecard_ids", []))
                confidence_by_section[sid] = result["content"].get("confidence", "MEDIUM")
        
        total_latency = int((time.time() - start_time) * 1000)
        
        # 최종 합성 JSON
        report = {
            "meta": {
                "reportType": "business_owner_v2",
                "targetYear": target_year,
                "mode": "sectioned",
                "generatedAt": datetime.now().isoformat(),
                "llmModel": settings.openai_model,
                "sectionCount": len(sections),
                "ruleCardsUsedTotal": rulecards_used_total,
                "featureTagsCount": 0,
                "confidence": {
                    "overall": self._calculate_overall_confidence(confidence_by_section),
                    "bySection": confidence_by_section
                },
                "latencyMs": {
                    "total": total_latency,
                    "bySection": latency_by_section
                }
            },
            "toc": [
                {"id": sid, "title": SECTION_SPECS[sid]["title"]}
                for sid in section_ids
            ],
            "sections": sections,
            "render": {
                "mergedMarkdown": self._merge_markdown(sections),
                "notes": "본 보고서는 동양 철학에 기반한 통찰을 제공하며, 의학/법률/투자 등 전문 분야의 조언을 대체하지 않습니다."
            },
            # 레거시 호환 필드
            "legacy": self._create_legacy_fields(sections, target_year, name)
        }
        
        logger.info(f"[ReportBuilder] 완료 | Sections={len(sections)} | TotalLatency={total_latency}ms | CardsUsed={rulecards_used_total}")
        
        return report
    
    async def _generate_section(
        self,
        section_id: str,
        saju_data: Dict[str, Any],
        rulecards: List[Dict[str, Any]],
        target_year: int,
        user_question: str
    ) -> Dict[str, Any]:
        """단일 섹션 생성 (Semaphore로 동시성 제한)"""
        settings = get_settings()
        
        async with self._semaphore:
            start_time = time.time()
            
            # 룰카드 분배
            rulecards_context, rulecard_ids = distribute_rulecards(
                rulecards,
                section_id,
                saju_data,
                settings.report_section_max_rulecards
            )
            
            # 프롬프트 생성
            system_prompt = get_section_system_prompt(section_id, target_year)
            user_prompt = get_section_user_prompt(
                section_id, saju_data, rulecards_context, target_year, user_question
            )
            
            logger.info(f"[Section:{section_id}] 시작 | Cards={len(rulecard_ids)}")
            
            try:
                # GPT 호출
                response = await self._client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=settings.report_section_max_output_tokens,
                    temperature=0.3,
                    response_format={"type": "json_object"}
                )
                
                content_str = response.choices[0].message.content
                content = self._parse_json(content_str)
                
                if not content:
                    raise ValueError("JSON 파싱 실패")
                
                # evidence에 실제 사용된 카드 ID 추가
                if "evidence" not in content:
                    content["evidence"] = {}
                content["evidence"]["ruleCardIds"] = rulecard_ids
                
                latency_ms = int((time.time() - start_time) * 1000)
                tokens_used = response.usage.total_tokens if response.usage else 0
                
                logger.info(f"[Section:{section_id}] 완료 | Latency={latency_ms}ms | Tokens={tokens_used}")
                
                return {
                    "content": content,
                    "latency_ms": latency_ms,
                    "tokens_used": tokens_used,
                    "rulecard_ids": rulecard_ids
                }
                
            except Exception as e:
                logger.error(f"[Section:{section_id}] 에러: {type(e).__name__}: {str(e)[:100]}")
                
                # 폴백: 짧은 모드 재시도
                if settings.report_enable_fallback and settings.report_fallback_short_mode:
                    try:
                        return await self._generate_section_short_mode(
                            section_id, saju_data, rulecard_ids[:20], target_year
                        )
                    except Exception as e2:
                        logger.error(f"[Section:{section_id}] 짧은 모드도 실패: {str(e2)[:50]}")
                
                raise
    
    async def _generate_section_short_mode(
        self,
        section_id: str,
        saju_data: Dict[str, Any],
        rulecard_ids: List[str],
        target_year: int
    ) -> Dict[str, Any]:
        """짧은 모드로 재시도 (분량 요구 완화)"""
        settings = get_settings()
        start_time = time.time()
        
        # 간단한 프롬프트
        simple_prompt = f"""당신은 사주 분석 전문가입니다.
{target_year}년 기준으로 {SECTION_SPECS[section_id]['title']} 섹션을 간략히 작성해주세요.

JSON 형식으로 응답:
{{
  "title": "{SECTION_SPECS[section_id]['title']}",
  "markdown": "## {SECTION_SPECS[section_id]['title']}\\n\\n(간략한 분석 내용)",
  "highlights": ["핵심1", "핵심2", "핵심3"],
  "actionItems": ["액션1", "액션2", "액션3"],
  "evidence": {{"ruleCardIds": [], "topTags": []}},
  "confidence": "LOW"
}}
"""
        
        response = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": simple_prompt}],
            max_tokens=1500,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        content = self._parse_json(response.choices[0].message.content)
        if not content:
            content = self._create_fallback_section(section_id, target_year)
        
        content["evidence"] = {"ruleCardIds": rulecard_ids, "topTags": []}
        content["confidence"] = "LOW"
        
        return {
            "content": content,
            "latency_ms": int((time.time() - start_time) * 1000),
            "tokens_used": response.usage.total_tokens if response.usage else 0,
            "rulecard_ids": rulecard_ids
        }
    
    def _create_fallback_section(self, section_id: str, target_year: int) -> Dict[str, Any]:
        """템플릿 기반 폴백 섹션"""
        spec = SECTION_SPECS.get(section_id, {})
        return {
            "title": spec.get("title", section_id),
            "markdown": f"## {spec.get('title', section_id)}\n\n{target_year}년 분석 데이터를 불러오는 중 일시적인 문제가 발생했습니다.\n\n잠시 후 다시 시도해주세요.",
            "highlights": ["서비스 일시 지연"],
            "actionItems": ["잠시 후 재시도"],
            "evidence": {"ruleCardIds": [], "topTags": []},
            "confidence": "LOW"
        }
    
    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        """JSON 파싱 (마크다운 코드블록 제거)"""
        if not content:
            return None
        
        text = content.strip()
        
        # 코드블록 제거
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
            text = "\n".join(lines)
        
        try:
            return json.loads(text)
        except:
            pass
        
        # JSON 부분 추출 시도
        import re
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
        
        return None
    
    def _calculate_overall_confidence(self, by_section: Dict[str, str]) -> str:
        """전체 신뢰도 계산"""
        scores = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        total = sum(scores.get(v, 2) for v in by_section.values())
        avg = total / len(by_section) if by_section else 2
        
        if avg >= 2.5:
            return "HIGH"
        elif avg >= 1.5:
            return "MEDIUM"
        return "LOW"
    
    def _merge_markdown(self, sections: Dict[str, Any]) -> str:
        """모든 섹션의 마크다운 합체"""
        parts = []
        for section_id in SECTION_SPECS.keys():
            section = sections.get(section_id, {})
            md = section.get("markdown", "")
            if md:
                parts.append(md)
        
        return "\n\n---\n\n".join(parts)
    
    def _create_legacy_fields(
        self,
        sections: Dict[str, Any],
        target_year: int,
        name: str
    ) -> Dict[str, Any]:
        """기존 프론트엔드 호환용 레거시 필드"""
        exec_section = sections.get("exec", {})
        money_section = sections.get("money", {})
        calendar_section = sections.get("calendar", {})
        sprint_section = sections.get("sprint", {})
        
        # 강점 추출
        strengths = []
        for h in exec_section.get("highlights", [])[:5]:
            if isinstance(h, dict):
                strengths.append(h.get("content", str(h)))
            else:
                strengths.append(str(h))
        
        # 리스크 추출
        risks = []
        for r in exec_section.get("risks", [])[:3]:
            if isinstance(r, dict):
                risks.append(r.get("content", str(r)))
            else:
                risks.append(str(r))
        
        # 액션 플랜 추출
        action_plan = []
        for a in exec_section.get("actionItems", [])[:5]:
            if isinstance(a, dict):
                action_plan.append(a.get("action", str(a)))
            else:
                action_plan.append(str(a))
        
        # 좋은 시기 / 주의 시기
        year_overview = calendar_section.get("yearOverview", {})
        lucky_periods = year_overview.get("bestMonths", [])
        caution_periods = year_overview.get("cautionMonths", [])
        
        return {
            "success": True,
            "summary": f"{target_year}년 프리미엄 비즈니스 컨설팅 보고서",
            "day_master_analysis": exec_section.get("markdown", "")[:500],
            "strengths": strengths,
            "risks": risks,
            "answer": exec_section.get("markdown", ""),
            "action_plan": action_plan,
            "lucky_periods": lucky_periods,
            "caution_periods": caution_periods,
            "lucky_elements": {
                "color": "황금색",
                "direction": "남동쪽",
                "number": "8"
            },
            "blessing": f"{name}님, {target_year}년 큰 성취를 이루시길 응원합니다!",
            "disclaimer": "본 보고서는 오락/참고 목적으로 제공되며, 전문적 조언을 대체하지 않습니다."
        }


# 싱글톤 인스턴스
report_builder = ReportBuilder()
