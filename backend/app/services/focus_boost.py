from __future__ import annotations
from typing import Dict, List, Set

TAG_NORMALIZE = {
    "정제":"정재","편제":"편재","겁제":"겁재",
    "식신생제":"식신생재","상관생제":"상관생재","식상생제":"식상생재",
    "간목":"인목","신지금":"신금",
}

def canon(t: str) -> str:
    s = " ".join(str(t).strip().split())
    return TAG_NORMALIZE.get(s, s)

def has(ft: Set[str], *keys: str) -> bool:
    return any(canon(k) in ft for k in keys)

def boost_preset_focus(preset: Dict, feature_tags: List[str]) -> Dict:
    ft = set(canon(x) for x in feature_tags)

    BASE = {
        "EXEC_SUMMARY": ["우선순위","전략","리스크","조절","성과","목표"],
        "MONEY": ["현금흐름","유동성","지출","투자","자산","리스크","방어"],
        "BUSINESS": ["포지셔닝","확장","관리","전문성","브랜딩","성과"],
        "TEAM_RISK": ["계약","권한","정산","책임","갈등","리스크","관리"],
        "HEALTH_PERF": ["루틴","수면","스트레스","번아웃","조절","회복"],
        "CALENDAR": ["결정","타이밍","리스크","기회","변화","계획"],
        "SPRINT_90D": ["실행","성과","지표","집중","속도","관리"],
    }

    RULES = [
        (lambda ft: has(ft, "재생관"), {
            "MONEY": ["문서","권리","계약","자산","재산","축적","안정성"],
            "BUSINESS": ["권위","책임","조직","관리","거래","거버넌스"],
            "TEAM_RISK": ["책임","권한","정산","계약","분쟁"],
        }),
        (lambda ft: has(ft, "관인상생"), {
            "BUSINESS": ["자격","문서","전문성","브랜딩","공신력","권위"],
            "EXEC_SUMMARY": ["전문성","권위","문서","자격"],
        }),
        (lambda ft: has(ft, "식신생재","상관생재","식상생재"), {
            "BUSINESS": ["마케팅","콘텐츠","세일즈","상품","런칭","성과"],
            "MONEY": ["수익","매출","현금흐름","확장","지출통제"],
            "SPRINT_90D": ["실행","마케팅","런칭","지표","KPI","성과"],
        }),
        (lambda ft: has(ft, "재다신약"), {
            "MONEY": ["방어","현금흐름","지출","리스크","안정","조절","축적"],
            "HEALTH_PERF": ["번아웃","조절","루틴","회복","수면","스트레스"],
            "TEAM_RISK": ["권한","정산","계약","책임","리스크"],
        }),
        (lambda ft: has(ft, "관살혼잡"), {
            "TEAM_RISK": ["규칙","감사","책임","권한","계약","정산","분쟁","리스크"],
            "BUSINESS": ["관리","거버넌스","조직","책임","규정"],
            "CALENDAR": ["주의","리스크","결정","검토","보류"],
        }),
        (lambda ft: has(ft, "상관견관"), {
            "TEAM_RISK": ["구설","갈등","규칙","계약","리스크","대외발언","검토"],
            "BUSINESS": ["브랜딩","메시지","소통","관리","규정"],
            "CALENDAR": ["발언주의","계약주의","검토"],
        }),
        (lambda ft: has(ft, "식신제살","살인상생"), {
            "HEALTH_PERF": ["루틴","규칙","회복","조절","지속성"],
            "BUSINESS": ["장기전","운영","관리","프로세스","품질"],
            "MONEY": ["안정성","방어","축적"],
        }),
        (lambda ft: has(ft, "조열","건조"), {
            "HEALTH_PERF": ["과열","휴식","수면","조절","회복"],
            "CALENDAR": ["무리금지","리스크","보류"],
        }),
        (lambda ft: has(ft, "한랭","습윤"), {"HEALTH_PERF": ["활력","루틴","지속성","회복"]}),
        (lambda ft: has(ft, "충","형","파","해"), {
            "TEAM_RISK": ["갈등","분쟁","계약","정산","리스크"],
            "CALENDAR": ["충돌","주의","리스크","보류","검토"],
        }),
        (lambda ft: has(ft, "육합","삼합"), {
            "BUSINESS": ["협력","네트워크","확장","기회"],
            "TEAM_RISK": ["협력","소통","파트너"],
        }),
        (lambda ft: has(ft, "비겁"), {"TEAM_RISK": ["경쟁","동업","수익배분","정산","권한","리스크"], "MONEY": ["지출","누수","수수료","유동성"]}),
        (lambda ft: has(ft, "인성"), {"BUSINESS": ["문서","자격","연구","전문성","권위"], "MONEY": ["권리","저작권","문서"]}),
        (lambda ft: has(ft, "관성"), {"BUSINESS": ["조직","관리","규정","권위","책임"], "TEAM_RISK": ["규칙","책임","감사","계약"]}),
        (lambda ft: has(ft, "식상"), {"BUSINESS": ["마케팅","런칭","성과","콘텐츠","세일즈"], "SPRINT_90D": ["실행","지표","런칭","성과"]}),
        (lambda ft: has(ft, "재성"), {"MONEY": ["자산","투자","현금흐름","수익","축적"]}),
    ]

    enhanced = {**preset}
    enhanced_sections = []
    for sec in preset["sections"]:
        cur = set(canon(x) for x in sec["focusTags"])
        for x in BASE.get(sec["key"], []):
            cur.add(canon(x))
        for cond, apply in RULES:
            if cond(ft):
                for x in apply.get(sec["key"], []):
                    cur.add(canon(x))
        sec2 = {**sec, "focusTags": list(list(cur)[:28])}
        enhanced_sections.append(sec2)

    enhanced["sections"] = enhanced_sections
    return enhanced
