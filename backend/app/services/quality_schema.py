"""
Quality Schema - Evidence → Action 스키마 강제
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P2 요구사항:
- 모든 섹션에 evidence/actions/risks/opportunities 필수
- 파싱 실패 시 자동 Retry (최대 3회)
- 금지어 필터 + 유사문장 중복 제거
- 모든 action은 수치(%, 횟수, 기간) + 주차별 체크리스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import re
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Pydantic 스키마 정의
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ActionItem(BaseModel):
    """액션 아이템 - 반드시 수치/기간 포함"""
    action: str = Field(..., description="구체적 액션 (수치/기간 필수)")
    metric: str = Field(..., description="측정 지표 (%, 횟수, 금액)")
    deadline: str = Field(..., description="기한 (n주차, n월, Q1 등)")
    checklist: List[str] = Field(default_factory=list, description="주차별 체크리스트")
    
    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        # 수치 포함 여부 체크
        if not re.search(r'\d+', v):
            raise ValueError(f"액션에 수치가 없음: {v}")
        return v


class EvidenceItem(BaseModel):
    """근거 아이템 - 사주 데이터 기반"""
    source: str = Field(..., description="근거 출처 (기둥, 십신, 오행 등)")
    finding: str = Field(..., description="발견 내용")
    implication: str = Field(..., description="비즈니스 시사점")


class RiskItem(BaseModel):
    """리스크 아이템"""
    risk: str = Field(..., description="리스크 설명")
    probability: str = Field(..., description="발생 확률 (높음/중간/낮음)")
    mitigation: str = Field(..., description="완화 방안")
    timeline: str = Field(..., description="주의 시기")


class OpportunityItem(BaseModel):
    """기회 아이템"""
    opportunity: str = Field(..., description="기회 설명")
    timing: str = Field(..., description="최적 시기")
    action_required: str = Field(..., description="필요 액션")
    expected_outcome: str = Field(..., description="예상 결과 (수치 포함)")


class SectionContent(BaseModel):
    """섹션 콘텐츠 스키마 - 모든 섹션에 적용"""
    title: str = Field(..., description="섹션 제목")
    summary: str = Field(..., description="요약 (3문장 이내)")
    
    evidence: List[EvidenceItem] = Field(
        ..., 
        min_length=2,
        description="근거 (최소 2개)"
    )
    
    actions: List[ActionItem] = Field(
        ..., 
        min_length=3,
        description="액션 아이템 (최소 3개, 수치/기간 필수)"
    )
    
    risks: List[RiskItem] = Field(
        default_factory=list,
        description="리스크 (0개 이상)"
    )
    
    opportunities: List[OpportunityItem] = Field(
        default_factory=list,
        description="기회 (0개 이상)"
    )
    
    weekly_checklist: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="주차별 체크리스트 (week1, week2...)"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 금지어 리스트 (자기계발서 탈출)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BANNED_PHRASES = [
    # 자기계발서 클리셰
    "노력하면", "노력이 필요", "꾸준히 노력", "꾸준한 노력",
    "성장의 기회", "성장할 수 있", "성장하는",
    "긍정적인 마인드", "긍정적으로", "긍정의 힘",
    "기회가 찾아", "기회를 잡", "좋은 기회",
    "도전정신", "도전하는 자세",
    "잠재력을 발휘", "잠재력이 있",
    "자신감을 가지", "자신감을 잃지",
    "꿈을 향해", "꿈을 이루",
    "열정을 가지", "열정적으로",
    "포기하지 마", "포기하지 않",
    "믿음을 가지", "믿음이 필요",
    "한 걸음씩", "한 단계씩",
    "마음먹기에 달려", "마음가짐",
    "진정한 성공", "성공으로 이끌",
    "밝은 미래", "더 나은 내일",
    "최선을 다하", "최선의 노력",
    
    # 덕담
    "행운이 함께", "행운을 빌",
    "좋은 결과가", "좋은 일이",
    "잘 될 것", "잘 풀릴",
    "축복이", "복이 따르",
    "순탄한", "순조로운",
    "무궁무진한", "무한한 가능성",
    
    # 모호한 표현
    "할 수 있습니다", "할 수 있을 것",
    "도움이 될 것", "도움이 됩니다",
    "좋을 것 같습니다", "좋겠습니다",
    "고려해 보세요", "생각해 보세요",
    "중요합니다", "필요합니다",
    
    # 취업/경력 관련 (비즈니스 리포트에 부적절)
    "취업", "이력서", "면접", "자격증", "포트폴리오",
    "채용", "합격", "입사", "퇴사", "구직",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 검증 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_banned_phrases(text: str) -> List[str]:
    """금지어 검출"""
    found = []
    for phrase in BANNED_PHRASES:
        if phrase in text:
            found.append(phrase)
    return found


def check_duplicate_sentences(text: str, threshold: float = 0.8) -> List[tuple]:
    """유사 문장 중복 검출"""
    sentences = re.split(r'[.!?]\s*', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    duplicates = []
    for i, s1 in enumerate(sentences):
        for j, s2 in enumerate(sentences):
            if i < j:
                ratio = SequenceMatcher(None, s1, s2).ratio()
                if ratio > threshold:
                    duplicates.append((s1[:50], s2[:50], ratio))
    
    return duplicates


def check_action_specificity(actions: List[Dict]) -> List[str]:
    """액션 구체성 검증 - 수치/기간 필수"""
    issues = []
    
    for i, action in enumerate(actions):
        action_text = action.get("action", "")
        
        # 수치 체크
        has_number = bool(re.search(r'\d+', action_text))
        
        # 기간 체크
        has_timeline = bool(re.search(
            r'(주차|월|분기|Q\d|일|주|년|week|month|day)', 
            action_text, 
            re.IGNORECASE
        ))
        
        if not has_number:
            issues.append(f"Action {i+1}: 수치 없음 - '{action_text[:50]}'")
        if not has_timeline:
            issues.append(f"Action {i+1}: 기간 없음 - '{action_text[:50]}'")
    
    return issues


def validate_section_content(content: Dict[str, Any]) -> Dict[str, Any]:
    """
    섹션 콘텐츠 전체 검증
    
    Returns:
        {
            "valid": bool,
            "issues": [...],
            "banned_phrases": [...],
            "duplicates": [...],
            "action_issues": [...],
            "score": 0-100
        }
    """
    result = {
        "valid": True,
        "issues": [],
        "banned_phrases": [],
        "duplicates": [],
        "action_issues": [],
        "score": 100
    }
    
    # 텍스트 추출
    full_text = str(content)
    
    # 1. 금지어 체크
    banned = check_banned_phrases(full_text)
    if banned:
        result["banned_phrases"] = banned
        result["issues"].append(f"금지어 {len(banned)}개 발견")
        result["score"] -= len(banned) * 5
    
    # 2. 중복 문장 체크
    duplicates = check_duplicate_sentences(full_text)
    if duplicates:
        result["duplicates"] = duplicates
        result["issues"].append(f"유사 문장 {len(duplicates)}쌍 발견")
        result["score"] -= len(duplicates) * 10
    
    # 3. 필수 필드 체크
    required_fields = ["evidence", "actions"]
    for field in required_fields:
        if field not in content or not content[field]:
            result["issues"].append(f"필수 필드 없음: {field}")
            result["score"] -= 20
    
    # 4. 액션 구체성 체크
    if "actions" in content and content["actions"]:
        action_issues = check_action_specificity(content["actions"])
        if action_issues:
            result["action_issues"] = action_issues
            result["issues"].append(f"액션 구체성 부족 {len(action_issues)}건")
            result["score"] -= len(action_issues) * 5
    
    # 5. 최소 개수 체크
    if len(content.get("evidence", [])) < 2:
        result["issues"].append("evidence 최소 2개 필요")
        result["score"] -= 15
    
    if len(content.get("actions", [])) < 3:
        result["issues"].append("actions 최소 3개 필요")
        result["score"] -= 15
    
    # 합격 여부
    result["score"] = max(0, result["score"])
    result["valid"] = result["score"] >= 70 and len(result["issues"]) == 0
    
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 파싱 + Retry 래퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_section_content(raw_json: Dict[str, Any], max_retries: int = 3) -> Optional[SectionContent]:
    """
    섹션 콘텐츠 파싱 (Pydantic 검증)
    
    - 파싱 실패 시 None 반환
    - 호출자가 재시도 로직 처리
    """
    try:
        return SectionContent(**raw_json)
    except Exception as e:
        logger.warning(f"[Schema] 파싱 실패: {e}")
        return None


def clean_banned_from_text(text: str) -> str:
    """금지어를 대체 표현으로 치환"""
    replacements = {
        "노력하면": "실행하면",
        "노력이 필요": "실행이 필요",
        "꾸준히 노력": "지속 실행",
        "성장의 기회": "확장 가능성",
        "긍정적인 마인드": "실행 중심 사고",
        "좋은 기회": "유효한 기회",
        "마음가짐": "실행 전략",
        "할 수 있습니다": "실행하세요",
        "도움이 될 것": "효과가 있습니다",
        "좋겠습니다": "권장합니다",
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text


def get_quality_feedback_prompt(validation_result: Dict) -> str:
    """검증 결과를 기반으로 재생성 프롬프트 생성"""
    lines = [
        "\n[⚠️ 이전 생성 품질 피드백 - 반드시 수정하세요]\n"
    ]
    
    if validation_result["banned_phrases"]:
        lines.append(f"❌ 금지어 발견: {', '.join(validation_result['banned_phrases'][:5])}")
        lines.append("   → 이 표현들을 절대 사용하지 마세요.\n")
    
    if validation_result["action_issues"]:
        lines.append("❌ 액션 구체성 부족:")
        for issue in validation_result["action_issues"][:3]:
            lines.append(f"   - {issue}")
        lines.append("   → 모든 액션에 수치(%, 횟수, 금액)와 기간(n주차, n월)을 포함하세요.\n")
    
    if validation_result["duplicates"]:
        lines.append(f"❌ 유사 문장 중복: {len(validation_result['duplicates'])}쌍")
        lines.append("   → 같은 의미를 반복하지 마세요.\n")
    
    lines.append(f"현재 점수: {validation_result['score']}/100 (70점 이상 필요)\n")
    
    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. JSON 스키마 (OpenAI Structured Output용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "finding": {"type": "string"},
                    "implication": {"type": "string"}
                },
                "required": ["source", "finding", "implication"]
            },
            "minItems": 2
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "metric": {"type": "string"},
                    "deadline": {"type": "string"},
                    "checklist": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["action", "metric", "deadline"]
            },
            "minItems": 3
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string"},
                    "probability": {"type": "string"},
                    "mitigation": {"type": "string"},
                    "timeline": {"type": "string"}
                },
                "required": ["risk", "probability", "mitigation", "timeline"]
            }
        },
        "opportunities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "opportunity": {"type": "string"},
                    "timing": {"type": "string"},
                    "action_required": {"type": "string"},
                    "expected_outcome": {"type": "string"}
                },
                "required": ["opportunity", "timing", "action_required", "expected_outcome"]
            }
        },
        "weekly_checklist": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"}
            }
        }
    },
    "required": ["title", "summary", "evidence", "actions"]
}
