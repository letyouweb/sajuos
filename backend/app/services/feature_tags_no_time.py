from __future__ import annotations
from typing import Dict, List, Set

STEM_META = {
  "甲":("목","양"),"乙":("목","음"),
  "丙":("화","양"),"丁":("화","음"),
  "戊":("토","양"),"己":("토","음"),
  "庚":("금","양"),"辛":("금","음"),
  "壬":("수","양"),"癸":("수","음"),
}
STEM_TO_TAG = {"甲":"갑목","乙":"을목","丙":"병화","丁":"정화","戊":"무토","己":"기토","庚":"경금","辛":"신금","壬":"임수","癸":"계수"}
BRANCH_TO_TAG = {"子":"자수","丑":"축토","寅":"인목","卯":"묘목","辰":"진토","巳":"사화","午":"오화","未":"미토","申":"신금","酉":"유금","戌":"술토","亥":"해수"}
BRANCH_MAIN_ELEM = {"子":"수","丑":"토","寅":"목","卯":"목","辰":"토","巳":"화","午":"화","未":"토","申":"금","酉":"금","戌":"토","亥":"수"}

HIDDEN_STEMS = {
  "子":[("癸",1.0)],
  "丑":[("己",0.6),("癸",0.3),("辛",0.1)],
  "寅":[("甲",0.6),("丙",0.3),("戊",0.1)],
  "卯":[("乙",1.0)],
  "辰":[("戊",0.6),("乙",0.3),("癸",0.1)],
  "巳":[("丙",0.6),("戊",0.3),("庚",0.1)],
  "午":[("丁",0.7),("己",0.3)],
  "未":[("己",0.6),("丁",0.3),("乙",0.1)],
  "申":[("庚",0.6),("壬",0.3),("戊",0.1)],
  "酉":[("辛",1.0)],
  "戌":[("戊",0.6),("辛",0.3),("丁",0.1)],
  "亥":[("壬",0.7),("甲",0.3)],
}

GEN = {"목":"화","화":"토","토":"금","금":"수","수":"목"}
CTRL = {"목":"토","토":"수","수":"화","화":"금","금":"목"}

def ten_god(day_stem: str, other_stem: str) -> str:
    dm_elem, dm_yy = STEM_META[day_stem]
    ot_elem, ot_yy = STEM_META[other_stem]
    same_yy = (dm_yy == ot_yy)

    if dm_elem == ot_elem:
        return "비견" if same_yy else "겁재"
    if GEN[dm_elem] == ot_elem:
        return "식신" if same_yy else "상관"
    if CTRL[dm_elem] == ot_elem:
        return "편재" if same_yy else "정재"
    if CTRL[ot_elem] == dm_elem:
        return "편관" if same_yy else "정관"
    if GEN[ot_elem] == dm_elem:
        return "편인" if same_yy else "정인"
    return "비견"

def group_of(tg: str) -> str:
    if tg in ("비견","겁재"): return "비겁"
    if tg in ("식신","상관"): return "식상"
    if tg in ("정재","편재"): return "재성"
    if tg in ("정관","편관"): return "관성"
    return "인성"

CHUNG = set(["子午","午子","丑未","未丑","寅申","申寅","卯酉","酉卯","辰戌","戌辰","巳亥","亥巳"])
YUKHAP = set(["子丑","丑子","寅亥","亥寅","卯戌","戌卯","辰酉","酉辰","巳申","申巳","午未","未午"])
PA = set(["子酉","酉子","丑辰","辰丑","寅亥","亥寅","卯午","午卯","申巳","巳申","未戌","戌未"])
HAE = set(["子未","未子","丑午","午丑","寅巳","巳寅","卯辰","辰卯","申亥","亥申","酉戌","戌酉"])
SAMHAP_SETS = [set(["申","子","辰"]), set(["寅","午","戌"]), set(["亥","卯","未"]), set(["巳","酉","丑"])]

def branch_dynamics(branches: List[str]) -> List[str]:
    tags = set()
    uniq = list(dict.fromkeys(branches))
    for i in range(len(uniq)):
        for j in range(i+1, len(uniq)):
            a, b = uniq[i], uniq[j]
            key = a+b
            if key in CHUNG: tags.add("충")
            if key in YUKHAP: tags.add("육합")
            if key in PA: tags.add("파")
            if key in HAE: tags.add("해")
            # 간단 형
            if (a=="子" and b=="卯") or (a=="卯" and b=="子"): tags.add("형")
            if (a in ["寅","巳","申"] and b in ["寅","巳","申"]): tags.add("형")
            if (a in ["丑","戌","未"] and b in ["丑","戌","未"]): tags.add("형")
    for s in SAMHAP_SETS:
        if all(x in uniq for x in s):
            tags.add("삼합")
    return list(tags)

def season_by_month_branch(mb: str) -> str:
    if mb in ["巳","午","未"]: return "summer"
    if mb in ["亥","子","丑"]: return "winter"
    if mb in ["寅","卯","辰"]: return "spring"
    return "autumn"

def build_feature_tags_no_time_from_pillars(
    year_pillar: str, month_pillar: str, day_pillar: str, overlay_year: int = 2026
) -> Dict:
    yStem, yBranch = year_pillar[0], year_pillar[1]
    mStem, mBranch = month_pillar[0], month_pillar[1]
    dStem, dBranch = day_pillar[0], day_pillar[1]  # day master

    tags: Set[str] = set()

    # 기본 태그
    tags.add(STEM_TO_TAG.get(dStem, ""))
    tags.add(BRANCH_TO_TAG.get(yBranch, ""))
    tags.add(BRANCH_TO_TAG.get(mBranch, ""))
    tags.add(BRANCH_TO_TAG.get(dBranch, ""))
    tags.add(STEM_META[dStem][0])  # 일간 오행
    tags.add("조후")

    # 십신 + 그룹
    ten_cnt: Dict[str, float] = {}
    grp_cnt: Dict[str, float] = {"비겁":0,"식상":0,"재성":0,"관성":0,"인성":0}

    def push_tg(tg: str, w: float):
        ten_cnt[tg] = ten_cnt.get(tg, 0) + w
        grp_cnt[group_of(tg)] += w
        tags.add(tg); tags.add(group_of(tg))

    push_tg(ten_god(dStem, yStem), 1.0)
    push_tg(ten_god(dStem, mStem), 1.0)
    for b in [yBranch, mBranch, dBranch]:
        for hs, w in HIDDEN_STEMS.get(b, []):
            push_tg(ten_god(dStem, hs), w)

    # 오행 비율(간단)
    elem_mass = {"목":0.0,"화":0.0,"토":0.0,"금":0.0,"수":0.0}
    def add_elem(e: str, w: float): elem_mass[e] += w
    add_elem(STEM_META[yStem][0], 1); add_elem(STEM_META[mStem][0], 1); add_elem(STEM_META[dStem][0], 1)
    add_elem(BRANCH_MAIN_ELEM[yBranch], 1); add_elem(BRANCH_MAIN_ELEM[mBranch], 1); add_elem(BRANCH_MAIN_ELEM[dBranch], 1)
    for b in [yBranch, mBranch, dBranch]:
        for hs, w in HIDDEN_STEMS.get(b, []):
            add_elem(STEM_META[hs][0], 0.6*w)

    total = sum(elem_mass.values()) or 1.0
    elem_ratio = {k: v/total for k, v in elem_mass.items()}

    # 신강/신약(간단 점수)
    dm_elem = STEM_META[dStem][0]
    month_elem = BRANCH_MAIN_ELEM[mBranch]
    strength = 0.0
    if month_elem == dm_elem: strength += 2.0
    elif GEN[month_elem] == dm_elem: strength += 1.0
    elif CTRL[month_elem] == dm_elem: strength -= 1.0
    elif CTRL[dm_elem] == month_elem: strength -= 0.5
    elif GEN[dm_elem] == month_elem: strength -= 0.5

    # 주변 가중
    token_elems = [(STEM_META[yStem][0],1.0),(STEM_META[mStem][0],1.0),
                   (BRANCH_MAIN_ELEM[yBranch],1.0),(BRANCH_MAIN_ELEM[mBranch],1.0),(BRANCH_MAIN_ELEM[dBranch],1.0)]
    for b in [yBranch, mBranch, dBranch]:
        for hs, w in HIDDEN_STEMS.get(b, []):
            token_elems.append((STEM_META[hs][0], w))
    for e, w in token_elems:
        if e == dm_elem: strength += 0.4*w
        elif GEN[e] == dm_elem: strength += 0.25*w
        elif CTRL[e] == dm_elem: strength -= 0.25*w

    if strength >= 2.5: tags.add("신강")
    elif strength <= 0.5: tags.add("신약")
    else: tags.add("중화")

    # 조후/습건
    season = season_by_month_branch(mBranch)
    if season == "summer": tags.add("조열")
    if season == "winter": tags.add("한랭")
    hot_dry = elem_ratio["화"] + elem_ratio["토"]
    cool_wet = elem_ratio["수"] + elem_ratio["금"]
    if hot_dry - cool_wet > 0.15: tags.add("건조")
    if cool_wet - hot_dry > 0.15: tags.add("습윤")

    # 지지 다이내믹(원국)
    for t in branch_dynamics([yBranch, mBranch, dBranch]):
        tags.add(t)

    # 2026 오버레이(병오)
    if overlay_year == 2026:
        tags.update(["병화","오화","화"])
        for t in branch_dynamics([yBranch, mBranch, dBranch, "午"]):
            tags.add(t)

    # 사업가형 실무 태그(그룹 기반)
    if grp_cnt["식상"] >= 2: tags.update(["실행","마케팅","성과","사업"])
    if grp_cnt["재성"] >= 2: tags.update(["자산","투자","재정","재물","재테크"])
    if grp_cnt["관성"] >= 2: tags.update(["조직","관리","권위","책임","직업"])
    if grp_cnt["인성"] >= 2: tags.update(["전문성","자격","문서"])
    if grp_cnt["비겁"] >= 2: tags.update(["확장","리더십","경쟁","동업"])

    # 추가 파생태그(정밀도 핵심)
    def has_tg(k: str) -> bool: return ten_cnt.get(k, 0.0) >= 0.8
    wealth_any = ten_cnt.get("정재",0)+ten_cnt.get("편재",0) >= 1.0
    officer_any = ten_cnt.get("정관",0)+ten_cnt.get("편관",0) >= 1.0
    resource_any = ten_cnt.get("정인",0)+ten_cnt.get("편인",0) >= 1.0
    output_any = ten_cnt.get("식신",0)+ten_cnt.get("상관",0) >= 1.0

    if wealth_any and officer_any: tags.add("재생관")
    if officer_any and resource_any: tags.add("관인상생")
    if has_tg("편관") and resource_any: tags.add("살인상생")
    if has_tg("정관") and has_tg("편관"): tags.add("관살혼잡")
    if has_tg("상관") and has_tg("정관"): tags.add("상관견관")
    if has_tg("식신") and has_tg("편관"): tags.add("식신제살")
    if has_tg("식신") and wealth_any: tags.add("식신생재")
    if has_tg("상관") and wealth_any: tags.add("상관생재")
    if output_any and wealth_any: tags.add("식상생재")
    if wealth_any and strength <= 0.5: tags.add("재다신약")

    out = [t for t in tags if t]
    return {
        "tags": sorted(out),
        "debug": {
            "pillars": {"year":year_pillar,"month":month_pillar,"day":day_pillar},
            "elem_ratio": elem_ratio,
            "strength_score": round(strength, 2),
            "group_counts": grp_cnt,
            "ten_counts": ten_cnt,
        }
    }
